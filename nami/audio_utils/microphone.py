import os
import sys
import numpy as np
import sounddevice as sd
import time
from faster_whisper import WhisperModel
from ..config import MICROPHONE_DEVICE_ID
from queue import Queue, Empty
from threading import Thread, Event

# ---- Configuration for Microphone ---
MODEL_SIZE = "base.en" 
DEVICE = "cpu"
# --- FIX: Change compute type to int8 for optimal CPU performance ---
COMPUTE_TYPE = "int8"
SAMPLE_RATE = 16000
CHANNELS = 1
BLOCKSIZE = int(SAMPLE_RATE * 1.5)

# Global variables for this self-contained module
model = None
audio_queue = Queue()
stop_event = Event()

def initialize_faster_whisper():
    """Initializes the Faster Whisper model for the microphone."""
    global model
    print("🎙️ Initializing faster-whisper for Microphone...")
    try:
        model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
        print("✅ faster-whisper model for Microphone is ready.")
    except Exception as e:
        print(f"❌ Error initializing faster-whisper for Microphone: {e}")
        raise

def audio_callback(indata, frames, time_info, status):
    """Puts microphone audio chunks into a queue."""
    if status:
        print(status, file=sys.stderr)
    audio_queue.put(indata.copy())

def transcription_worker():
    """Worker thread that processes microphone audio from the queue."""
    global model
    while not stop_event.is_set():
        try:
            audio_chunk_raw = audio_queue.get(timeout=1.0)
            audio_chunk = audio_chunk_raw.flatten().astype(np.float32)

            rms_level = np.sqrt(np.mean(audio_chunk**2))
            if rms_level < 0.008:
                continue

            segments, info = model.transcribe(audio_chunk, beam_size=5, language="en")
            full_text = "".join(segment.text for segment in segments).strip()

            if full_text:
                print(f"[Microphone Input] {full_text}")
                sys.stdout.flush()

        except Empty:
            continue
        except Exception as e:
            print(f"🎤 Mic Whisper transcription error: {e}", file=sys.stderr)

def transcribe_microphone():
    """Starts the complete, self-contained microphone transcription system."""
    try:
        initialize_faster_whisper()
        device_info = sd.query_devices(MICROPHONE_DEVICE_ID, 'input')
        print(f"🎤 Using: {device_info['name']} (ID: {MICROPHONE_DEVICE_ID})")

        worker = Thread(target=transcription_worker, daemon=True)
        worker.start()

        with sd.InputStream(
            device=MICROPHONE_DEVICE_ID,
            samplerate=SAMPLE_RATE,
            blocksize=BLOCKSIZE,
            dtype="float32",
            channels=CHANNELS,
            callback=audio_callback
        ):
            print("🎤 Whisper is now listening to the microphone...")
            stop_event.wait() 

    except Exception as e:
        print(f"❌ Error in transcribe_microphone: {e}", file=sys.stderr)
    finally:
        print("🎤 Microphone transcription stopped.")

if __name__ == "__main__":
    try:
        transcribe_microphone()
    except KeyboardInterrupt:
        print("\nStopping microphone listener...")
        stop_event.set()