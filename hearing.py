import threading
from audio_utils.transcriber import SpeechMusicTranscriber
from audio_utils.microphone import transcribe_microphone

if __name__ == "__main__":
    # You can control debug mode here
    debug_mode = False  # Set to True to enable debug mode
    
    # Start the Vosk microphone transcription in a separate thread
    mic_thread = threading.Thread(
        target=transcribe_microphone,
        args=(debug_mode,),
        daemon=True
    )
    mic_thread.start()
    
    # Create and run the main Whisper transcriber
    transcriber = SpeechMusicTranscriber(
        keep_files=False, 
        auto_detect=True,
        debug_mode=debug_mode
    )
    
    try:
        transcriber.run()
    except KeyboardInterrupt:
        print("Stopping all services...")
    finally:
        # The transcriber will handle its own cleanup
        # The mic_thread will be terminated when the main thread exits
        # because it's a daemon thread
        pass