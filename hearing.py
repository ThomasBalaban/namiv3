import argparse
import threading
import os
import time
import signal
import sys
import atexit

from audio_utils.transcriber import SpeechMusicTranscriber
from audio_utils.microphone import transcribe_microphone
from audio_utils.audio_manager import TranscriptManager

def process_transcript(message):
    """
    Process incoming transcripts from the message queue.
    This is where you'd integrate with an AI system.
    """
    source = message.get("source", "unknown")
    text = message.get("text", "")
    timestamp = message.get("timestamp", "")
    
    # This is where you would send the transcription to your AI system
    # For now, we'll just print a message
    print(f"AI RECEIVED: [{timestamp}] ({source}) {text}")

def setup_signal_handlers(transcript_manager):
    """Set up signal handlers for graceful shutdown"""
    def signal_handler(sig, frame):
        print("\nShutting down transcription system...")
        if transcript_manager:
            transcript_manager.close()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Also register an exit handler
    if transcript_manager:
        atexit.register(transcript_manager.close)

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Audio Transcription System")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--keep-files", action="store_true", help="Keep audio files after processing")
    parser.add_argument("--no-mongo", action="store_true", help="Disable MongoDB storage")
    parser.add_argument("--no-mq", action="store_true", help="Disable message queue")
    parser.add_argument("--mongo-uri", type=str, default="mongodb://localhost:27017/", 
                        help="MongoDB connection URI")
    parser.add_argument("--rabbitmq-uri", type=str, default="amqp://guest:guest@localhost:5672/", 
                        help="RabbitMQ connection URI")
    parser.add_argument("--db-name", type=str, default="transcriptions", 
                        help="Database name")
    parser.add_argument("--queue-name", type=str, default="transcriptions", 
                        help="Message queue name")
    args = parser.parse_args()
    
    # Initialize the transcript manager if enabled
    transcript_manager = None
    if not (args.no_mongo and args.no_mq):
        try:
            print(f"Initializing transcript manager...")
            transcript_manager = TranscriptManager(
                mongodb_uri=args.mongo_uri,
                rabbitmq_uri=args.rabbitmq_uri,
                db_name=args.db_name,
                queue_name=args.queue_name,
                debug=args.debug
            )
            
            # Start a consumer to process messages from the queue
            transcript_manager.start_consumer(process_transcript)
            print(f"Transcript manager ready.")
            
            # Set up signal handlers for graceful shutdown
            setup_signal_handlers(transcript_manager)
            
            # Create a directory to store MongoDB data if it doesn't exist
            os.makedirs("data/db", exist_ok=True)
        except Exception as e:
            print(f"Error initializing transcript manager: {e}")
            print(f"Running without transcript storage or messaging.")
            transcript_manager = None
            
    # Start the Vosk microphone transcription in a separate thread
    print("Starting microphone transcription...")
    mic_thread = threading.Thread(
        target=transcribe_microphone,
        args=(args.debug, transcript_manager),
        daemon=True
    )
    mic_thread.start()
    
    # Create and run the main Whisper transcriber
    print("Starting desktop audio transcription...")
    transcriber = SpeechMusicTranscriber(
        keep_files=args.keep_files,
        auto_detect=True,
        debug_mode=args.debug,
        transcript_manager=transcript_manager
    )
    
    try:
        transcriber.run()
    except KeyboardInterrupt:
        print("Stopping all services...")
    finally:
        # Stop the transcript manager if it's running
        if transcript_manager:
            transcript_manager.close()
            
        # The transcriber will handle its own cleanup
        # The mic_thread will be terminated when the main thread exits
        # because it's a daemon thread
        print("Shutdown complete.")

if __name__ == "__main__":
    main()