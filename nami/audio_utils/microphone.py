import os
import sys
import numpy as np
import sounddevice as sd
import time
from contextlib import contextmanager
from ..config import MICROPHONE_DEVICE_ID

# ---- Set environment variable FIRST ----
os.environ["VOSK_SILENT"] = "1"  # Critical to set BEFORE importing Vosk

# Now import Vosk
from vosk import Model, KaldiRecognizer

# Global variable declaration at the top of the module
transcript_manager = None

# ---- Suppression Utility ----
@contextmanager
def suppress_vosk_logs():
    # Save original file descriptors
    original_stderr_fd = os.dup(sys.stderr.fileno())
    original_stdout_fd = os.dup(sys.stdout.fileno())
    
    # Redirect to /dev/null
    with open(os.devnull, 'w') as devnull:
        os.dup2(devnull.fileno(), sys.stderr.fileno())
        os.dup2(devnull.fileno(), sys.stdout.fileno())
    try:
        yield
    finally:
        # Restore original file descriptors
        os.dup2(original_stderr_fd, sys.stderr.fileno())
        os.dup2(original_stdout_fd, sys.stdout.fileno())
        os.close(original_stderr_fd)
        os.close(original_stdout_fd)

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- Configuration ----
MODEL_PATH = os.path.join(SCRIPT_DIR, "..", "..", "nami/local_models/vosk-model-en-us-0.22")

SAMPLE_RATE = 48000
VOSK_RATE = 16000
CHANNELS = 4
ACTIVE_CHANNEL = 1
BLOCKSIZE = 8000

# Function to initialize vosk model
def initialize_vosk():
    print("Initializing Vosk...")
    with suppress_vosk_logs():
        try:
            model = Model(MODEL_PATH)
            recognizer = KaldiRecognizer(model, VOSK_RATE)
            recognizer.SetWords(False)
            print("Vosk ready.")
            return recognizer
        except Exception as e:
            print(f"Error initializing Vosk: {e}")
            raise

def create_audio_callback(recognizer, manager=None):
    """Create a callback function for the audio stream"""
    
    # Determine if this module is being run directly
    is_standalone = __name__ == "__main__"
    
    def audio_callback(indata, frames, time_info, status):
        """Process audio from microphone"""
        global transcript_manager
        current_manager = manager or transcript_manager
        
        try:
            # Convert byte buffer to numpy array (int16)
            audio_array = np.frombuffer(indata, dtype=np.int16)
            
            # Reshape to (samples, channels)
            audio_2d = audio_array.reshape(-1, CHANNELS)
            
            # Extract active channel
            active_channel = audio_2d[:, ACTIVE_CHANNEL]
            
            # Resample from 48kHz to 16kHz (Vosk requirement)
            resampled = active_channel[::3]  # Simple decimation (48k -> 16k)
            
            # Convert to bytes and feed to Vosk
            if recognizer.AcceptWaveform(resampled.tobytes()):
                result = recognizer.Result()
                text = result[14:-3].strip()  # Extract text from JSON
                
                if text:
                    # Print directly if standalone or transcript manager is not available
                    if is_standalone or not current_manager:
                        print(f"[Microphone Input] {text}")
                    
                    # Publish to transcript manager if available
                    if current_manager:
                        metadata = {
                            "device_id": MICROPHONE_DEVICE_ID,
                            "sample_rate": SAMPLE_RATE
                        }
                        current_manager.publish_transcript(
                            source="microphone",
                            text=text,
                            metadata=metadata
                        )
        except Exception as e:
            print(f"Microphone callback error: {e}")
    
    return audio_callback

def transcribe_microphone(debug_mode=False, manager=None):
    """
    Start microphone transcription with Vosk.
    
    Args:
        debug_mode: Enable debug output
        manager: TranscriptManager instance for publishing transcripts
    """
    global transcript_manager
    transcript_manager = manager
    
    try:
        # Initialize Vosk recognizer
        recognizer = initialize_vosk()
        
        # Get device info
        device_info = sd.query_devices(MICROPHONE_DEVICE_ID)
        print(f"🎤 Using: {device_info['name']} (ID: {MICROPHONE_DEVICE_ID})")
        
        # Create the audio callback with the manager passed directly
        callback = create_audio_callback(recognizer, manager)
        
        # Start the audio stream
        with sd.RawInputStream(
            device=MICROPHONE_DEVICE_ID,
            samplerate=SAMPLE_RATE,
            blocksize=BLOCKSIZE,
            dtype="int16",
            channels=CHANNELS,
            callback=callback
        ):
            print("🎧 Listening with microphone...")
            while True:
                sd.sleep(1000)
                
    except Exception as e:
        print(f"Error in transcribe_microphone: {e}")
        # Don't re-raise, just print the error and return to avoid crashing the main process
        return

if __name__ == "__main__":
    try:
        # When running as main script, transcript_manager is None
        transcribe_microphone()
    except KeyboardInterrupt:
        print("\nStopped listening")