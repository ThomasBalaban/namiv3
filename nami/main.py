# Save as: nami/main.py
import uvicorn
import asyncio
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

import sys
import threading
import os
import subprocess
import time
import requests
import json
import re
import atexit
from nami.bot_core import ask_question, BOTNAME

from nami.twitch_integration import init_twitch_bot, send_to_twitch_sync
from nami.input_systems import (
    init_priority_system,
    shutdown_priority_system,
    process_console_command,
)

from nami.tts_utils.content_filter import process_response_for_content
from nami.director_process_manager import start_director_process, stop_director_process
from nami.director_connector import (
    start_connector_thread, 
    stop_connector, 
    send_bot_reply,
    notify_speech_started,  # NEW
    notify_speech_finished  # NEW
)

from nami.config import (
    NGROK_AUTH_ENABLED, 
    NGROK_AUTH_USERNAME, 
    NGROK_AUTH_PASSWORD,
    NGROK_BIND_TLS,
    NGROK_INSPECT,
    SECURITY_NOTIFICATIONS
)

try:
    from nami.input_funnel.input_funnel import InputFunnel
    input_funnel_available = True
except ImportError:
    input_funnel_available = False
    print("InputFunnel module not found, will use traditional priority system")

try:
    from nami.tts_utils.tts_engine import text_to_speech_file
    from nami.tts_utils.audio_player import play_audio_file
    tts_available = True
except ImportError:
    tts_available = False
    text_to_speech_file = None
    play_audio_file = None

global_input_funnel = None
ngrok_process = None

def start_ngrok_tunnel():
    global ngrok_process
    if SECURITY_NOTIFICATIONS:
        print("🔒 Starting secure ngrok tunnel for sound effects...")
    try:
        # Note: Director Engine is on 8002
        cmd = ["ngrok", "http", "8002"] 
        if NGROK_AUTH_ENABLED and NGROK_AUTH_USERNAME and NGROK_AUTH_PASSWORD:
            auth_string = f"{NGROK_AUTH_USERNAME}:{NGROK_AUTH_PASSWORD}"
            cmd.extend(["-auth", auth_string])
        if NGROK_BIND_TLS: cmd.append("-bind-tls=true")
        if not NGROK_INSPECT: cmd.append("-inspect=false")
        cmd.extend(["--log=stdout"])
        ngrok_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(3)
        response = requests.get("http://localhost:4040/api/tunnels", timeout=5)
        tunnels = response.json()
        if tunnels.get("tunnels"):
            public_url = tunnels["tunnels"][0]["public_url"]
            if SECURITY_NOTIFICATIONS:
                print(f"✅ Secure tunnel active: {public_url}")
                print(f"   (Pointing to Director Engine on port 8002)")
            return public_url
        else:
            print("❌ No ngrok tunnels found")
            return None
    except Exception as e:
        print(f"❌ Error starting secure ngrok: {e}")
        return None

def stop_ngrok():
    global ngrok_process
    if ngrok_process:
        if SECURITY_NOTIFICATIONS: print("🔒 Stopping secure ngrok tunnel...")
        ngrok_process.terminate()
        try: ngrok_process.wait(timeout=5)
        except subprocess.TimeoutExpired: ngrok_process.kill()
        ngrok_process = None

def check_tunnel_security():
    try:
        response = requests.get("http://localhost:4040/api/tunnels", timeout=2)
        tunnels = response.json()
        if not tunnels.get("tunnels"):
            if SECURITY_NOTIFICATIONS: print("ℹ️ No active tunnels to check")
            return False
        tunnel = tunnels["tunnels"][0]
        url = tunnel["public_url"]
        if SECURITY_NOTIFICATIONS:
            print(f"\n🔍 Security Status:")
            print(f"   Tunnel URL: {url}")
            print(f"   HTTPS: {'✅' if url.startswith('https') else '❌'}")
            print(f"   Auth: {'✅' if NGROK_AUTH_ENABLED else '❌'}")
            print(f"   Inspection: {'🔒 Disabled' if not NGROK_INSPECT else '⚠️ Enabled'}")
            if NGROK_AUTH_ENABLED:
                print(f"   Username: {NGROK_AUTH_USERNAME}")
                print(f"   Password: {NGROK_AUTH_PASSWORD}")
        return True
    except Exception as e:
        if SECURITY_NOTIFICATIONS: print(f"❌ Error checking tunnel security: {e}")
        return False

class FunnelResponseHandler:
    def __init__(self, generation_func=None, playback_func=None):
        self.generation_func = generation_func
        self.playback_func = playback_func

    def handle_response(self, response, prompt_details, source_info):
        if not response:
            print("Empty response received")
            return
        
        filtered_content = process_response_for_content(response)
        tts_version = filtered_content['tts_version']
        twitch_version = filtered_content['twitch_version']
        ui_version = filtered_content['ui_version']
        is_censored = filtered_content['is_censored']

        if is_censored:
            print(f"\n[BOT - CENSORED] Original: {response[:50]}...")
            print(f"[BOT - CENSORED] Sending: {tts_version}")
        else:
            print(f"\n[BOT] {tts_version}")
        
        # Send to Director UI for display
        send_bot_reply(ui_version, prompt_details or "", is_censored)

        try:
            source = source_info.get('source')
            if source in ['TWITCH_MENTION', 'DIRECT_MICROPHONE'] or source and source.startswith('DIRECTOR_'):
                username = source_info.get('username')
                if source == 'TWITCH_MENTION' and username:
                    twitch_response = f"@{username} {twitch_version}"
                else:
                    twitch_response = twitch_version
                send_to_twitch_sync(twitch_response)
        except Exception as e:
            print(f"[TWITCH] Error sending response: {e}")

        # --- TTS PLAYBACK (THE VOICE) ---
        if self.generation_func and self.playback_func:
            try:
                # --- NEW: Notify Director that we're starting to speak ---
                notify_speech_started()
                
                audio_filename = self.generation_func(tts_version)
                if audio_filename:
                    # Create a wrapper that notifies when playback is done
                    def playback_with_notification(filename):
                        try:
                            self.playback_func(filename)
                        finally:
                            # --- NEW: Notify Director that we're done speaking ---
                            notify_speech_finished()
                    
                    playback_thread = threading.Thread(
                        target=playback_with_notification,
                        args=(audio_filename,),
                        daemon=True
                    )
                    playback_thread.start()
                else:
                    # No audio file generated, notify finished immediately
                    notify_speech_finished()
            except Exception as e:
                print(f"[TTS] Error processing TTS: {e}")
                # Make sure we notify finished even on error
                notify_speech_finished()
        # If TTS not available, no need to notify (no speech lock needed)

def console_input_loop():
    print(f"{BOTNAME} is ready. (Console input available for debugging)")
    while True:
        try:
            command = input("You: ")
            if process_console_command(command):
                break
        except Exception as e:
            print(f"Error in console loop: {e}")
            break

# --- INTERJECTION SERVER (The Ear for the Director) ---
interjection_app = FastAPI()
INTERJECTION_PORT = 8000
class InterjectionPayload(BaseModel):
    content: str
    priority: float
    source_info: Dict[str, Any] = Field(default_factory=dict)

@interjection_app.post("/funnel/interject")
async def receive_interjection(payload: InterjectionPayload):
    global global_input_funnel
    if global_input_funnel:
        print(f"✅ Received Command from Director: {payload.content[:50]}...")
        global_input_funnel.add_input(
            content=payload.content,
            priority=payload.priority,
            source_info=payload.source_info
        )
        return {"status": "success", "message": "Command received."}
    else:
        print("❌ Received interjection, but Nami is not ready.")
        return {"status": "error", "message": "Nami funnel not ready."}

def run_interjection_server():
    print(f"Starting Local Command Server on http://0.0.0.0:{INTERJECTION_PORT}...")
    uvicorn.run(interjection_app, host="0.0.0.0", port=INTERJECTION_PORT, log_level="warning")

def start_interjection_server_thread():
    server_thread = threading.Thread(target=run_interjection_server, daemon=True, name="InterjectionServer")
    server_thread.start()
    print("Local Command Server thread started.")

def main():
    global global_input_funnel
    
    print("\n" + "="*60)
    print("🌊 NAMI V3 (The Body) - Starting Up...")
    print("="*60)

    # 1. Start the Brain (Director Engine)
    print("🚀 Launching Director Engine...")
    if not start_director_process():
        print("CRITICAL ERROR: Director Engine failed to start. Exiting.")
        return
    
    # 2. Start Local Servers
    start_interjection_server_thread()
    
    print("🔗 Connecting to Director Engine...")
    start_connector_thread()
    
    time.sleep(3) 
    
    if tts_available:
        ngrok_url = start_ngrok_tunnel()
        if ngrok_url:
            check_tunnel_security()
            atexit.register(stop_ngrok)
            if SECURITY_NOTIFICATIONS:
                print(f"🎉 Public Tunnel Ready: {ngrok_url}")
        else:
            print("⚠️ Ngrok tunnel failed (TTS functionality unaffected locally)")
    
    # 3. Initialize The Voice (Funnel)
    use_funnel = input_funnel_available
    input_funnel = None
    funnel_response_handler = None

    if use_funnel:
        print("🎙️ Initializing Voice Output System...")
        funnel_response_handler = FunnelResponseHandler(
            generation_func=text_to_speech_file if tts_available else None,
            playback_func=play_audio_file if tts_available else None
        )
        input_funnel = InputFunnel(
            bot_callback=ask_question,
            response_handler=funnel_response_handler.handle_response,
            min_prompt_interval=2
        )
        global_input_funnel = input_funnel
        
        # --- FIXED: Re-enabled the Priority System ---
        # This bridges the Input Handlers (Microphone/Twitch) to the Funnel
        print("🧠 Initializing Local Reflex (Priority System)...")
        init_priority_system(funnel_instance=input_funnel)
    else:
        # Fallback if funnel isn't available
        print("⚠️ Voice system unavailable. Initializing basic priority system.")
        init_priority_system(enable_bot_core=True)

    # 4. Initialize Twitch
    init_twitch_bot(funnel=input_funnel)

    print("\n✅ Nami is Online.")
    print("   - Brain: Running (Director)")
    print("   - Senses: Managed by Brain (Gemini Monitor)")
    print("   - Voice: Ready")
    print("   - Reflexes: Active")
    print("   - Twitch: Connected")
    print("   - Speech Lock: Enabled (Director waits for TTS)")

    try:
        console_input_loop()
    except KeyboardInterrupt:
        print("\nCtrl+C detected. Shutting down...")
    finally:
        print("Cleaning up...")
        if global_input_funnel:
            global_input_funnel.stop()
        shutdown_priority_system()
        stop_director_process()
        stop_ngrok()
        stop_connector()
        print("Shutdown complete.")

if __name__ == "__main__":
    main()