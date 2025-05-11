import argparse
import signal
import threading
import os
import time
from nami.bot_core import ask_question, BOTNAME
from nami.audio_utils.hearing_system import start_hearing_system, stop_hearing_system
from nami.vision_utils import start_vision_system, stop_vision_system
from nami.chat_interface import init_twitch_bot
from nami.config import TARGET_CHANNEL
from nami.input_systems.response_handler import ResponseHandler

# Import priority system components from the input_systems folder
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
    print("TTS module not found, voice responses disabled")

# Global references to key components for clean shutdown
global_input_funnel = None

def signal_handler(sig, frame):
    """Handle clean shutdown on Ctrl+C"""
    print("\nShutting down...")
    try:
        # Try graceful shutdown first
        global global_input_funnel
        if global_input_funnel:
            print("Stopping input funnel...")
            global_input_funnel.stop()
            
        print("Stopping hearing system...")
        stop_hearing_system()
        
        print("Stopping vision system...")
        stop_vision_system()
        
        print("Stopping priority system...")
        shutdown_priority_system()
        
        # Force exit after a delay if something hangs
        print("Scheduling forced exit in 4 seconds...")
        threading.Timer(4.0, lambda: os._exit(0)).start()
    except Exception as e:
        print(f"Error during shutdown: {e}")
        # If anything fails, force exit immediately
        os._exit(0)

class PriorityHearingOutputReader:
    """Reading and processing hearing output with priority system"""
    
    def __call__(self, process):
        """Read and process output from the hearing process"""
        for line in iter(process.stdout.readline, b''):
            # Decode the line
            line_str = line.decode('utf-8').rstrip()
            
            # Check if it's a transcription line
            if ("[Microphone Input]" in line_str or 
                ("]" in line_str and any(x in line_str for x in ["SPEECH", "MUSIC"]))):
                
                # Format based on source
                if "[Microphone Input]" in line_str:
                    formatted = line_str.replace("[Microphone Input]", "[HEARING] 🎤")
                else:
                    formatted = line_str.replace("[", "[HEARING] 🔊 [", 1)
                
                # Print formatted transcript with clear separation
                print(f"\n{formatted}")
                print("You: ", end="", flush=True)
                
                # Process with priority system
                process_hearing_line(line_str)
            
            # Print other important output lines (like startup messages)
            elif any(x in line_str for x in ["Loading", "Starting", "Initializing", "Error", "Vosk"]):
                print(f"[Hearing] {line_str}")

class PriorityVisionOutputReader:
    """Reading and processing vision output with priority system"""
    
    def __call__(self, process):
        """Read and process output from the vision process"""
        for line in iter(process.stdout.readline, b''):
            # Decode the line
            line_str = line.decode('utf-8').rstrip()
            
            # Skip empty lines
            if not line_str.strip():
                continue
            
            # Process with priority system
            process_vision_line(line_str)
            
            # Format for display
            if line_str.strip().startswith(("[SUMMARY]", "[Summary]")):
                # Format summary line - don't truncate!
                formatted = line_str.replace("[SUMMARY]", "[VISION SUMMARY] 👁️")
                formatted = formatted.replace("[Summary]", "[VISION SUMMARY] 👁️")
                print(f"\n{formatted}")
                print("You: ", end="", flush=True)
            elif any(x in line_str for x in ["Error", "Exception", "WARNING"]):
                # Print error messages
                print(f"\n[VISION ERROR] ⚠️ {line_str}")
                print("You: ", end="", flush=True)
            elif line_str.strip().startswith(("0.", "1.", "2.")):
                # Analysis line with time prefix
                parts = line_str.split(":", 1)
                if len(parts) > 1:
                    time_part = parts[0].strip()
                    content_part = parts[1].strip()
                    formatted = f"[VISION] 👁️ ({time_part}): {content_part}"
                    print(f"\n{formatted}")
                    print("You: ", end="", flush=True)
            else:
                # Any other analysis output
                if len(line_str.strip()) > 0:  # Skip truly empty lines
                    print(f"\n[VISION] 👁️ {line_str}")
                    print("You: ", end="", flush=True)

# ====== FUNNEL RESPONSE HANDLER ======
class FunnelResponseHandler:
    """Handler for funnel responses (including TTS)"""
    
    def __init__(self, tts_function=None):
        self.tts_function = tts_function
    
    def handle_response(self, response, source_info):
        """Process a response from the bot via the funnel"""
        if not response:
            print("Empty response received")
            return
            
        # Format and display the response
        print(f"\n[BOT] {response}")
        print("You: ", end="", flush=True)
        
        # Handle TTS if needed
        if self.tts_function and source_info.get('use_tts', False):
            try:
                self.tts_function(response)
                print("[TTS] Response spoken")
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
                print(f"[TWITCH] Response sent")
            except Exception as e:
                print(f"[TWITCH] Error sending response: {e}")

# ====== CONSOLE INPUT LOOP ======
def console_input_loop():
    """Run the console input loop with command handling"""
    print(f"MAIN.PY: {BOTNAME} is ready. Start chatting!")
    
    while True:
        try:
            command = input("You: ")
            if command.lower() == "test_bot_core":
                # Test using bot_core directly
                response = ask_question("This is a test from console. Can you respond?")
                print(f"Bot core test response: {response}")
                continue
                
            if process_console_command(command):
                break
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")

def main():
    """
    Start the bot with integrated priority system.
    """
    global global_input_funnel
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Bot with Hearing and Vision Systems")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode for transcription")
    parser.add_argument("--no-vision", action="store_true", help="Disable vision system")
    parser.add_argument("--no-hearing", action="store_true", help="Disable hearing system")
    parser.add_argument("--no-twitch", action="store_true", help="Disable Twitch chat integration")
    parser.add_argument("--no-priority", action="store_true", help="Disable priority system")
    parser.add_argument("--no-funnel", action="store_true", help="Disable input funnel")
    parser.add_argument("--no-bot-core", action="store_true", help="Disable using bot_core for responses")
    parser.add_argument("--funnel-interval", type=float, default=2.0, help="Set funnel processing interval (seconds)")
    parser.add_argument("--enable-vision-inputs", action="store_true", help="Enable vision inputs to the AI")
    parser.add_argument("--enable-desktop-audio", action="store_true", help="Enable desktop audio inputs to the AI")
    # Keep the old flags for backward compatibility
    parser.add_argument("--twitch-responses", action="store_true", help="[Deprecated] Use --use-bot-core instead")
    parser.add_argument("--use-bot-core", action="store_true", help="[Deprecated] Bot core is used by default now")
    args = parser.parse_args()

    # Print just the command line flag first
    print(f"Status check - Using bot_core: {not args.no_bot_core}")
    
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    # Determine if we should use the funnel
    use_funnel = input_funnel_available and not args.no_funnel
    
    # Initialize input funnel if enabled
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
            bot_callback=ask_question if not args.no_bot_core else None,
            response_handler=funnel_response_handler.handle_response,
            min_prompt_interval=args.funnel_interval
        )
        
        # Store the reference globally for clean shutdown
        global_input_funnel = input_funnel
        
        print(f"Input funnel initialized with {args.funnel_interval}s interval")
    
    # Initialize the response handler for the priority system
    response_handler = None
    
    # Initialize priority system
    if not args.no_priority:
        # If not using funnel, create a traditional response handler
        if not use_funnel:
            response_handler = ResponseHandler(bot_name=BOTNAME)
            response_handler.set_llm_callback(ask_question)  # Set as fallback
            response_handler.enable_bot_core(not args.no_bot_core)  # Enable/disable based on flag
            
        # Initialize priority system with correct configuration
        priority_system = init_priority_system(
            llm_callback=ask_question,
            bot_name=BOTNAME,
            enable_bot_core=not args.no_bot_core,
            response_handler_instance=response_handler if not use_funnel else None,
            funnel_instance=input_funnel if use_funnel else None
        )
        
        # Set the input funnel in the input handlers if we're using it
        if use_funnel:
            from nami.input_systems.input_handlers import set_input_funnel, set_feature_flags
            set_input_funnel(input_funnel)
            print("Input funnel connected to input handlers")
            
            # Set feature flags based on command line arguments
            set_feature_flags(
                desktop_audio=args.enable_desktop_audio,
                vision=args.enable_vision_inputs
            )
        
        # Print status
        bot_core_status = "enabled" if not args.no_bot_core else "disabled"
        funnel_status = "enabled" if use_funnel else "disabled"
        print(f"Priority system initialized - Bot core: {bot_core_status}, Funnel: {funnel_status}")
        if use_funnel:
            print(f"Input sources - Desktop Audio: {args.enable_desktop_audio}, Vision: {args.enable_vision_inputs}")
    
    # Start the hearing system if enabled
    if not args.no_hearing:
        if start_hearing_system(
            debug_mode=args.debug,
            output_reader=PriorityHearingOutputReader() if not args.no_priority else None
        ):
            print("Hearing system started")
    
    # Start the vision system if enabled
    if not args.no_vision:
        if start_vision_system(
            output_reader=PriorityVisionOutputReader() if not args.no_priority else None
        ):
            print("Vision system started")
    
    # Start the Twitch chat bot if enabled
    if not args.no_twitch:
        # Initialize the Twitch bot with the response handler (if using traditional approach)
        if use_funnel:
            # When using funnel, the funnel handles Twitch responses
            init_twitch_bot()
        else:
            # With traditional approach, pass the response handler
            init_twitch_bot(handler=response_handler)
        print(f"Twitch chat integration started (with {'funnel' if use_funnel else 'response handler'})")

    # Skip the bot_core startup test - we don't want this prompt to go to the funnel
    # Just wait a short time for all subsystems to initialize
    print("System initialization complete, ready for input")
    time.sleep(1)  # Brief

    # Print a helpful message about input commands
    print("\nInput control commands:")
    print("  enable vision - Enable vision inputs to the AI")
    print("  disable vision - Disable vision inputs to the AI")
    print("  enable desktop audio - Enable desktop audio inputs to the AI")
    print("  disable desktop audio - Disable desktop audio inputs to the AI")
    print("  enable all inputs - Enable all input sources")
    print("  disable all inputs - Disable all input sources except microphone")
    print("  status inputs - Show current input source status")

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