# Save as: nami/main.py
import uvicorn
import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
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
from pathlib import Path

from nami.input_systems.priority_core import ConversationState
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

# Thread-safe event to prevent Nami from talking over herself
nami_is_busy = threading.Event()
nami_is_busy.clear()

# --- INTERJECTION SERVER ---
interjection_app = FastAPI()
INTERJECTION_PORT = 8000

possible_paths = [
    Path("audio_effects"),
    Path(__file__).parent.parent / "audio_effects",
    Path(__file__).parent / "audio_effects"
]

audio_effects_path = None
for path in possible_paths:
    if path.exists() and path.is_dir():
        audio_effects_path = path.resolve()
        break

if audio_effects_path:
    print(f"✅ Found audio effects directory at: {audio_effects_path}")
    interjection_app.mount("/audio_effects", StaticFiles(directory=str(audio_effects_path)), name="audio_effects")


class InterjectionPayload(BaseModel):
    content: str
    priority: float
    source_info: Dict[str, Any] = Field(default_factory=dict)

@interjection_app.post("/funnel/interject")
async def receive_interjection(payload: InterjectionPayload):
    global global_input_funnel
    
    # [FIX] Strict gating: If busy, ignore everything. No whitelist.
    if nami_is_busy.is_set():
        return {"status": "ignored", "message": "Nami is currently talking or thinking."}

    if global_input_funnel:
        # Lock the system immediately to prevent overlapping commands
        nami_is_busy.set()
        print(f"✅ Accepted Command from Director: {payload.content[:50]}...")
        global_input_funnel.add_input(
            content=payload.content,
            priority=payload.priority,
            source_info=payload.source_info
        )
        return {"status": "success", "message": "Command received."}
    else:
        return {"status": "error", "message": "Nami funnel not ready."}

def run_interjection_server():
    uvicorn.run(interjection_app, host="0.0.0.0", port=INTERJECTION_PORT, log_level="warning")

def start_interjection_server_thread():
    server_thread = threading.Thread(target=run_interjection_server, daemon=True, name="InterjectionServer")
    server_thread.start()

def start_ngrok_tunnel():
    global ngrok_process
    try:
        response = requests.get("http://localhost:4040/api/tunnels", timeout=1)
        tunnels = response.json()
        if tunnels.get("tunnels"):
            tunnel = tunnels["tunnels"][0]
            if "8000" in tunnel.get("config", {}).get("addr", ""):
                return tunnel["public_url"]
    except:
        pass

    ngrok_path = shutil.which("ngrok")
    if not ngrok_path:
        return None
        
    try:
        cmd = [ngrok_path, "http", str(INTERJECTION_PORT)]
        if not NGROK_INSPECT:
            cmd.append("--inspect=false")
        cmd.append("--log=stdout")
        
        ngrok_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(5)
        
        for attempt in range(5):
            try:
                response = requests.get("http://localhost:4040/api/tunnels", timeout=2)
                tunnels = response.json()
                if tunnels.get("tunnels"):
                    return tunnels["tunnels"][0]["public_url"]
            except:
                pass
            time.sleep(2)
        return None
    except:
        return None

def stop_ngrok():
    global ngrok_process
    if ngrok_process:
        ngrok_process.terminate()
        try: ngrok_process.wait(timeout=5)
        except subprocess.TimeoutExpired: ngrok_process.kill()
        ngrok_process = None

class FunnelResponseHandler:
    def __init__(self, generation_func=None, playback_func=None):
        self.generation_func = generation_func
        self.playback_func = playback_func

    def handle_response(self, response, prompt_details, source_info):
        if not response:
            nami_is_busy.clear() # Unlock if no response generated
            return
        
        filtered_content = process_response_for_content(response)
        tts_version = filtered_content['tts_version']
        twitch_version = filtered_content['twitch_version']
        ui_version = filtered_content['ui_version']
        is_censored = filtered_content['is_censored']

        if is_censored:
            print(f"\n[BOT - CENSORED] Sending: {tts_version}")
        else:
            print(f"\n[BOT] {tts_version}")
        
        send_bot_reply(ui_version, prompt_details or "", is_censored)

        try:
            source = source_info.get('source')
            if source in ['TWITCH_MENTION', 'DIRECT_MICROPHONE'] or (source and source.startswith('DIRECTOR_')):
                username = source_info.get('username')
                if source == 'TWITCH_MENTION' and username:
                    twitch_response = f"@{username} {twitch_version}"
                else:
                    twitch_response = twitch_version
                send_to_twitch_sync(twitch_response)
        except:
            pass

        # Update Local Priority System state to BUSY
        from nami.input_systems.input_handlers import priority_system
        if priority_system:
            priority_system.set_state(ConversationState.BUSY)

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
                            # [FIX] Final unlock occurs only after playback ends
                            nami_is_busy.clear()
                            if priority_system:
                                priority_system.set_state(ConversationState.IDLE)
                    
                    threading.Thread(target=playback_with_notification, args=(audio_filename,), daemon=True).start()
                else:
                    nami_is_busy.clear()
                    notify_speech_finished()
            except Exception:
                nami_is_busy.clear()
                notify_speech_finished()
        else:
            # If no audio system, unlock immediately after UI update
            nami_is_busy.clear()

def console_input_loop():
    print(f"{BOTNAME} is ready.")
    while True:
        try:
            command = input("You: ")
            if process_console_command(command):
                break
        except Exception:
            break

def main():
    global global_input_funnel
    
    print("\n" + "="*60)
    print("🌊 NAMI V3 (The Body) - Starting Up...")
    print("="*60)

    if not start_director_process():
        return
    
    start_interjection_server_thread()
    start_connector_thread()
    time.sleep(3) 
    
    if tts_available:
        ngrok_url = start_ngrok_tunnel()
        if ngrok_url:
            os.environ["NAMI_AUDIO_URL"] = f"{ngrok_url}/audio_effects"
            atexit.register(stop_ngrok)

    use_funnel = input_funnel_available
    if use_funnel:
        funnel_handler = FunnelResponseHandler(
            generation_func=text_to_speech_file if tts_available else None,
            playback_func=play_audio_file if tts_available else None
        )
        input_funnel = InputFunnel(
            bot_callback=ask_question,
            response_handler=funnel_handler.handle_response,
            min_prompt_interval=2
        )
        global_input_funnel = input_funnel
        init_priority_system(funnel_instance=input_funnel)
    else:
        init_priority_system(enable_bot_core=True)

    init_twitch_bot(funnel=global_input_funnel)

    print("\n✅ Nami is Online.")
    
    try:
        console_input_loop()
    except KeyboardInterrupt:
        pass
    finally:
        if global_input_funnel:
            global_input_funnel.stop()
        shutdown_priority_system()
        stop_director_process()
        stop_ngrok()
        stop_connector()

if __name__ == "__main__":
    main()