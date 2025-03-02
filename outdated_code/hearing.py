import os
import time
import sounddevice as sd
import numpy as np
import whisper
import soundfile as sf  # For saving audio files

# Global configuration
FS = 16000              # Sample rate in Hz
CHUNK_DURATION = 5      # Duration in seconds for each audio chunk
SAVE_DIR = "audio_captures"  # Directory to save audio captures

# Ensure the directory exists
os.makedirs(SAVE_DIR, exist_ok=True)

def capture_system_audio(duration=CHUNK_DURATION, fs=FS):
    """
    Capture a chunk of system audio.
    Ensure that your system audio is routed to an input device (using BlackHole/Soundflower).
    """
    print("Recording system audio...")
    recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='float32')
    sd.wait()
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

def transcribe_audio(audio, model):
    """
    Transcribe the provided audio chunk using the Whisper model.
    
    Whisper's transcribe() accepts either a filename or a numpy array.
    """
    print("Transcribing audio chunk...")
    result = model.transcribe(audio, fp16=False)
    return result["text"]

if __name__ == '__main__':
    print("Loading Whisper model...")
    model = whisper.load_model("large")  # or "base", "small", "medium", etc.

    print("Starting continuous desktop audio transcription. Press Ctrl+C to stop.")
    while True:
        # Capture a chunk of system audio
        sys_audio = capture_system_audio()

        # Save the audio capture so you can review it later
        saved_filename = save_audio(sys_audio)

        try:
            # Transcribe the captured audio
            transcription = transcribe_audio(sys_audio, model)
            print("Transcription:")
            print(transcription)
        except Exception as e:
            print("Error during transcription:", e)
        
        # Pause briefly between chunks to avoid overlap or CPU overuse
        time.sleep(0.5)
