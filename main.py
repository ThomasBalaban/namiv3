#!/usr/bin/env python3
"""
Main entry point for the PeepingNami bot with Priority System.
"""
import argparse
import signal
import threading
import os
from bot_core import ask_question, BOTNAME
from hearing_system import start_hearing_system, stop_hearing_system
from vision_system import start_vision_system, stop_vision_system, check_vision_queue
from chat_interface import init_twitch_bot
from config import TARGET_CHANNEL
from input_systems.response_handler import ResponseHandler

# Import priority system components from the input_systems folder
from input_systems import (
    init_priority_system,
    shutdown_priority_system, 
    process_console_command,
    process_hearing_line,
    process_vision_line
)

def signal_handler(sig, frame):
    """Handle clean shutdown on Ctrl+C"""
    print("\nShutting down...")
    try:
        # Try graceful shutdown first
        stop_hearing_system()
        stop_vision_system()
        shutdown_priority_system()
        
        threading.Timer(4.0, lambda: os._exit(0)).start()
    except:
        # If anything fails, force exit immediately
        os._exit(0)

# ====== MODIFIED OUTPUT READERS ======

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

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Bot with Hearing and Vision Systems")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode for transcription")
    parser.add_argument("--no-vision", action="store_true", help="Disable vision system")
    parser.add_argument("--no-hearing", action="store_true", help="Disable hearing system")
    parser.add_argument("--no-twitch", action="store_true", help="Disable Twitch chat integration")
    parser.add_argument("--no-priority", action="store_true", help="Disable priority system")
    # Add new argument for bot_core, defaults to True (opposite of previous twitch_responses)
    parser.add_argument("--no-bot-core", action="store_true", help="Disable using bot_core for responses")
    # Keep the old flags for backward compatibility
    parser.add_argument("--twitch-responses", action="store_true", help="[Deprecated] Use --use-bot-core instead")
    parser.add_argument("--use-bot-core", action="store_true", help="[Deprecated] Bot core is used by default now")
    args = parser.parse_args()

    # Print just the command line flag first
    print(f"Status check - Using bot_core: {not args.no_bot_core}")
    
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    # Initialize the response handler for the new integration
    response_handler = None
    
    # Initialize priority system if enabled
    if not args.no_priority:
        # Create the response handler
        response_handler = ResponseHandler(bot_name=BOTNAME)
        response_handler.set_llm_callback(ask_question)  # Set as fallback
        response_handler.enable_bot_core(not args.no_bot_core)  # Enable/disable based on flag
        
        # Initialize priority system with the response handler
        priority_system = init_priority_system(
            llm_callback=ask_question,
            twitch_callback=None,
            bot_name=BOTNAME,
            enable_twitch_responses=True,
            enable_bot_core=not args.no_bot_core,
            response_handler_instance=response_handler  # Changed from response_handler
        )
        
        bot_core_status = "enabled" if not args.no_bot_core else "disabled"
        print(f"Priority system initialized - Bot core responses {bot_core_status}")
        print(f"Response handler initialized - use_bot_core flag: {response_handler.use_bot_core}")
    
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
        # Initialize the Twitch bot with the response handler
        init_twitch_bot(handler=response_handler)
        print("Twitch chat integration started with response handler integration")

    # Test the bot_core at startup if enabled
    if not args.no_bot_core:
        print("\n" + "!" * 50)
        print("!!!!! TESTING BOT_CORE AT STARTUP !!!!!")
        print("!" * 50 + "\n")
        try:
            test_response = ask_question("This is a startup test. Please respond briefly.")
            print(f"Bot core test response: {test_response}")
        except Exception as e:
            print(f"Error in startup bot_core test: {e}")

    try:
        # Start the main console interaction loop
        console_input_loop()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Clean up resources
        stop_hearing_system()
        stop_vision_system()
        shutdown_priority_system()
        print("Shutdown complete")

if __name__ == "__main__":
    main()