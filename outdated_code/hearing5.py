import os
import time
import numpy as np
import sounddevice as sd
import soundfile as sf
import torch
import whisper
from threading import Thread, Lock
from queue import Queue

# Configuration
FS = 16000               # Sample rate
CHUNK_DURATION = 10      # Seconds per recording chunk
MODEL_SIZE = "medium.en" # Whisper model size (small/medium/large)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
SAVE_DIR = "audio_captures"

class DualTranscriber:
    def __init__(self):
        os.makedirs(SAVE_DIR, exist_ok=True)
        self.audio_queue = Queue(maxsize=1)  # Single-slot buffer
        self.lock = Lock()
        self.running = True
        
        # Load Whisper model once
        self.model = whisper.load_model(MODEL_SIZE, device=DEVICE)
        if DEVICE == "cuda":
            self.model.half()

    def record_audio(self):
        """Continuous recording thread"""
        while self.running:
            # Only record if queue is empty (prevents parallel recording)
            if self.audio_queue.empty():
                with self.lock:
                    print("\nRecording new chunk...")
                    audio = sd.rec(int(CHUNK_DURATION * FS), 
                                 samplerate=FS, channels=1, dtype='float32')
                    sd.wait()
                
                audio = np.squeeze(audio)
                self.audio_queue.put(audio)
                
                # Save audio to file in background
                Thread(target=self.save_audio, args=(audio,)).start()
                
            time.sleep(0.1)  # Prevent CPU spin

    def process_audio(self):
        """Continuous processing thread"""
        while self.running:
            if not self.audio_queue.empty():
                audio = self.audio_queue.get()
                with self.lock:  # Ensure no recording during transcription
                    start_time = time.time()
                    result = self.model.transcribe(audio, fp16=(DEVICE == "cuda"))
                    print(f"\nTranscription ({time.time()-start_time:.1f}s):")
                    print(result["text"])
                self.audio_queue.task_done()

    def save_audio(self, audio):
        """Save audio chunk with timestamp"""
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = os.path.join(SAVE_DIR, f"chunk_{timestamp}.wav")
        sf.write(filename, audio, FS)
        return filename

    def run(self):
        print(f"Starting dual-threaded transcription with {MODEL_SIZE} model")
        print(f"Using device: {DEVICE.upper()}")
        
        recorder = Thread(target=self.record_audio)
        processor = Thread(target=self.process_audio)
        
        recorder.start()
        processor.start()
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.running = False
            recorder.join()
            processor.join()
            print("\nTranscription stopped.")

if __name__ == "__main__":
    dt = DualTranscriber()
    dt.run()