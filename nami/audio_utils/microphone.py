import os
import sys
import numpy as np
import sounddevice as sd
import time
from contextlib import contextmanager

# ---- Set environment variable FIRST ----
os.environ["VOSK_SILENT"] = "1"  # Critical to set BEFORE importing Vosk

# Now import Vosk
from vosk import Model, KaldiRecognizer

# ---- Suppression Utility (Updated) ----
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

# ---- Rest of Configuration ----
MICROPHONE_DEVICE_ID = 4
MODEL_PATH = os.path.join(SCRIPT_DIR, "..", "..", "nami/local_models/vosk-model-en-us-0.22")

print(f"Checking if model exists at: {os.path.abspath(MODEL_PATH)}")
print(f"Directory exists: {os.path.isdir(MODEL_PATH)}")

SAMPLE_RATE = 48000
VOSK_RATE = 16000
CHANNELS = 4
ACTIVE_CHANNEL = 1
BLOCKSIZE = 8000

# Global transcript manager reference
transcript_manager = None

# Function to initialize vosk model
def initialize_vosk(debug_mode=False):
    print("Initializing Vosk...")
    with suppress_vosk_logs():
        model = Model(MODEL_PATH)
        recognizer = KaldiRecognizer(model, VOSK_RATE)
        recognizer.SetWords(False)
    print("Vosk ready. Starting transcription...")
    return recognizer

def create_audio_callback(recognizer, debug_mode=False):
    """Create a callback function for the audio stream"""
    
    def audio_callback(indata, frames, time_info, status):
        """Process audio from microphone"""
        try:
            # If in debug mode, print status information
            if debug_mode and status:
                print(f"Mic Status: {status}")
                
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
                    # Get current timestamp from system time (not from callback's time_info)
                    timestamp = time.strftime("%H:%M:%S")
                    
                    # Print with expected format for main.py to detect
                    print(f"[Microphone Input] {text}")
                    
                    # Publish to transcript manager if available
                    global transcript_manager
                    if transcript_manager:
                        metadata = {
                            "device_id": MICROPHONE_DEVICE_ID,
                            "sample_rate": SAMPLE_RATE
                        }
                        transcript_manager.publish_transcript(
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
    
    # Initialize Vosk recognizer
    recognizer = initialize_vosk(debug_mode)
    
    # Get device info
    device_info = sd.query_devices(MICROPHONE_DEVICE_ID)
    print(f"🎤 Using: {device_info['name']} (ID: {MICROPHONE_DEVICE_ID})")
    
    # Only print these lines in debug mode
    if debug_mode:
        print(f" Hardware Rate: {SAMPLE_RATE}Hz -> Vosk Rate: {VOSK_RATE}Hz")
        print(f" Active Channel: Input {ACTIVE_CHANNEL + 1} (Left)")
        if transcript_manager:
            print(f" Transcript Manager: Connected")
    
    # Create the audio callback
    callback = create_audio_callback(recognizer, debug_mode)
    
    # Start the audio stream
    with sd.RawInputStream(
        device=MICROPHONE_DEVICE_ID,
        samplerate=SAMPLE_RATE,
        blocksize=BLOCKSIZE,
        dtype="int16",
        channels=CHANNELS,
        callback=callback
    ):
        print("🎧 Listening... (Press Ctrl+C to stop)")
        while True:
            sd.sleep(1000)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Microphone transcription with Vosk")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()
    
    try:
        transcribe_microphone(debug_mode=args.debug)
    except KeyboardInterrupt:
        print("\nStopped listening")