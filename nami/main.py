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
from nami.prompt_service_manager import start_prompt_service, stop_prompt_service
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
    
    source = payload.source_info.get('source', '')
    username = payload.source_info.get('username', '').lower()
    
    is_handler_interrupt = (
        (username == 'peepingotter' and 
         source in ['TWITCH_MENTION', 'DIRECT_MICROPHONE']) or
        payload.source_info.get('is_interrupt', False) or
        payload.source_info.get('is_direct_address', False)
    )
    
    # If Nami is busy, only allow handler interrupts
    if nami_is_busy.is_set() and not is_handler_interrupt:
        print(f"🔇 [Interject] Ignored - Nami is busy (source: {source})")
        return {"status": "ignored", "message": "Nami is currently talking or thinking."}
    
    # If handler is interrupting, clear the busy state
    if is_handler_interrupt and nami_is_busy.is_set():
        print(f"⚡ [Interject] HANDLER INTERRUPT from {source} (username: {username or 'mic'})!")
        nami_is_busy.clear()

    if global_input_funnel:
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

@interjection_app.post("/stop_audio")
async def stop_audio():
    """
    Emergency stop: kill Nami's current TTS playback immediately.
    Called by the Prompt Service when an interrupt arrives mid-speech.
    """
    try:
        import sounddevice as sd
        sd.stop()
        nami_is_busy.clear()
        print("🛑 [StopAudio] Audio playback killed by interrupt")
        return {"status": "stopped"}
    except Exception as e:
        print(f"⚠️ [StopAudio] Error stopping audio: {e}")
        return {"status": "error", "message": str(e)}

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
        """
        Processes the bot's response, handles filtering, updates the UI,
        sends to Twitch, and manages the TTS playback lifecycle.
        """
        if not response:
            print("⚠️ No response generated by bot. Releasing lock.")
            nami_is_busy.clear()
            from nami.input_systems.input_handlers import priority_system
            if priority_system:
                priority_system.set_state(ConversationState.IDLE)
            return
        
        # Process content through filters
        filtered_content = process_response_for_content(response)
        tts_version = filtered_content['tts_version']
        twitch_version = filtered_content['twitch_version']
        ui_version = filtered_content['ui_version']
        is_censored = filtered_content['is_censored']
        reason = filtered_content.get('censorship_reason')

        if is_censored:
            print(f"\n[BOT - CENSORED] Reason: {reason}")
            print(f"Sending to TTS: {tts_version}")
        else:
            print(f"\n[BOT] {tts_version}")
        
        # Send details to Director Engine
        send_bot_reply(
            reply_text=ui_version, 
            prompt_text=prompt_details or "", 
            is_censored=is_censored,
            censorship_reason=reason,
            filtered_area=filtered_content.get('filtered_area')
        )

        # Handle Twitch integration
        try:
            source = source_info.get('source')
            if source in ['TWITCH_MENTION', 'DIRECT_MICROPHONE'] or (source and source.startswith('DIRECTOR_')):
                username = source_info.get('username')
                if source == 'TWITCH_MENTION' and username:
                    twitch_response = f"@{username} {twitch_version}"
                else:
                    twitch_response = twitch_version
                send_to_twitch_sync(twitch_response)
        except Exception as e:
            print(f"Twitch sending failed: {e}")

        # Update local state to BUSY while processing/speaking
        from nami.input_systems.input_handlers import priority_system
        if priority_system:
            priority_system.set_state(ConversationState.BUSY)

        # Determine if this is a user-direct response or idle thought
        source = source_info.get('source', '')
        username = str(source_info.get('username', '')).lower()
        is_user_direct = (
            source in ['TWITCH_MENTION', 'DIRECT_MICROPHONE'] or 
            'peepingotter' in username or
            not source.startswith('DIRECTOR_')
        )
        speech_source = 'USER_DIRECT' if is_user_direct else 'IDLE_THOUGHT'
        
        print(f"🎯 [Response] Source: {source}, Username: {username}, Speech type: {speech_source}")

        # Handle TTS Generation and Playback
        if self.generation_func and self.playback_func:
            try:
                # Notify PROMPT SERVICE that Nami started speaking
                notify_speech_started(source=speech_source)
                
                print(f"🎵 [TTS] Generating audio...")
                audio_filename = self.generation_func(tts_version)
                
                if audio_filename:
                    def playback_with_notification(filename):
                        try:
                            print(f"🔊 [TTS] Starting playback...")
                            self.playback_func(filename)
                            print(f"🔊 [TTS] Playback ACTUALLY finished")
                        except Exception as e:
                            print(f"❌ [TTS] Playback error: {e}")
                        finally:
                            print(f"🔊 [TTS] Releasing speech lock...")
                            # Notify PROMPT SERVICE that Nami finished speaking
                            notify_speech_finished()
                            nami_is_busy.clear()
                            if priority_system:
                                priority_system.set_state(ConversationState.IDLE)
                    
                    playback_thread = threading.Thread(
                        target=playback_with_notification, 
                        args=(audio_filename,), 
                        daemon=True
                    )
                    playback_thread.start()
                else:
                    print("❌ TTS Generation failed. Cleaning up.")
                    nami_is_busy.clear()
                    notify_speech_finished()
                    if priority_system:
                        priority_system.set_state(ConversationState.IDLE)
            except Exception as e:
                print(f"Error in TTS lifecycle: {e}")
                nami_is_busy.clear()
                notify_speech_finished()
        else:
            nami_is_busy.clear()
            if priority_system:
                priority_system.set_state(ConversationState.IDLE)          
                                        
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
    
    print("\n" + "=" * 60)
    print("🌊 NAMI V3 (The Body) - Starting Up...")
    print("=" * 60)

    # === BOOT ORDER ===
    # 1. Director Engine (Brain) — port 8002
    if not start_director_process():
        return
    
    # 2. Interjection Server (Nami's intake) — port 8000
    #    Must be up before Prompt Service tries to POST to it
    start_interjection_server_thread()
    
    # 3. Prompt Service (The Mouth) — port 8001
    #    Gates speech, forwards approved interjections to port 8000
    prompt_service_ok = start_prompt_service()
    if not prompt_service_ok:
        print("⚠️ Prompt Service not running — speech will be ungated.")
        print("   Director interjections will go directly to Nami (legacy mode).")
    
    # 4. Socket.IO connector to Director
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

    print("\n" + "=" * 60)
    print("✅ Nami is Online.")
    print("   🧠 Brain (Director):    port 8002")
    print(f"   🎤 Mouth (Prompt Svc):  port 8001 {'✅' if prompt_service_ok else '❌ (offline)'}")
    print("   👂 Intake (Funnel):     port 8000")
    print("=" * 60)
    
    try:
        console_input_loop()
    except KeyboardInterrupt:
        pass
    finally:
        # === SHUTDOWN ORDER (reverse of boot) ===
        print("\n🛑 NAMI SHUTDOWN INITIATED")
        if global_input_funnel:
            global_input_funnel.stop()
        shutdown_priority_system()
        stop_connector()
        stop_prompt_service()
        stop_director_process()
        stop_ngrok()
        print("✅ NAMI SHUTDOWN COMPLETE")

if __name__ == "__main__":
    main()