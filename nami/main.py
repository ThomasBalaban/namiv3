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
import time
import requests
from pathlib import Path

from nami.input_systems.priority_core import ConversationState
from nami.bot_core import ask_question, BOTNAME
from nami.input_systems import (
    init_priority_system,
    shutdown_priority_system,
    process_console_command,
)

from nami.tts_utils.content_filter import process_response_for_content
from nami.director_connector import (
    start_connector_thread,
    stop_connector,
    send_bot_reply,
)

try:
    from nami.input_funnel.input_funnel import InputFunnel
    input_funnel_available = True
except ImportError:
    input_funnel_available = False
    print("InputFunnel module not found, will use traditional priority system")

global_input_funnel = None

TTS_SERVICE_URL = "http://localhost:8004"

# Thread-safe event to prevent Nami from talking over herself
nami_is_busy = threading.Event()
nami_is_busy.clear()


# ── TTS Service helpers ────────────────────────────────────────────────────

def _tts_speak(text: str, source: str):
    """
    POST to the TTS service and block until playback is complete.
    Runs in its own daemon thread — clears nami_is_busy when done.
    """
    try:
        requests.post(
            f"{TTS_SERVICE_URL}/speak",
            json={"text": text, "source": source},
            timeout=120,   # long enough for slow TTS + lengthy responses
        )
    except Exception as e:
        print(f"⚠️  [Nami] TTS service call failed: {e}")
    finally:
        nami_is_busy.clear()
        from nami.input_systems.input_handlers import priority_system
        if priority_system:
            priority_system.set_state(ConversationState.IDLE)


def _tts_stop():
    """Tell the TTS service to kill current playback."""
    try:
        requests.post(f"{TTS_SERVICE_URL}/stop", timeout=3)
    except Exception as e:
        print(f"⚠️  [Nami] TTS stop failed: {e}")


def _tts_available() -> bool:
    try:
        r = requests.get(f"{TTS_SERVICE_URL}/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


# ── Interjection Server (port 8000) ───────────────────────────────────────

interjection_app = FastAPI()
INTERJECTION_PORT = 8000

possible_paths = [
    Path("audio_effects"),
    Path(__file__).parent.parent / "audio_effects",
    Path(__file__).parent / "audio_effects",
]
audio_effects_path = next((p.resolve() for p in possible_paths if p.exists() and p.is_dir()), None)
if audio_effects_path:
    print(f"✅ Found audio effects directory at: {audio_effects_path}")
    interjection_app.mount(
        "/audio_effects",
        StaticFiles(directory=str(audio_effects_path)),
        name="audio_effects",
    )


class InterjectionPayload(BaseModel):
    # The specific trigger/instruction from the brain
    # e.g. "Skill Issue Detected", "Dead Air", or the user's actual words
    content: str

    # The full structured context block fetched by the prompt service from
    # the director's /context endpoint. This contains visual summary, event
    # log, memories, directive, scene state, etc.
    # Empty string means the director was unreachable — Nami falls back to
    # her base personality.
    context: str = ""

    priority: float
    source_info: Dict[str, Any] = Field(default_factory=dict)


@interjection_app.post("/funnel/interject")
async def receive_interjection(payload: InterjectionPayload):
    global global_input_funnel

    source   = payload.source_info.get("source", "")
    username = payload.source_info.get("username", "").lower()

    is_handler_interrupt = (
        (username == "peepingotter" and source in ["TWITCH_MENTION", "DIRECT_MICROPHONE"])
        or payload.source_info.get("is_interrupt", False)
        or payload.source_info.get("is_direct_address", False)
    )

    if nami_is_busy.is_set() and not is_handler_interrupt:
        print(f"🔇 [Interject] Ignored - Nami is busy (source: {source})")
        return {"status": "ignored", "message": "Nami is currently talking or thinking."}

    if is_handler_interrupt and nami_is_busy.is_set():
        print(f"⚡ [Interject] HANDLER INTERRUPT from {source} (username: {username or 'mic'})!")
        _tts_stop()
        nami_is_busy.clear()

    if global_input_funnel:
        nami_is_busy.set()

        # --- CORE FIX ---
        # The prompt service already fetched the full structured context from
        # the director and put it in payload.context.
        # We combine it with payload.content (the trigger instruction) so that
        # generate_response() receives a fully-formed prompt and skips its own
        # director fetch (which was hitting /breadcrumbs and getting the wrong format).
        #
        # Format matches what generate_response() expects when context is pre-built:
        #   <full context block>
        #   USER INPUT: <trigger instruction>
        #
        # If context is empty (director was unreachable), we fall through to just
        # the content — generate_response() will then attempt its own fetch as a
        # secondary fallback.
        if payload.context and len(payload.context.strip()) > 20:
            combined_content = f"{payload.context}\n\nUSER INPUT: {payload.content}"
            print(f"✅ [Interject] Using pre-built context ({len(payload.context)} chars) + trigger")
        else:
            combined_content = payload.content
            print(f"⚠️ [Interject] No context from prompt service — using trigger only: {payload.content[:60]}...")

        print(f"✅ Accepted command from Director: {payload.content[:50]}...")
        global_input_funnel.add_input(
            content=combined_content,
            priority=payload.priority,
            source_info=payload.source_info,
        )
        return {"status": "success", "message": "Command received."}

    return {"status": "error", "message": "Nami funnel not ready."}


@interjection_app.post("/stop_audio")
async def stop_audio():
    """
    Called by the Prompt Service to interrupt mid-speech.
    Proxies to the TTS service and clears Nami's busy state.
    """
    _tts_stop()
    nami_is_busy.clear()
    print("🛑 [Nami] stop_audio received — forwarded to TTS service")
    return {"status": "stopped"}


def _run_interjection_server():
    uvicorn.run(interjection_app, host="0.0.0.0", port=INTERJECTION_PORT, log_level="warning")


def _start_interjection_server():
    threading.Thread(target=_run_interjection_server, daemon=True, name="InterjectionServer").start()


# ── Response handler ───────────────────────────────────────────────────────

class FunnelResponseHandler:
    def handle_response(self, response: Optional[str], prompt_details: Optional[str], source_info: dict):
        """
        Filter → Director UI → Twitch → TTS (async thread).
        """
        if not response:
            print("⚠️ No response generated. Releasing lock.")
            nami_is_busy.clear()
            from nami.input_systems.input_handlers import priority_system
            if priority_system:
                priority_system.set_state(ConversationState.IDLE)
            return

        # Content filter
        filtered = process_response_for_content(response)
        tts_version    = filtered["tts_version"]
        twitch_version = filtered["twitch_version"]
        ui_version     = filtered["ui_version"]
        is_censored    = filtered["is_censored"]
        reason         = filtered.get("censorship_reason")

        if is_censored:
            print(f"\n[BOT - CENSORED] Reason: {reason}")
        else:
            print(f"\n[BOT] {tts_version}")

        # Send to Director UI
        send_bot_reply(
            reply_text=ui_version,
            prompt_text=prompt_details or "",
            is_censored=is_censored,
            censorship_reason=reason,
            filtered_area=filtered.get("filtered_area"),
        )

        # Update state to BUSY while TTS is running
        from nami.input_systems.input_handlers import priority_system
        if priority_system:
            priority_system.set_state(ConversationState.BUSY)

        # Determine speech type for Prompt Service gating
        source   = source_info.get("source", "")
        username = str(source_info.get("username", "")).lower()
        is_user_direct = (
            source in ["TWITCH_MENTION", "DIRECT_MICROPHONE"]
            or "peepingotter" in username
            or not source.startswith("DIRECTOR_")
        )
        speech_source = "USER_DIRECT" if is_user_direct else "IDLE_THOUGHT"

        if _tts_available():
            threading.Thread(
                target=_tts_speak,
                args=(tts_version, speech_source),
                daemon=True,
                name="TTSCall",
            ).start()
        else:
            print("⚠️  TTS service unavailable — skipping audio")
            nami_is_busy.clear()
            if priority_system:
                priority_system.set_state(ConversationState.IDLE)


# ── Console ────────────────────────────────────────────────────────────────

def console_input_loop():
    print(f"{BOTNAME} is ready. (type 'exit' to quit)")
    while True:
        try:
            command = input("You: ")
            if process_console_command(command):
                break
        except Exception:
            break


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    global global_input_funnel

    print("\n" + "=" * 60)
    print("🌊 NAMI — Starting Up...")
    print("=" * 60)

    # 1. Interjection server — port 8000 (launcher health-checks this)
    _start_interjection_server()

    # 2. Socket.IO connector to Director Engine
    start_connector_thread()
    time.sleep(2)

    # 3. Input funnel + priority system
    if input_funnel_available:
        handler      = FunnelResponseHandler()
        input_funnel = InputFunnel(
            bot_callback=ask_question,
            response_handler=handler.handle_response,
            min_prompt_interval=2,
        )
        global_input_funnel = input_funnel
        init_priority_system(funnel_instance=input_funnel)
    else:
        init_priority_system(enable_bot_core=True)

    try:
        console_input_loop()
    except KeyboardInterrupt:
        pass
    finally:
        print("\n🛑 NAMI SHUTDOWN INITIATED")
        if global_input_funnel:
            global_input_funnel.stop()
        shutdown_priority_system()
        stop_connector()
        print("✅ NAMI SHUTDOWN COMPLETE")


if __name__ == "__main__":
    main()