import os
import time
import numpy as np
import sounddevice as sd
import soundfile as sf
import torch
import whisper

# Global configuration
FS = 16000              # Sample rate in Hz
CHUNK_DURATION = 5      # Duration in seconds for each audio chunk
SAVE_DIR = "audio_captures"  # Directory to save audio captures
MODEL_ID = "large-v3"   # Whisper model variant

# Ensure the directory exists
os.makedirs(SAVE_DIR, exist_ok=True)

# Set device based on availability
device = "cuda" if torch.cuda.is_available() else "cpu"

# Load the Whisper model
print("Loading Whisper model...")
model = whisper.load_model(MODEL_ID, device=device)
if device == "cuda":
    model.half()  # Use half-precision for better performance on GPU

def capture_audio(duration=CHUNK_DURATION, fs=FS):
    """Capture a chunk of audio from the default microphone."""
    print("Recording audio...")
    recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='float32')
    sd.wait()  # Wait until recording is finished
    return np.squeeze(recording)

def save_audio(audio, fs=FS):
    """Save the captured audio to a WAV file with a timestamp."""
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = os.path.join(SAVE_DIR, f"capture_{timestamp}.wav")
    sf.write(filename, audio, fs)
    print(f"Saved audio capture to: {filename}")
    return filename

def transcribe_audio(audio_array, fs=FS):
    """Transcribe the provided audio numpy array using Whisper."""
    print("Transcribing audio chunk...")
    result = model.transcribe(
        audio_array,
        fp16=(device == "cuda"),  # Use FP16 if on CUDA
        language="en"              # Optional: specify language
    )
    return result["text"]

def main():
    print("Starting continuous live audio transcription. Press Ctrl+C to stop.")
    try:
        while True:
            # Capture and save audio
            audio = capture_audio()
            save_audio(audio)  # Optional but recommended for review
            
            # Transcribe the audio
            transcription = transcribe_audio(audio)
            print("Transcription:")
            print(transcription)
            
            # Brief pause between chunks
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Transcription stopped by user.")

if __name__ == '__main__':
    main()