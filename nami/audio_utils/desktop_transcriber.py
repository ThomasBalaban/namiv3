import os
import time
import argparse
from threading import Thread, Event
from queue import Queue
from .desktop_speech_music_classifier import SpeechMusicClassifier
from .desktop_audio_processor import AudioProcessor

class SpeechMusicTranscriber:
    def __init__(self, keep_files=False, auto_detect=True, transcript_manager=None):
        from nami.config import FS, MODEL_SIZE, DEVICE, SAVE_DIR
        self.FS = FS
        
        os.makedirs(SAVE_DIR, exist_ok=True)
        
        print(f"Loading Whisper model: {MODEL_SIZE} on {DEVICE}")
        try:            
            import whisper
            self.model = whisper.load_model(MODEL_SIZE)
            
            # Move model to specified device if needed
            if DEVICE == "cuda" and hasattr(self.model, "to"):
                self.model = self.model.to(DEVICE)
                # For CUDA devices, we can use half precision
                self.model = self.model.half()
                
        except Exception as e:
            print(f"Error loading model: {e}")
            print(f"Detailed error information to help fix the issue:")
            import traceback
            traceback.print_exc()
            raise
            
        self.result_queue = Queue()
        self.stop_event = Event()
        self.saved_files = []  # Track saved files for cleanup
        self.keep_files = keep_files  # Flag to control file retention
        self.active_threads = 0  # Track number of active processing threads
        self.processing_lock = Event()  # Used to control processing flow
        self.processing_lock.set()  # Initially allow processing
        self.last_processed = time.time()
        
        # Speech/Music classifier
        self.classifier = SpeechMusicClassifier()
        self.auto_detect = auto_detect
        
        # Transcript Manager for persistent storage
        self.transcript_manager = transcript_manager
        
        # Initialize audio processor
        self.audio_processor = AudioProcessor(self)

    def set_audio_type(self, audio_type):
        """Manual override of audio type"""
        valid_types = ["speech", "music"]
        if audio_type in valid_types:
            prev_type = self.classifier.current_type
            self.classifier.current_type = audio_type
            # Also set history to this type for persistence
            self.classifier.history = [audio_type] * self.classifier.max_history
            print(f"Audio type changed: {prev_type.upper()} → {audio_type.upper()}")
            return True
        return False
        
    def toggle_auto_detect(self):
        """Toggle automatic audio type detection"""
        self.auto_detect = not self.auto_detect
        print(f"Automatic detection: {'ON' if self.auto_detect else 'OFF'}")

    def cleanup_files(self):
        """Remove all saved audio files"""
        count = 0
        for filename in self.saved_files:
            if os.path.exists(filename):
                try:
                    os.remove(filename)
                    count += 1
                except Exception as e:
                    print(f"Error removing file {filename}: {str(e)}")
        
        print(f"Cleaned up {count} audio files")
    
    def output_worker(self):
        """Process and display transcription results"""
        while not self.stop_event.is_set():
            try:
                if not self.result_queue.empty():
                    text, filename, audio_type, confidence = self.result_queue.get()
                    latency = time.time() - self.last_processed
                    timestamp = time.strftime("%H:%M:%S")
                    
                    # Format output based on whether we have text
                    if text:
                        if text.startswith("[Error"):
                            print(f"\n[{timestamp} | {latency:.1f}s] [{audio_type.upper()} {confidence:.2f}] {text}", flush=True)
                        else:
                            print(f"[{timestamp} | {latency:.1f}s] [{audio_type.upper()} {confidence:.2f}] {text}", flush=True)
                            
                            # Publish to transcript manager if available
                            if self.transcript_manager:
                                metadata = {
                                    "audio_type": audio_type,
                                    "confidence": float(confidence),
                                    "latency": float(latency)
                                }
                                self.transcript_manager.publish_transcript(
                                    source="desktop",
                                    text=text,
                                    metadata=metadata
                                )
                    
                    # Delete the file after processing if not keeping files
                    if not self.keep_files and filename and os.path.exists(filename):
                        try:
                            os.remove(filename)
                        except Exception as e:
                            print(f"Error removing file: {str(e)}")
                    
                    self.result_queue.task_done()
                time.sleep(0.05)
            except Exception as e:
                print(f"Output worker error: {str(e)}")
        
    def run(self):
        from nami.config import MODEL_SIZE, DEVICE, CHUNK_DURATION, OVERLAP, FS
        import sounddevice as sd
        
        print(f"Model: {MODEL_SIZE.upper()} | Device: {DEVICE.upper()}")
        print(f"Chunk: {CHUNK_DURATION}s with {OVERLAP}s overlap")
        print(f"Transcript Manager: Connected")

        # Start output worker thread
        output_thread = Thread(target=self.output_worker, daemon=True)
        output_thread.start()
        
        try:
            # Start audio input stream
            with sd.InputStream(
                samplerate=FS,
                channels=1,
                callback=self.audio_processor.audio_callback,
                blocksize=FS//10 # 100ms blocks
            ):
                print("Listening to desktop...")
                print("Press Ctrl+C to stop")
                
                # Main loop - just wait for Ctrl+C or 'q'
                while not self.stop_event.is_set():
                    time.sleep(0.1)
                    
        except KeyboardInterrupt:
            print("\nReceived interrupt, stopping...")
        finally:
            self.stop_event.set()
            print("\nShutting down...")
            
            # Final cleanup of any remaining files
            if not self.keep_files:
                self.cleanup_files()


def main():    
    try:
        transcriber = SpeechMusicTranscriber()
        transcriber.run()
    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as e:
        print(f"Error: {str(e)}")


# This will make the module executable when run directly
if __name__ == "__main__":
    main()