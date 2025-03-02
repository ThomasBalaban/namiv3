import os
import sys
import numpy as np
import sounddevice as sd
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

# ---- Rest of Configuration ----
MICROPHONE_DEVICE_ID = 4        
MODEL_PATH = "local_models/vosk-model-en-us-0.22"
SAMPLE_RATE = 48000             
VOSK_RATE = 16000               
CHANNELS = 4                    
ACTIVE_CHANNEL = 1           
BLOCKSIZE = 8000                

# ---- Silent Model Loading ----
print("Initializing Vosk...")
with suppress_vosk_logs():
    model = Model(MODEL_PATH)
    recognizer = KaldiRecognizer(model, VOSK_RATE)
    recognizer.SetWords(False)
print("Vosk ready. Starting transcription...")


def audio_callback(indata, frames, time, status, debug_mode=False):
    """Process audio from Scarlett Solo"""
    # Convert byte buffer to numpy array (int16)
    audio_array = np.frombuffer(indata, dtype=np.int16)
    
    # If in debug mode, print status information
    if debug_mode and status:
        print(f"Status: {status}")
        
    # Reshape to (samples, channels)
    audio_2d = audio_array.reshape(-1, CHANNELS)
    # Extract active channel
    active_channel = audio_2d[:, ACTIVE_CHANNEL]
    # Resample from 48kHz to 16kHz (Vosk requirement)
    resampled = active_channel[::3] # Simple decimation (48k -> 16k)
    # Convert to bytes and feed to Vosk
    if recognizer.AcceptWaveform(resampled.tobytes()):
        result = recognizer.Result()
        text = result[14:-3].strip()
        print(f"[Microphone Input] {text}")


def transcribe_microphone(debug_mode=False):
    device_info = sd.query_devices(MICROPHONE_DEVICE_ID)
    print(f"🎤 Using: {device_info['name']} (ID: {MICROPHONE_DEVICE_ID})")
    
    # Only print these lines in debug mode
    if debug_mode:
        print(f" Hardware Rate: {SAMPLE_RATE}Hz -> Vosk Rate: {VOSK_RATE}Hz")
        print(f" Active Channel: Input {ACTIVE_CHANNEL + 1} (Left)")
    
    with sd.RawInputStream(
        device=MICROPHONE_DEVICE_ID,
        samplerate=SAMPLE_RATE,
        blocksize=BLOCKSIZE,
        dtype="int16",
        channels=CHANNELS,
        callback=audio_callback
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