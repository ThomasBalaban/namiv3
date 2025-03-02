import os
import time
import numpy as np
import sounddevice as sd
import soundfile as sf
import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

# Global configuration
FS = 16000              # Sample rate in Hz
CHUNK_DURATION = 5      # Duration in seconds for each audio chunk
SAVE_DIR = "audio_captures"  # Directory to save audio captures

# Ensure the directory exists
os.makedirs(SAVE_DIR, exist_ok=True)

# Set device and precision based on availability
device = "cuda:0" if torch.cuda.is_available() else "cpu"
torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32

# Load the distil-whisper model and processor
model_id = "distil-whisper/distil-large-v3"
print("Loading model...")
model = AutoModelForSpeechSeq2Seq.from_pretrained(
    model_id, torch_dtype=torch_dtype, low_cpu_mem_usage=True, use_safetensors=True
)
model.to(device)
processor = AutoProcessor.from_pretrained(model_id)

def capture_audio(duration=CHUNK_DURATION, fs=FS):
    """
    Capture a chunk of audio from the default microphone.
    """
    print("Recording audio...")
    recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='float32')
    sd.wait()  # Wait until recording is finished
    return np.squeeze(recording)

def save_audio(audio, fs=FS):
    """
    Save the captured audio to a WAV file with a timestamp.
    """
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = os.path.join(SAVE_DIR, f"capture_{timestamp}.wav")
    sf.write(filename, audio, fs)
    print(f"Saved audio capture to: {filename}")
    return filename

def transcribe_audio(audio, fs=FS):
    """
    Transcribe the provided audio chunk using the loaded distil-whisper model.
    """
    print("Transcribing audio chunk...")
    # Preprocess audio (the processor handles resampling/padding if needed)
    inputs = processor(audio, sampling_rate=fs, return_tensors="pt")
    input_features = inputs.input_features.to(device)
    
    # Generate token ids
    with torch.no_grad():
        predicted_ids = model.generate(input_features)
    
    # Decode the token ids to a text transcription
    transcription = processor.batch_decode(predicted_ids, skip_special_tokens=True)[0]
    return transcription

def main():
    print("Starting continuous live audio transcription. Press Ctrl+C to stop.")
    try:
        while True:
            # Capture a chunk of audio
            audio = capture_audio()

            # Optionally, save the captured audio for later review
            save_audio(audio)

            # Transcribe the captured audio chunk
            transcription = transcribe_audio(audio)
            print("Transcription:")
            print(transcription)
            
            # Brief pause between chunks to manage CPU usage
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Transcription stopped by user.")

if __name__ == '__main__':
    main()
