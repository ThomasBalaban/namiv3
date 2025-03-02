import os
import time
import numpy as np
import sounddevice as sd
import soundfile as sf
import whisper
import torch  # Added missing torch import
from threading import Thread, Event
from queue import Queue

# Configuration
FS = 16000
CHUNK_DURATION = 6
OVERLAP = 1
MODEL_SIZE = "large-v3"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
SAVE_DIR = "audio_captures"

class LiveTranscriber:
    def __init__(self):
        os.makedirs(SAVE_DIR, exist_ok=True)
        self.model = whisper.load_model(MODEL_SIZE, device=DEVICE)
        if DEVICE == "cuda":
            self.model = self.model.half()
            
        self.audio_queue = Queue(maxsize=3)
        self.stop_event = Event()
        self.last_chunk_buffer = np.array([], dtype=np.float32)  # Fixed initialization

    def record_audio(self):
        """Fixed recording with proper buffer handling"""
        while not self.stop_event.is_set():
            try:
                # Record new audio
                new_audio = sd.rec(int(CHUNK_DURATION * FS), 
                                  samplerate=FS, channels=1, dtype='float32')
                sd.wait()
                new_audio = np.squeeze(new_audio).astype(np.float32)
                
                # Combine with overlap buffer
                full_chunk = np.concatenate([self.last_chunk_buffer, new_audio])
                
                # Update buffer with overlap for next chunk
                self.last_chunk_buffer = new_audio[-int(OVERLAP*FS):]
                
                # Save and queue in parallel
                Thread(target=self.save_audio, args=(full_chunk,), daemon=True).start()
                self.audio_queue.put(full_chunk)
                
            except Exception as e:
                print(f"Recording error: {str(e)}")
                break

    def transcribe_audio(self):
        """More robust transcription handling"""
        while not self.stop_event.is_set():
            try:
                if not self.audio_queue.empty():
                    audio = self.audio_queue.get()
                    
                    result = self.model.transcribe(
                        audio,
                        fp16=(DEVICE == "cuda"),
                        beam_size=5,
                        temperature=0.5
                    )
                    
                    print(f"\n[{time.strftime('%H:%M:%S')}] Transcription:")
                    print(result["text"][:500])
                    self.audio_queue.task_done()
                    
            except Exception as e:
                print(f"Transcription error: {str(e)}")
                break

    def save_audio(self, audio):
        """Guaranteed sample rate conversion for Whisper"""
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = os.path.join(SAVE_DIR, f"live_{timestamp}.wav")
        sf.write(filename, audio, FS, subtype='PCM_16')
        return filename

    def run(self):
        print(f"Starting LIVE transcription ({MODEL_SIZE})")
        print(f"Chunk: {CHUNK_DURATION}s | Overlap: {OVERLAP}s | Device: {DEVICE.upper()}")

        recorder = Thread(target=self.record_audio, daemon=True)
        transcriber = Thread(target=self.transcribe_audio, daemon=True)

        recorder.start()
        time.sleep(1)  # Ensure recorder starts first
        transcriber.start()

        try:
            while True: 
                time.sleep(1)
                print(f"\r[Status] Queue: {self.audio_queue.qsize()} | Buffer: {len(self.last_chunk_buffer)/FS:.1f}s", end="")
        except KeyboardInterrupt:
            self.stop_event.set()
            recorder.join(timeout=1)
            transcriber.join(timeout=1)
            print("\nTranscription stopped safely.")

if __name__ == "__main__":
    lt = LiveTranscriber()
    lt.run()