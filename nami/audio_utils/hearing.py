import argparse
import threading
import os
import time
import signal
import sys
import atexit
from nami.audio_utils.transcriber import SpeechMusicTranscriber
from nami.audio_utils.microphone import transcribe_microphone
from nami.audio_utils.audio_manager import TranscriptManager

def process_transcript(message):
    """
    Process incoming transcripts from the message queue.
    Format the output according to the source for main.py to recognize.
    """
    source = message.get("source", "unknown")
    text = message.get("text", "")
    timestamp = message.get("timestamp", "")
    
    # Format the output differently based on source
    if source.lower() == "microphone":
        # Format for microphone - this is what main.py is looking for
        print(f"[Microphone Input] {text}")
    elif source.lower() in ["desktop", "speech", "music"]:
        # Format for desktop audio - main.py expects this format
        confidence = message.get("metadata", {}).get("confidence", 0.7)
        source_type = message.get("metadata", {}).get("source_type", "SPEECH")
        print(f"[{source_type} {confidence:.2f}] {text}")
    else:
        # Fallback format for other sources
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
    parser.add_argument("--no-mq", action="store_true", help="Disable message queue")
    parser.add_argument("--rabbitmq-uri", type=str, default="amqp://guest:guest@localhost:5672/", 
                        help="RabbitMQ connection URI")
    parser.add_argument("--queue-name", type=str, default="transcriptions", 
                        help="Message queue name")
    args = parser.parse_args()
    
    # Initialize transcript manager
    transcript_manager = None
    
    # If message queue is disabled, create a memory-only manager
    if args.no_mq:
        print(f"Creating memory-only transcript manager...")
        transcript_manager = TranscriptManager(debug=args.debug)
        
        # Create a simple processing function
        def direct_process(source, text, metadata=None):
            process_transcript({
                "source": source,
                "text": text,
                "timestamp": time.strftime("%H:%M:%S"),
                "metadata": metadata or {}
            })
            
        # Set up a simplified publish_transcript that calls process_transcript directly
        old_publish = transcript_manager.publish_transcript
        def new_publish(source, text, timestamp=None, metadata=None):
            # Still call the original for any in-memory tracking
            old_publish(source, text, timestamp, metadata)
            # Also process immediately
            process_transcript({
                "source": source,
                "text": text,
                "timestamp": timestamp or time.strftime("%H:%M:%S"),
                "metadata": metadata or {}
            })
        transcript_manager.publish_transcript = new_publish
        
    else:
        # Try to initialize with message queue only
        try:
            print(f"Initializing transcript manager with message queue only...")
            transcript_manager = TranscriptManager(
                queue_name=args.queue_name,
                debug=args.debug
            )
            
            # Start a consumer to process messages from the queue
            transcript_manager.start_consumer(process_transcript)
            print(f"Transcript manager ready.")
            
            # Set up signal handlers for graceful shutdown
            setup_signal_handlers(transcript_manager)
        except Exception as e:
            print(f"Error initializing transcript manager: {e}")
            print(f"Running without messaging.")
            
            # Fall back to memory-only manager
            transcript_manager = TranscriptManager(debug=args.debug)
            
            # Set up direct processing
            old_publish = transcript_manager.publish_transcript
            def new_publish(source, text, timestamp=None, metadata=None):
                # Call the original for any in-memory tracking
                old_publish(source, text, timestamp, metadata)
                # Also process immediately
                process_transcript({
                    "source": source,
                    "text": text,
                    "timestamp": timestamp or time.strftime("%H:%M:%S"),
                    "metadata": metadata or {}
                })
            transcript_manager.publish_transcript = new_publish
            
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