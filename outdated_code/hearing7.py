import os
import time
import numpy as np
import sounddevice as sd
import soundfile as sf
import whisper
import torch
from threading import Thread, Event
from queue import Queue

# Optimized configuration
FS = 16000
CHUNK_DURATION = 3
OVERLAP = 1
MODEL_SIZE = "medium.en"  # More efficient for CPU
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
SAVE_DIR = "audio_captures"

class FixedLatencyTranscriber:
    def __init__(self):
        os.makedirs(SAVE_DIR, exist_ok=True)
        self.model = whisper.load_model(MODEL_SIZE, device=DEVICE)
        if DEVICE == "cuda":
            self.model = self.model.half()
            
        self.result_queue = Queue()
        self.stop_event = Event()
        self.audio_buffer = np.array([], dtype=np.float32)
        self.last_processed = time.time()

    def audio_callback(self, indata, frames, timestamp, status):
        """Fixed parameter naming and buffer handling"""
        if status:
            print(f"Audio status: {status}")
        
        new_audio = np.squeeze(indata).astype(np.float32)
        self.audio_buffer = np.concatenate([self.audio_buffer, new_audio])
        
        # Process when buffer reaches target duration
        while len(self.audio_buffer) >= FS * CHUNK_DURATION:
            chunk = self.audio_buffer[:FS*CHUNK_DURATION]
            self.audio_buffer = self.audio_buffer[FS*(CHUNK_DURATION-OVERLAP):]
            
            if len(chunk) >= FS * 0.5:  # Minimum 0.5s audio
                Thread(target=self.process_chunk, args=(chunk,)).start()
                self.last_processed = time.time()  # Use Python's time module

    def process_chunk(self, chunk):
        try:
            # Save audio in background
            Thread(target=self.save_audio, args=(chunk,), daemon=True).start()
            
            result = self.model.transcribe(
                chunk,
                fp16=(DEVICE == "cuda"),
                beam_size=1,
                temperature=0.0,
                no_speech_threshold=0.4
            )
            
            if result["text"].strip():
                self.result_queue.put(result["text"])
                
        except Exception as e:
            print(f"Processing error: {str(e)}")

    def output_worker(self):
        while not self.stop_event.is_set():
            if not self.result_queue.empty():
                text = self.result_queue.get()
                latency = time.time() - self.last_processed
                print(f"\n[{time.strftime('%H:%M:%S')} | {latency:.1f}s] {text}", flush=True)
                self.result_queue.task_done()
            time.sleep(0.05)

    def save_audio(self, chunk):
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = os.path.join(SAVE_DIR, f"fixed_{timestamp}.wav")
        sf.write(filename, chunk, FS, subtype='PCM_16')

    def run(self):
        print(f"FIXED LATENCY TRANSCRIBER ({MODEL_SIZE.upper()})")
        print(f"Chunk: {CHUNK_DURATION}s | Device: {DEVICE.upper()}")
        
        Thread(target=self.output_worker, daemon=True).start()
        
        try:
            with sd.InputStream(
                samplerate=FS,
                channels=1,
                callback=self.audio_callback,
                blocksize=FS//10  # 100ms blocks
            ):
                print("Listening... [Speak now]")
                while not self.stop_event.is_set():
                    time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop_event.set()
            print("\nTranscription stopped.")

if __name__ == "__main__":
    flt = FixedLatencyTranscriber()
    flt.run()