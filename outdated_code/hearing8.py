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
MODEL_SIZE = "medium.en" # More efficient for CPU
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
SAVE_DIR = "audio_captures"
MAX_THREADS = 3  # Limit concurrent processing threads

class FixedLatencyTranscriber:
    def __init__(self, keep_files=False):
        os.makedirs(SAVE_DIR, exist_ok=True)
        self.model = whisper.load_model(MODEL_SIZE, device=DEVICE)
        if DEVICE == "cuda":
            self.model = self.model.half()
        self.result_queue = Queue()
        self.stop_event = Event()
        self.audio_buffer = np.array([], dtype=np.float32)
        self.last_processed = time.time()
        self.saved_files = []  # Track saved files for cleanup
        self.keep_files = keep_files  # Flag to control file retention
        self.active_threads = 0  # Track number of active processing threads
        self.processing_lock = Event()  # Used to control processing flow
        self.processing_lock.set()  # Initially allow processing
        
    def audio_callback(self, indata, frames, timestamp, status):
        """Process incoming audio data"""
        if status:
            print(f"Audio status: {status}")
        
        # Check for silence or very low audio - this could help prevent empty chunks
        new_audio = np.squeeze(indata).astype(np.float32)
        
        # Skip if audio is mostly silence
        if np.abs(new_audio).mean() < 0.001:
            return
            
        self.audio_buffer = np.concatenate([self.audio_buffer, new_audio])
        
        # Process when buffer reaches target duration and we're not overloaded
        if self.processing_lock.is_set() and len(self.audio_buffer) >= FS * CHUNK_DURATION:
            # Check if we have too many active threads
            if self.active_threads >= MAX_THREADS:
                return  # Skip processing this chunk to avoid overload
                
            chunk = self.audio_buffer[:FS*CHUNK_DURATION].copy()
            self.audio_buffer = self.audio_buffer[FS*(CHUNK_DURATION-OVERLAP):]
            
            # Validate chunk has actual content
            if len(chunk) >= FS * 0.5 and np.abs(chunk).mean() > 0.001:
                self.active_threads += 1
                Thread(target=self.process_chunk, args=(chunk,)).start()
                self.last_processed = time.time()
            
    def process_chunk(self, chunk):
        try:
            # Validate the chunk before processing
            if len(chunk) < FS * 0.5 or np.abs(chunk).mean() < 0.001:
                # Silently skip empty or silent audio chunk
                self.active_threads -= 1
                return
                
            # Save audio in background and get the filename
            filename = self.save_audio(chunk)
            
            # Add minimal padding to prevent shape errors
            if len(chunk) % 2 != 0:
                chunk = np.pad(chunk, (0, 1), 'constant')
                
            result = self.model.transcribe(
                chunk,
                fp16=(DEVICE == "cuda"),
                beam_size=1,
                temperature=0.0,
                no_speech_threshold=0.6  # Increased to better filter out non-speech
            )
            
            if result["text"].strip():
                self.result_queue.put((result["text"], filename))
            else:
                # Clean up file if no speech detected
                if not self.keep_files and filename and os.path.exists(filename):
                    os.remove(filename)
                
        except Exception as e:
            print(f"Processing error: {str(e)}")
            # Try to diagnose the issue
            if "cannot reshape tensor of 0 elements" in str(e):
                print(f"Chunk length: {len(chunk)}, Mean amplitude: {np.abs(chunk).mean()}")
                # Temporarily pause processing to prevent cascade failures
                if self.processing_lock.is_set():
                    self.processing_lock.clear()
                    print("Pausing processing due to errors...")
                    # Resume after a short delay
                    Thread(target=self.resume_processing_after_delay, args=(2,)).start()
        finally:
            self.active_threads -= 1
            
    def resume_processing_after_delay(self, delay_seconds):
        """Resume processing after a delay"""
        time.sleep(delay_seconds)
        # Clear audio buffer to start fresh
        self.audio_buffer = np.array([], dtype=np.float32)
        print("Resuming processing...")
        self.processing_lock.set()
            
    def output_worker(self):
        while not self.stop_event.is_set():
            if not self.result_queue.empty():
                text, filename = self.result_queue.get()
                latency = time.time() - self.last_processed
                print(f"\n[{time.strftime('%H:%M:%S')} | {latency:.1f}s] {text}", flush=True)
                
                # Delete the file after transcription if not keeping files (silently)
                if not self.keep_files and filename and os.path.exists(filename):
                    try:
                        os.remove(filename)
                    except Exception as e:
                        # Only print on error, not on successful deletion
                        print(f"Error removing file: {str(e)}")
                
                self.result_queue.task_done()
            time.sleep(0.05)
            
    def save_audio(self, chunk):
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = os.path.join(SAVE_DIR, f"fixed_{timestamp}.wav")
        sf.write(filename, chunk, FS, subtype='PCM_16')
        self.saved_files.append(filename)
        return filename
        
    def cleanup_files(self):
        """Remove all saved audio files"""
        count = 0
        for filename in self.saved_files:
            if os.path.exists(filename):
                try:
                    os.remove(filename)
                    count += 1
                except Exception as e:
                    print(f"Error removing file {filename}: {str(e)}")
        
        print(f"Cleaned up {count} audio files")
        
    def run(self):
        print(f"FIXED LATENCY TRANSCRIBER ({MODEL_SIZE.upper()})")
        print(f"Chunk: {CHUNK_DURATION}s | Device: {DEVICE.upper()}")
        print(f"Audio files will be automatically deleted after processing")
        
        Thread(target=self.output_worker, daemon=True).start()
        
        try:
            with sd.InputStream(
                samplerate=FS,
                channels=1,
                callback=self.audio_callback,
                blocksize=FS//10 # 100ms blocks
            ):
                print("Listening... [Speak now]")
                print("Press Ctrl+C to stop")
                while not self.stop_event.is_set():
                    time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop_event.set()
            print("\nTranscription stopped.")
            
        # Final cleanup of any remaining files
        if not self.keep_files:
            self.cleanup_files()

if __name__ == "__main__":
    # Set keep_files=True if you want to retain the audio files
    flt = FixedLatencyTranscriber(keep_files=False)
    flt.run()