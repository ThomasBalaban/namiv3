#!/usr/bin/env python3
"""
Main entry point for the PeepingNami bot with Hearing and Vision systems.
"""
import argparse
import signal
import sys

# Import our modularized components
from bot_core import start_bot_console
from hearing_system import start_hearing_system, stop_hearing_system
from vision_system import start_vision_system, stop_vision_system, check_vision_queue
from chat_interface import init_twitch_bot

def signal_handler(sig, frame):
    """Handle clean shutdown on Ctrl+C"""
    print("\nShutting down...")
    stop_hearing_system()
    stop_vision_system()
    sys.exit(0)

def main():
    """
    Start the bot, Twitch chat listener, hearing, and vision systems concurrently.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Bot with Hearing and Vision Systems")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode for transcription")
    parser.add_argument("--no-vision", action="store_true", help="Disable vision system")
    parser.add_argument("--no-hearing", action="store_true", help="Disable hearing system")
    parser.add_argument("--no-twitch", action="store_true", help="Disable Twitch chat integration")
    args = parser.parse_args()
    
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    # Start the hearing system if enabled
    if not args.no_hearing:
        start_hearing_system(debug_mode=args.debug)
    
    # Start the vision system if enabled
    if not args.no_vision:
        start_vision_system()
    
    # Start the Twitch chat bot if enabled
    if not args.no_twitch:
        init_twitch_bot()

    try:
        # Start the main bot interaction loop
        start_bot_console()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Clean up resources
        stop_hearing_system()
        stop_vision_system()
        print("Shutdown complete")

if __name__ == "__main__":
    main()