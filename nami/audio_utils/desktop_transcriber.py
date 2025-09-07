import os
import time
import argparse
from threading import Thread, Event
from queue import Queue
import sounddevice as sd
from .desktop_speech_music_classifier import SpeechMusicClassifier
from .desktop_audio_processor import AudioProcessor

# Import faster-whisper
try:
    from faster_whisper import WhisperModel
    print("✅ faster-whisper imported successfully")
except ImportError as e:
    print(f"❌ Error importing faster-whisper: {e}")
    print("Please install it with: pip install faster-whisper")
    raise

class SpeechMusicTranscriber:
    def __init__(self, keep_files=False, auto_detect=True, transcript_manager=None):
        # Import config here to avoid circular imports
        try:
            from nami.config import FS, MODEL_SIZE, DEVICE, SAVE_DIR
            self.FS = FS
            self.MODEL_SIZE = MODEL_SIZE
            self.DEVICE = DEVICE
            self.SAVE_DIR = SAVE_DIR
        except ImportError:
            print("⚠️ Using fallback config values")
            self.FS = 16000
            self.MODEL_SIZE = "base.en"
            self.DEVICE = "cpu"
            self.SAVE_DIR = "audio_captures"
        
        os.makedirs(self.SAVE_DIR, exist_ok=True)
        
        print(f"🎙️ Initializing Faster Whisper model: {self.MODEL_SIZE} on {self.DEVICE}")
        
        # Try to fix tqdm issue by setting environment variable
        os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
        
        try:
            # Use faster-whisper with proper error handling
            compute_type = "int8" if self.DEVICE == "cpu" else "float16"
            
            # First try with local files only (if already downloaded)
            try:
                self.model = WhisperModel(
                    self.MODEL_SIZE, 
                    device=self.DEVICE, 
                    compute_type=compute_type,
                    download_root=None,
                    local_files_only=True
                )
                print("✅ Faster Whisper model loaded from cache")
            except Exception:
                # If local files don't exist, try downloading
                print("📥 Model not cached, downloading...")
                self.model = WhisperModel(
                    self.MODEL_SIZE, 
                    device=self.DEVICE, 
                    compute_type=compute_type,
                    download_root=None,
                    local_files_only=False
                )
                print("✅ Faster Whisper model downloaded and loaded")
                
        except Exception as e:
            error_msg = str(e)
            if "_lock" in error_msg or "tqdm" in error_msg:
                print(f"❌ Error loading model due to tqdm compatibility issue: {e}")
                print("🔧 Try running: python download_models.py")
                print("   Or manually fix with: pip install 'tqdm>=4.66.0,<5.0.0'")
            else:
                print(f"❌ Error loading Faster Whisper model: {e}")
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
        print("🔄 Audio processor initialized")

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
        
        if count > 0:
            print(f"🧹 Cleaned up {count} audio files")
    
    def output_worker(self):
        """Process and display transcription results"""
        print("🔄 Output worker started")
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
                print(f"❌ Output worker error: {str(e)}")
        
        print("🔄 Output worker stopped")
    
    def run(self):
        print(f"🚀 Starting Desktop Audio Transcription")
        print(f"Model: {self.MODEL_SIZE.upper()} | Device: {self.DEVICE.upper()}")
        print(f"Chunk: {3}s with {0.5}s overlap")  # Using hardcoded values for now
        print(f"Transcript Manager: {'Connected' if self.transcript_manager else 'None'}")

        # Start output worker thread
        output_thread = Thread(target=self.output_worker, daemon=True)
        output_thread.start()
        print("✅ Output worker thread started")
        
        # List available audio devices
        print("\n📱 Available audio devices:")
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                print(f"  {i}: {device['name']} (Input)")
        
        try:
            # Start audio input stream
            print(f"\n🎧 Starting audio stream...")
            with sd.InputStream(
                samplerate=self.FS,
                channels=1,
                callback=self.audio_processor.audio_callback,
                blocksize=self.FS//10,  # 100ms blocks
                device=None  # Use default device, you can specify device ID here
            ):
                print("✅ Audio stream started successfully")
                print("🎤 Listening to desktop audio...")
                print("Press Ctrl+C to stop")
                
                # Main loop - just wait for Ctrl+C or 'q'
                while not self.stop_event.is_set():
                    time.sleep(0.1)
                    
        except KeyboardInterrupt:
            print("\n🛑 Received interrupt, stopping...")
        except Exception as e:
            print(f"❌ Error in audio stream: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.stop_event.set()
            print("\n🔄 Shutting down...")
            
            # Final cleanup of any remaining files
            if not self.keep_files:
                self.cleanup_files()
            
            print("✅ Shutdown complete")


def main():    
    try:
        print("🎙️ Starting Desktop Audio Transcriber...")
        transcriber = SpeechMusicTranscriber()
        transcriber.run()
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user")
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()


# This will make the module executable when run directly
if __name__ == "__main__":
    main()