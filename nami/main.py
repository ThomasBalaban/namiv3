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
from nami.audio_utils.hearing_system import start_hearing_system, stop_hearing_system
from nami.vision_client import start_vision_client
from nami.twitch_integration import init_twitch_bot, send_to_twitch_sync
from nami.input_systems import (
    init_priority_system,
    shutdown_priority_system,
    process_console_command,
    process_hearing_line,
)
from nami.vision_process_manager import start_vision_process, stop_vision_process
from nami.tts_utils.content_filter import process_response_for_content
from nami.audio_process_manager import start_audio_mon_process, stop_audio_mon_process
from nami.director_process_manager import start_director_process, stop_director_process
# --- MODIFIED: Import send_bot_reply ---
from nami.director_connector import start_connector_thread, stop_connector, send_bot_reply

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
        cmd = ["ngrok", "http", "8002"] # Points to Director Engine
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

def hearing_line_processor(line_str):
    if ("[Microphone Input]" in line_str or
        ("]" in line_str and any(x in line_str for x in ["SPEECH", "MUSIC"]))):
        if "[Microphone Input]" in line_str:
            formatted = line_str.replace("[Microphone Input]", "[HEARING] 🎤")
        else:
            formatted = line_str.replace("[", "[HEARING] 🔊 [", 1)
        print(f"\n{formatted}")
        print("You: ", end="", flush=True)
        process_hearing_line(line_str)
    elif any(x in line_str for x in ["Loading", "Starting", "Initializing", "Error", "Vosk"]):
        print(f"[Hearing] {line_str}")

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
        is_censored = filtered_content['is_censored']

        if is_censored:
            print(f"\n[BOT - CENSORED] Original: {response[:50]}...")
            print(f"[BOT - CENSORED] Sending: {tts_version}")
        else:
            print(f"\n[BOT] {tts_version}")
        print("You: ", end="", flush=True)

        # --- MODIFIED: Send to Director UI via Connector ---
        send_bot_reply(tts_version, prompt_details or "", is_censored)

        try:
            source = source_info.get('source')
            if source in ['TWITCH_MENTION', 'DIRECT_MICROPHONE'] or source.startswith('DIRECTOR_'):
                username = source_info.get('username')
                if source == 'TWITCH_MENTION' and username:
                    twitch_response = f"@{username} {twitch_version}"
                else:
                    twitch_response = twitch_version
                send_to_twitch_sync(twitch_response)
        except Exception as e:
            print(f"[TWITCH] Error sending response: {e}")

        if self.generation_func and self.playback_func and source_info.get('use_tts', False):
            try:
                audio_filename = self.generation_func(tts_version)
                if audio_filename:
                    playback_thread = threading.Thread(
                        target=self.playback_func,
                        args=(audio_filename,),
                        daemon=True
                    )
                    playback_thread.start()
            except Exception as e:
                print(f"[TTS] Error processing TTS: {e}")

def console_input_loop():
    print(f"{BOTNAME} is ready. Start chatting!")
    while True:
        try:
            command = input("You: ")
            if process_console_command(command):
                break
        except Exception as e:
            print(f"Error in console loop: {e}")
            break

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
        print(f"✅ Received Tier 2 Interjection from Director: {payload.content[:50]}...")
        global_input_funnel.add_input(
            content=payload.content,
            priority=payload.priority,
            source_info=payload.source_info
        )
        return {"status": "success", "message": "Interjection added to funnel."}
    else:
        print("❌ Received interjection, but no funnel is active.")
        return {"status": "error", "message": "Input funnel not available."}

def run_interjection_server():
    print(f"Starting Interjection server on http://0.0.0.0:{INTERJECTION_PORT}...")
    uvicorn.run(interjection_app, host="0.0.0.0", port=INTERJECTION_PORT, log_level="warning")

def start_interjection_server_thread():
    server_thread = threading.Thread(target=run_interjection_server, daemon=True, name="InterjectionServer")
    server_thread.start()
    print("Interjection server thread started.")

def main():
    global global_input_funnel
    
    print("\n" + "="*60)
    print("Starting Director Engine (Brain 1)...")
    print("="*60)
    if not start_director_process():
        print("CRITICAL ERROR: Director Engine (Brain 1) failed to start. Exiting.")
        return
    
    print("\n" + "="*60)
    print("Starting audio_mon process...")
    print("="*60)
    if not start_audio_mon_process():
        print("⚠️ Warning: audio_mon failed to start")
        time.sleep(2)

    start_vision_process()
    start_interjection_server_thread()
    
    print("\n" + "="*60)
    print("Starting Director Connector (Brain 2 -> Brain 1)...")
    print("="*60)
    start_connector_thread()
    
    time.sleep(3) 
    
    if tts_available:
        ngrok_url = start_ngrok_tunnel()
        if ngrok_url:
            check_tunnel_security()
            atexit.register(stop_ngrok)
            if SECURITY_NOTIFICATIONS:
                print(f"\n🎉 Secure audio server is ready! URL: {ngrok_url}")
        else:
            print("⚠️ Sound effects will use fallback text (ngrok not available)")
    
    print("\nLog redirection to UI is disabled (UI is now in Director Engine).")

    use_funnel = input_funnel_available
    input_funnel = None
    funnel_response_handler = None

    if use_funnel:
        print("Initializing input funnel...")
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

    init_priority_system(
        llm_callback=ask_question,
        bot_name=BOTNAME,
        enable_bot_core=True,
        funnel_instance=input_funnel if use_funnel else None
    )

    if use_funnel:
        from nami.input_systems.input_handlers import set_input_funnel
        set_input_funnel(input_funnel)
        print("NOTICE: Desktop audio and vision inputs are now context-only (sent to Director).")

    start_hearing_system(callback=hearing_line_processor)
    start_vision_client()
    init_twitch_bot(funnel=input_funnel)

    print("System initialization complete, ready for input")

    try:
        console_input_loop()
    except KeyboardInterrupt:
        print("\nCtrl+C detected. Shutting down gracefully...")
    finally:
        print("Cleaning up resources...")
        if global_input_funnel:
            global_input_funnel.stop()
        stop_hearing_system()
        shutdown_priority_system()
        stop_vision_process()
        stop_audio_mon_process()
        stop_director_process()
        stop_ngrok()
        stop_connector()
        print("Shutdown complete.")

if __name__ == "__main__":
    main()