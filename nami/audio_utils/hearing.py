import threading
import os
import time
import signal
import sys
import atexit
from nami.audio_utils.desktop_transcriber import SpeechMusicTranscriber
from nami.audio_utils.microphone import transcribe_microphone
from nami.audio_utils.audio_manager import TranscriptManager

def process_transcript(message):
    """
    Process incoming transcripts from the message queue.
    Format the output according to the source for main.py to recognize.
    """
    source = message.get("source", "unknown")
    text = message.get("text", "")
    
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
        print(f"AI RECEIVED: ({source}) {text}")

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
    # Initialize transcript manager
    transcript_manager = None
    
    try:
        transcript_manager = TranscriptManager()
        
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
            
        # Set up signal handlers for graceful shutdown
        setup_signal_handlers(transcript_manager)
    except Exception as e:
        print(f"Error initializing transcript manager: {e}")
        print(f"Running without messaging.")
        
        # Fall back to memory-only manager
        transcript_manager = TranscriptManager()
            
    # Start the microphone transcription in a separate thread
    print("Starting microphone transcription...")
    mic_thread = threading.Thread(
        target=transcribe_microphone,
        args=(False, transcript_manager),  # Fix: added comma to make it a tuple
        daemon=True
    )
    mic_thread.start()
    
    # Create and run the main Whisper transcriber
    print("Starting desktop audio transcription...")
    transcriber = SpeechMusicTranscriber(
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
            
        print("Shutdown complete.")

if __name__ == "__main__":
    main()