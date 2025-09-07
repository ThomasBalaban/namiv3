import os
import sys
import numpy as np
import sounddevice as sd
import time
from faster_whisper import WhisperModel
from ..config import MICROPHONE_DEVICE_ID

# ---- Configuration ----
# Model size can be: "tiny.en", "base.en", "small.en", "medium.en", "large-v3"
# Using a smaller model like "base.en" is recommended for real-time performance.
MODEL_SIZE = "base.en" 
# or "cuda" if you have a compatible GPU and CUDA installed
DEVICE = "cpu" 
COMPUTE_TYPE = "int8" # change to "float16" for GPU

SAMPLE_RATE = 16000 # Whisper models are trained on 16kHz audio
CHANNELS = 1
BLOCKSIZE = 16000 # 1 second of audio

# Global variable for the transcription model
model = None
transcript_manager = None

def initialize_faster_whisper():
    """Initializes the Faster Whisper model."""
    global model
    print("Initializing Faster Whisper model...")
    try:
        model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
        print("Faster Whisper model ready.")
    except Exception as e:
        print(f"Error initializing Faster Whisper: {e}")
        raise

def audio_callback(indata, frames, time_info, status):
    """Processes audio from the microphone and transcribes it."""
    global model, transcript_manager
    
    if status:
        print(status, file=sys.stderr)

    try:
        audio_chunk = indata.flatten().astype(np.float32)
        
        # Check if audio chunk is loud enough to be speech
        rms_level = np.sqrt(np.mean(audio_chunk**2))
        if rms_level < 0.01:  # Adjust this threshold as needed
            return

        print(f"🎤 Processing audio (RMS: {rms_level:.4f})...")
        
        # Transcribe the audio chunk with faster-whisper compatible parameters
        # ONLY use parameters that faster-whisper supports
        try:
            segments, info = model.transcribe(
                audio_chunk, 
                beam_size=1,
                language="en"
            )
            
            # Extract text from segments
            full_text = "".join(segment.text for segment in segments).strip()
            
            print(f"🎤 Transcribed: '{full_text}'")

            if full_text and transcript_manager:
                metadata = {
                    "device_id": MICROPHONE_DEVICE_ID,
                    "sample_rate": SAMPLE_RATE,
                    "language": info.language,
                    "language_probability": info.language_probability
                }
                transcript_manager.publish_transcript(
                    source="microphone",
                    text=full_text,
                    metadata=metadata
                )
        except Exception as e:
            print(f"🎤 Transcription error: {e}")
            # Try with no parameters as fallback
            try:
                segments, info = model.transcribe(audio_chunk)
                full_text = "".join(segment.text for segment in segments).strip()
                print(f"🎤 Fallback transcribed: '{full_text}'")
                
                if full_text and transcript_manager:
                    metadata = {
                        "device_id": MICROPHONE_DEVICE_ID,
                        "sample_rate": SAMPLE_RATE,
                        "language": info.language,
                        "language_probability": info.language_probability
                    }
                    transcript_manager.publish_transcript(
                        source="microphone",
                        text=full_text,
                        metadata=metadata
                    )
            except Exception as e2:
                print(f"🎤 Even fallback transcription failed: {e2}")
            
    except Exception as e:
        print(f"Microphone callback error: {e}", file=sys.stderr)

def transcribe_microphone(debug_mode=False, manager=None):
    """
    Starts microphone transcription with Faster Whisper.
    
    Args:
        debug_mode: Enable debug output.
        manager: TranscriptManager instance for publishing transcripts.
    """
    global transcript_manager
    transcript_manager = manager

    try:
        # Initialize the model
        initialize_faster_whisper()

        # Get device info
        device_info = sd.query_devices(MICROPHONE_DEVICE_ID, 'input')
        print(f"🎤 Using: {device_info['name']} (ID: {MICROPHONE_DEVICE_ID})")

        # Start the audio stream
        with sd.InputStream(
            device=MICROPHONE_DEVICE_ID,
            samplerate=SAMPLE_RATE,
            blocksize=BLOCKSIZE,
            dtype="float32",
            channels=CHANNELS,
            callback=audio_callback
        ):
            print("🎧 Listening with microphone (Faster Whisper)...")
            while True:
                sd.sleep(1000)

    except Exception as e:
        print(f"Error in transcribe_microphone: {e}", file=sys.stderr)
        return

if __name__ == "__main__":
    try:
        transcribe_microphone()
    except KeyboardInterrupt:
        print("\nStopped listening")