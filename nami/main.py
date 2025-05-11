import signal
import threading
import os
from nami.bot_core import ask_question, BOTNAME
from nami.audio_utils.hearing_system import start_hearing_system, stop_hearing_system
from nami.vision_utils import start_vision_system, stop_vision_system
from nami.chat_interface import init_twitch_bot
from nami.input_systems import (
    init_priority_system,
    shutdown_priority_system, 
    process_console_command,
    process_hearing_line,
    process_vision_line
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

def signal_handler(sig, frame):
    """Handle clean shutdown on Ctrl+C"""
    print("\nShutting down...")
    try:
        if global_input_funnel:
            global_input_funnel.stop()
        stop_hearing_system()
        stop_vision_system()
        shutdown_priority_system()
        # Force exit after a delay if something hangs
        threading.Timer(2.0, lambda: os._exit(0)).start()
    except Exception as e:
        print(f"Error during shutdown: {e}")
        os._exit(0)

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

class PriorityVisionOutputReader:
    """Reading and processing vision output with priority system"""
    
    def __call__(self, process):
        for line in iter(process.stdout.readline, b''):
            line_str = line.decode('utf-8').rstrip()
            
            if not line_str.strip():
                continue
            
            # Process with priority system
            process_vision_line(line_str)
            
            # Format for display
            if line_str.strip().startswith(("[SUMMARY]", "[Summary]")):
                formatted = line_str.replace("[SUMMARY]", "[VISION SUMMARY] 👁️")
                formatted = formatted.replace("[Summary]", "[VISION SUMMARY] 👁️")
                print(f"\n{formatted}")
                print("You: ", end="", flush=True)
            elif any(x in line_str for x in ["Error", "Exception", "WARNING"]):
                print(f"\n[VISION ERROR] ⚠️ {line_str}")
                print("You: ", end="", flush=True)
            elif line_str.strip().startswith(("0.", "1.", "2.")):
                parts = line_str.split(":", 1)
                if len(parts) > 1:
                    time_part = parts[0].strip()
                    content_part = parts[1].strip()
                    formatted = f"[VISION] 👁️ ({time_part}): {content_part}"
                    print(f"\n{formatted}")
                    print("You: ", end="", flush=True)
            else:
                if len(line_str.strip()) > 0:
                    print(f"\n[VISION] 👁️ {line_str}")
                    print("You: ", end="", flush=True)

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
        
        # Handle TTS if needed
        if self.tts_function and source_info.get('use_tts', False):
            try:
                self.tts_function(response)
            except Exception as e:
                print(f"[TTS] Error: {e}")
        
        # Handle responses to Twitch
        source_type = source_info.get('source', '').upper()
        if source_type in ['TWITCH_MENTION', 'TWITCH_CHAT']:
            from nami.chat_interface import send_to_twitch_sync
            try:
                username = source_info.get('username', '')
                if username:
                    twitch_response = f"@{username} {response}"
                else:
                    twitch_response = response
                    
                send_to_twitch_sync(twitch_response)
            except Exception as e:
                print(f"[TWITCH] Error sending response: {e}")

def console_input_loop():
    """Run the console input loop with command handling"""
    print(f"{BOTNAME} is ready. Start chatting!")
    
    while True:
        try:
            command = input("You: ")
            if process_console_command(command):
                break
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")

def main():
    """Start the bot with integrated priority system."""
    global global_input_funnel
    
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    # Use the input funnel
    use_funnel = input_funnel_available
    
    # Initialize input funnel
    input_funnel = None
    funnel_response_handler = None
    
    if use_funnel:
        print("Initializing input funnel...")
        
        # Create the funnel response handler
        funnel_response_handler = FunnelResponseHandler(
            tts_function=speak_text if tts_available else None
        )
        
        # Create the input funnel with appropriate callback
        input_funnel = InputFunnel(
            bot_callback=ask_question,
            response_handler=funnel_response_handler.handle_response,
            min_prompt_interval=2.0
        )
        
        # Store the reference globally for clean shutdown
        global_input_funnel = input_funnel
    
    # Initialize priority system with input funnel
    priority_system = init_priority_system(
        llm_callback=ask_question,
        bot_name=BOTNAME,
        enable_bot_core=True,
        funnel_instance=input_funnel if use_funnel else None
    )
    
    # Set the input funnel in the input handlers if we're using it
    if use_funnel:
        from nami.input_systems.input_handlers import set_input_funnel, set_feature_flags
        set_input_funnel(input_funnel)
        
        # Enable all input sources
        set_feature_flags(desktop_audio=True, vision=True)
    
    # Start the hearing system
    start_hearing_system(
        debug_mode=False,
        output_reader=PriorityHearingOutputReader()
    )
    
    # Start the vision system
    start_vision_system(
        output_reader=PriorityVisionOutputReader()
    )
    
    # Start the Twitch chat bot
    if use_funnel:
        # When using funnel, the funnel handles Twitch responses
        init_twitch_bot()
    else:
        # With traditional approach, pass the response handler
        from nami.input_systems.response_handler import ResponseHandler
        response_handler = ResponseHandler(bot_name=BOTNAME)
        response_handler.set_llm_callback(ask_question)
        init_twitch_bot(handler=response_handler)

    print("System initialization complete, ready for input")
    
    try:
        # Start the main console interaction loop
        console_input_loop()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Clean up resources
        if global_input_funnel:
            global_input_funnel.stop()
        stop_hearing_system()
        stop_vision_system()
        shutdown_priority_system()
        print("Shutdown complete")

if __name__ == "__main__":
    main()