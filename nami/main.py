import sys
import threading
import os
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
from nami.ui import start_ui_server, emit_log, emit_bot_reply
from nami.vision_process_manager import start_vision_process, stop_vision_process
from nami.tts_utils.sfx_player import play_sound_effect_threaded
import traceback

# --- UI Log Redirection ---
_is_logging = threading.local()

class LogRedirector:
    """Redirects stdout/stderr to the UI log panel."""
    def __init__(self, original_stream, level):
        self.original_stream = original_stream
        self.level = level

    def write(self, message):
        if getattr(_is_logging, 'active', False):
            self.original_stream.write(message)
            return

        try:
            _is_logging.active = True
            self.original_stream.write(message)
            if message.strip():
                emit_log(self.level, message.strip())
        finally:
            _is_logging.active = False

    def flush(self):
        self.original_stream.flush()

# Import the input funnel
try:
    from nami.input_funnel.input_funnel import InputFunnel
    input_funnel_available = True
except ImportError:
    input_funnel_available = False
    print("InputFunnel module not found, will use traditional priority system")

# --- MODIFIED: Import TTS components separately ---
try:
    from nami.tts_utils.tts_engine import text_to_speech_file
    from nami.tts_utils.audio_player import play_audio_file
    tts_available = True
except ImportError:
    tts_available = False
    text_to_speech_file = None
    play_audio_file = None

# Global references for clean shutdown
global_input_funnel = None

def hearing_line_processor(line_str):
    """Processes a single line of text from the hearing system."""
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
    """Handler for funnel responses (including TTS and UI updates)"""
    def __init__(self, generation_func=None, playback_func=None):
        self.generation_func = generation_func
        self.playback_func = playback_func

    def handle_response(self, response_tuple, prompt_details, source_info):
        response_text, prompt_details_text, tool_call = response_tuple

        if not response_text and not tool_call:
            print("Empty response received")
            return

        print(f"\n[BOT] {response_text}")
        print("You: ", end="", flush=True)

        emit_bot_reply(response_text, prompt_details_text)

        if tool_call:
            tool_name = tool_call['tool']
            tool_args = tool_call['args']

            if tool_name == 'play_sound_effect':
                play_sound_effect_threaded(**tool_args)

        try:
            source = source_info.get('source')
            if source in ['TWITCH_MENTION', 'DIRECT_MICROPHONE']:
                username = source_info.get('username')
                if source == 'TWITCH_MENTION' and username:
                    twitch_response = f"@{username} {response_text}"
                else:
                    twitch_response = response_text
                send_to_twitch_sync(twitch_response)
        except Exception as e:
            print(f"[TWITCH] Error sending response: {e}")

        if self.generation_func and self.playback_func and source_info.get('use_tts', False):
            try:
                audio_filename = self.generation_func(response_text)
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
    """Run the console input loop with command handling"""
    print(f"{BOTNAME} is ready. Start chatting!")
    while True:
        try:
            command = input("You: ")
            if process_console_command(command):
                break
        except Exception as e:
            print(f"Error in console loop: {e}")
            break


def main():
    """Start the bot with integrated priority system."""
    global global_input_funnel

    print("Starting Nami systems...")
    try:
        start_vision_process()
        print("Vision process started.")
        start_ui_server()
        print("UI server started.")
        sys.stdout = LogRedirector(sys.stdout, 'INFO')
        sys.stderr = LogRedirector(sys.stderr, 'ERROR')
        print("Logging redirected.")

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
        print("Priority system initialized.")

        if use_funnel:
            from nami.input_systems.input_handlers import set_input_funnel
            set_input_funnel(input_funnel)
            print("NOTICE: Desktop audio and vision inputs are now context-only by default")

        start_hearing_system(callback=hearing_line_processor)
        print("Hearing system started.")
        start_vision_client()
        print("Vision client started.")
        init_twitch_bot(funnel=input_funnel)
        print("Twitch bot initialized.")

        print("System initialization complete, ready for input")

        console_input_loop()

    except Exception as e:
        print("\n" + "="*20 + " CRITICAL STARTUP ERROR " + "="*20)
        print("An error occurred during system initialization. The program will now exit.")
        print(f"Error: {e}")
        traceback.print_exc()
        print("="*64)
    finally:
        print("Cleaning up resources...")
        if global_input_funnel:
            global_input_funnel.stop()
        stop_hearing_system()
        shutdown_priority_system()
        stop_vision_process()
        print("Shutdown complete.")


if __name__ == "__main__":
    main()