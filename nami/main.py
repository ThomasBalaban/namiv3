# Save as: nami/main.py
import uvicorn
import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles  # <--- Added Import
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

import sys
import threading
import os
import shutil
import subprocess
import time
import requests
import json
import re
import atexit
from pathlib import Path  # <--- Added Import

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
    notify_speech_started,
    notify_speech_finished
)

from nami.config import (
    NGROK_AUTH_ENABLED, 
    NGROK_AUTH_USERNAME, 
    NGROK_AUTH_PASSWORD,
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

# --- INTERJECTION SERVER ---
interjection_app = FastAPI()
INTERJECTION_PORT = 8000

# [FIX 1] Mount the audio_effects folder directly to Nami's server
# Try to find the folder in common locations
possible_paths = [
    Path("audio_effects"),                    # Root relative to execution
    Path(__file__).parent.parent / "audio_effects", # Root relative to file
    Path(__file__).parent / "audio_effects"   # Inside nami package
]

audio_effects_path = None
for path in possible_paths:
    if path.exists() and path.is_dir():
        audio_effects_path = path.resolve()
        break

if audio_effects_path:
    print(f"✅ Found audio effects directory at: {audio_effects_path}")
    interjection_app.mount("/audio_effects", StaticFiles(directory=str(audio_effects_path)), name="audio_effects")
else:
    print("⚠️ WARNING: Could not find 'audio_effects' folder. Sound effects will fail.")
    print(f"   Checked: {[str(p) for p in possible_paths]}")


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

def start_ngrok_tunnel():
    global ngrok_process
    print("\n🔍 --- NGROK DIAGNOSTICS ---")
    
    # 1. Check for existing tunnel first
    try:
        print("   Checking for existing ngrok tunnel on localhost:4040...")
        response = requests.get("http://localhost:4040/api/tunnels", timeout=1)
        tunnels = response.json()
        if tunnels.get("tunnels"):
            # Check if existing tunnel points to the right port (8000)
            tunnel = tunnels["tunnels"][0]
            if "8000" in tunnel.get("config", {}).get("addr", ""):
                public_url = tunnel["public_url"]
                print(f"✅ Found existing active tunnel to port 8000: {public_url}")
                return public_url
            else:
                print("   Found tunnel but wrong port. Ignoring.")
    except Exception:
        print("   No existing tunnel found. Starting new one...")

    # 2. Find the ngrok executable
    ngrok_path = shutil.which("ngrok")
    if not ngrok_path:
        common_paths = ["/opt/homebrew/bin/ngrok", "/usr/local/bin/ngrok"]
        for path in common_paths:
            if os.path.exists(path):
                ngrok_path = path
                break
    
    if not ngrok_path:
        print("❌ FATAL: 'ngrok' executable not found in PATH or common locations.")
        print("   Please install with: brew install ngrok")
        return None
        
    print(f"   Using ngrok at: {ngrok_path}")

    # 3. Start the process
    try:
        # [FIX 2] Point ngrok to port 8000 (Nami) instead of 8002 (Director)
        cmd = [ngrok_path, "http", str(INTERJECTION_PORT)]
        
        # Disabled auth for audio accessibility
        print("   ℹ️  Auth disabled for audio tunnel (Required for Azure TTS access)")
        
        if not NGROK_INSPECT:
            cmd.append("--inspect=false")
        
        cmd.append("--log=stdout")
        
        print(f"   Running: {' '.join(cmd)}")
        ngrok_process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        
        print("   ⏳ Waiting 5s for tunnel initialization...")
        time.sleep(5)
        
        if ngrok_process.poll() is not None:
            _out, err = ngrok_process.communicate()
            print(f"❌ Ngrok process died immediately!")
            print(f"   Error: {err.decode('utf-8')}")
            return None

        # 4. Fetch the URL
        print("   Fetching new tunnel URL...")
        for attempt in range(5):
            try:
                response = requests.get("http://localhost:4040/api/tunnels", timeout=2)
                tunnels = response.json()
                if tunnels.get("tunnels"):
                    public_url = tunnels["tunnels"][0]["public_url"]
                    print(f"✅ SUCCESS: Tunnel created at {public_url}")
                    return public_url
            except requests.exceptions.ConnectionError:
                pass
            print(f"   ...attempt {attempt+1}/5...")
            time.sleep(2)
        
        print("❌ Ngrok running but API unreachable.")
        return None
        
    except Exception as e:
        print(f"❌ Error starting ngrok: {e}")
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
        if not tunnels.get("tunnels"): return False
        tunnel = tunnels["tunnels"][0]
        url = tunnel["public_url"]
        if SECURITY_NOTIFICATIONS:
            print(f"   Tunnel Security Check: {'✅ HTTPS' if url.startswith('https') else '❌ HTTPS Missing'}")
        return True
    except: return False

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

        if self.generation_func and self.playback_func:
            try:
                notify_speech_started()
                audio_filename = self.generation_func(tts_version)
                if audio_filename:
                    def playback_with_notification(filename):
                        try:
                            self.playback_func(filename)
                        finally:
                            notify_speech_finished()
                    
                    playback_thread = threading.Thread(
                        target=playback_with_notification,
                        args=(audio_filename,),
                        daemon=True
                    )
                    playback_thread.start()
                else:
                    notify_speech_finished()
            except Exception as e:
                print(f"[TTS] Error processing TTS: {e}")
                notify_speech_finished()

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

def main():
    global global_input_funnel
    
    print("\n" + "="*60)
    print("🌊 NAMI V3 (The Body) - Starting Up...")
    print("="*60)

    print("🚀 Launching Director Engine...")
    if not start_director_process():
        print("CRITICAL ERROR: Director Engine failed to start. Exiting.")
        return
    
    start_interjection_server_thread()
    
    print("🔗 Connecting to Director Engine...")
    start_connector_thread()
    
    time.sleep(3) 
    
    if tts_available:
        ngrok_url = start_ngrok_tunnel()
        
        if ngrok_url:
            os.environ["NAMI_AUDIO_URL"] = f"{ngrok_url}/audio_effects"
            print(f"✅ NAMI_AUDIO_URL set to: {os.environ['NAMI_AUDIO_URL']}")
            check_tunnel_security()
            atexit.register(stop_ngrok)
        else:
            print("\n⚠️ WARNING: Ngrok tunnel FAILED.")
            print("   Sound effects (airhorn/bonk) will NOT work via Azure TTS.")

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
        
        print("🧠 Initializing Local Reflex (Priority System)...")
        init_priority_system(funnel_instance=input_funnel)
    else:
        print("⚠️ Voice system unavailable. Initializing basic priority system.")
        init_priority_system(enable_bot_core=True)

    init_twitch_bot(funnel=input_funnel)

    print("\n✅ Nami is Online.")
    
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