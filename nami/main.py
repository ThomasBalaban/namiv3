# nami/main.py

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

# Import the input funnel
try:
    from nami.input_funnel.input_funnel import InputFunnel
    input_funnel_available = True
except ImportError:
    input_funnel_available = False
    print("InputFunnel module not found, will use traditional priority system")

# Try to import TTS if available
try:
    from nami.tts_utils.speaker import speak_text
    tts_available = True
except ImportError:
    tts_available = False
    speak_text = None

# Global references for clean shutdown
global_input_funnel = None

class PriorityHearingOutputReader:
    """Reading and processing hearing output with priority system"""

    def __call__(self, process):
        for line in iter(process.stdout.readline, b''):
            line_str = line.decode('utf-8').rstrip()

            if ("[Microphone Input]" in line_str or
                ("]" in line_str and any(x in line_str for x in ["SPEECH", "MUSIC"]))):

                if "[Microphone Input]" in line_str:
                    formatted = line_str.replace("[Microphone Input]", "[HEARING] 🎤")
                else:
                    formatted = line_str.replace("[", "[HEARING] 🔊 [", 1)

                print(f"\n{formatted}")
                print("You: ", end="", flush=True)

                # Process with priority system
                process_hearing_line(line_str)
            elif any(x in line_str for x in ["Loading", "Starting", "Initializing", "Error", "Vosk"]):
                print(f"[Hearing] {line_str}")

class FunnelResponseHandler:
    """Handler for funnel responses (including TTS)"""

    def __init__(self, tts_function=None):
        self.tts_function = tts_function

    def handle_response(self, response, source_info):
        if not response:
            print("Empty response received")
            return

        print(f"\n[BOT] {response}")
        print("You: ", end="", flush=True)
        
        # --- MODIFIED LOGIC ---
        # By default, we will now attempt to send every generated response to Twitch.
        # This makes her feel more present in the chat.
        try:
            # The username is only available for direct mentions, so we handle its absence.
            username = source_info.get('username')
            twitch_response = f"@{username} {response}" if username else response
            send_to_twitch_sync(twitch_response)
        except Exception as e:
            print(f"[TWITCH] Error sending response: {e}")

        # Handle TTS if needed (this logic remains the same)
        if self.tts_function and source_info.get('use_tts', False):
            try:
                self.tts_function(response)
            except Exception as e:
                print(f"[TTS] Error: {e}")

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
            break # Exit loop on error

def main():
    """Start the bot with integrated priority system."""
    global global_input_funnel

    # Use the input funnel
    use_funnel = input_funnel_available

    # Initialize input funnel
    input_funnel = None
    funnel_response_handler = None

    if use_funnel:
        print("Initializing input funnel...")
        funnel_response_handler = FunnelResponseHandler(
            tts_function=speak_text if tts_available else None
        )
        input_funnel = InputFunnel(
            bot_callback=ask_question,
            response_handler=funnel_response_handler.handle_response,
            min_prompt_interval=2.0
        )
        global_input_funnel = input_funnel

    # Initialize priority system with input funnel
    priority_system = init_priority_system(
        llm_callback=ask_question,
        bot_name=BOTNAME,
        enable_bot_core=True,
        funnel_instance=input_funnel if use_funnel else None
    )

    if use_funnel:
        from nami.input_systems.input_handlers import set_input_funnel
        set_input_funnel(input_funnel)
        print("NOTICE: Desktop audio and vision inputs are DISABLED by default")

    # Start system components
    start_hearing_system(debug_mode=False, output_reader=PriorityHearingOutputReader())
    start_vision_client()

    # --- UPDATED SECTION ---
    # Start the Twitch chat bot
    if use_funnel:
        # When using funnel, pass the funnel instance to the twitch initializer
        init_twitch_bot(funnel=input_funnel)
    else:
        # With traditional approach, pass the response handler
        from nami.input_systems.response_handler import ResponseHandler
        response_handler = ResponseHandler(bot_name=BOTNAME)
        response_handler.set_llm_callback(ask_question)
        init_twitch_bot(handler=response_handler)
    # --- END UPDATED SECTION ---

    print("System initialization complete, ready for input")

    try:
        # Start the main console interaction loop
        console_input_loop()
    except KeyboardInterrupt:
        # This will now correctly catch Ctrl+C and begin shutdown
        print("\nCtrl+C detected. Shutting down gracefully...")
    finally:
        # This block will run after the loop exits, either normally or via Ctrl+C
        print("Cleaning up resources...")
        if global_input_funnel:
            global_input_funnel.stop()
        stop_hearing_system()
        shutdown_priority_system()
        print("Shutdown complete.")

if __name__ == "__main__":
    main()