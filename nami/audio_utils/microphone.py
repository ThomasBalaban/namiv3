# nami/audio_utils/improved_microphone.py
import os
import sys
import numpy as np
import sounddevice as sd
import time
import soundfile as sf
from faster_whisper import WhisperModel
from ..config import MICROPHONE_DEVICE_ID, FS, CHUNK_DURATION, OVERLAP, MAX_THREADS, SAVE_DIR
from queue import Queue, Empty
from threading import Thread, Event, Lock

# Configuration for Microphone
MODEL_SIZE = "base.en" 
DEVICE = "cpu"
COMPUTE_TYPE = "int8"
SAMPLE_RATE = FS  # Use the same sample rate as desktop audio
CHANNELS = 1

# Global variables for this module
model = None
stop_event = Event()

class MicrophoneTranscriber:
    """Improved microphone transcriber with overlapping chunks like desktop audio"""
    
    def __init__(self, keep_files=False, transcript_manager=None):
        self.FS = SAMPLE_RATE
        self.SAVE_DIR = SAVE_DIR
        self.MAX_THREADS = MAX_THREADS
        self.MODEL_SIZE = MODEL_SIZE
        self.DEVICE = DEVICE
        self.COMPUTE_TYPE = COMPUTE_TYPE
        
        # Set microphone-specific timing (faster than desktop audio)
        self.CHUNK_DURATION = 1.5  # 1.5 seconds for faster response
        self.OVERLAP = 0.5  # 0.5 second overlap
        
        os.makedirs(self.SAVE_DIR, exist_ok=True)
        
        print(f"🎙️ Initializing faster-whisper for Microphone: {self.MODEL_SIZE} on {self.DEVICE}")
        try:
            self.model = WhisperModel(self.MODEL_SIZE, device=self.DEVICE, compute_type=self.COMPUTE_TYPE)
            print("✅ faster-whisper model for Microphone is ready.")
        except Exception as e:
            print(f"❌ Error loading model: {e}")
            raise
            
        self.result_queue = Queue()
        self.stop_event = stop_event
        self.saved_files = []
        self.keep_files = keep_files
        self.active_threads = 0
        self.processing_lock = Event()
        self.processing_lock.set()
        self.last_processed = time.time()
        
        # Audio buffering like desktop audio
        self.audio_buffer = np.array([], dtype=np.float32)
        self.buffer_lock = Lock()
        
        self.transcript_manager = transcript_manager

    def audio_callback(self, indata, frames, timestamp, status):
        """Buffers audio and spawns processing threads for overlapping chunks."""
        try:
            # Resume processing if thread count is low
            if not self.processing_lock.is_set() and self.active_threads < self.MAX_THREADS * 0.5:
                self.processing_lock.set()
                    
            if self.stop_event.is_set():
                return
                
            # Process incoming audio - flatten to mono
            new_audio = indata.flatten().astype(np.float32)
            
            # Skip if audio is too quiet (noise gate)
            rms_amplitude = np.sqrt(np.mean(new_audio**2))
            if rms_amplitude < 0.008:  # Same threshold as original
                return
                
            # Check for invalid data
            if np.isnan(new_audio).any() or np.isinf(new_audio).any():
                print("Warning: Microphone audio contains NaN or Inf values, replacing with zeros")
                new_audio = np.nan_to_num(new_audio, nan=0.0, posinf=0.0, neginf=0.0)
            
            with self.buffer_lock:
                self.audio_buffer = np.concatenate([self.audio_buffer, new_audio])
                
                # Limit buffer size to prevent memory issues (max 30 seconds)
                max_buffer_size = self.FS * 30
                if len(self.audio_buffer) > max_buffer_size:
                    self.audio_buffer = self.audio_buffer[-max_buffer_size:]
                
                # Process when buffer reaches target duration and we're not overloaded
                # FIXED: Use self.CHUNK_DURATION instead of imported CHUNK_DURATION
                chunk_samples = int(self.FS * self.CHUNK_DURATION)
                overlap_samples = int(self.FS * self.OVERLAP)
                advance_samples = chunk_samples - overlap_samples
                
                if (self.processing_lock.is_set() and 
                    len(self.audio_buffer) >= chunk_samples and
                    self.active_threads < self.MAX_THREADS):
                        
                    # Check overall buffer energy before processing
                    buffer_energy = np.abs(self.audio_buffer[:chunk_samples]).mean()
                    if buffer_energy < 0.008:
                        # Skip low-energy chunks, but still advance buffer
                        self.audio_buffer = self.audio_buffer[advance_samples:]
                        return
                        
                    # Copy chunk to prevent modification during processing
                    chunk = self.audio_buffer[:chunk_samples].copy()
                    # Slide buffer forward to create overlap
                    self.audio_buffer = self.audio_buffer[advance_samples:]
                        
                    self.active_threads += 1
                    Thread(target=self.process_chunk, args=(chunk,)).start()
                    self.last_processed = time.time()
                    
                    # If we get too many threads, temporarily pause processing
                    if self.active_threads >= self.MAX_THREADS:
                        self.processing_lock.clear()
                        print(f"Pausing microphone processing - too many active threads: {self.active_threads}")
                        
        except Exception as e:
            print(f"Microphone audio callback error: {e}")
            with self.buffer_lock:
                self.audio_buffer = np.array([], dtype=np.float32)

    def process_chunk(self, chunk):
        """Process audio chunk and transcribe (similar to desktop audio processing)"""
        filename = None
        try:
            # Exit early if we're stopping
            if self.stop_event.is_set():
                return
                
            # Pre-process audio like desktop audio
            # 1. Ensure minimum length
            if len(chunk) < self.FS * 0.5:
                return
                
            # 2. Apply noise gate
            amplitude = np.abs(chunk).mean()
            if amplitude < 0.008:  # Same threshold as original
                return
                
            # 3. Apply dynamic range compression
            threshold = 0.02
            ratio = 0.5
            compressed = np.zeros_like(chunk)
            for i in range(len(chunk)):
                if abs(chunk[i]) > threshold:
                    compressed[i] = chunk[i]
                else:
                    compressed[i] = chunk[i] * ratio
            
            # 4. Normalize audio after compression
            max_val = np.max(np.abs(compressed))
            if max_val < 1e-10:
                return
                
            chunk = compressed / max_val
            
            # 5. Ensure even length
            if len(chunk) % 2 != 0:
                chunk = np.pad(chunk, (0, 1), 'constant')
            
            # Save audio file
            filename = self.save_audio(chunk)
            
            # Transcribe with optimized parameters for speech
            params = {
                "beam_size": 5,  # Higher beam size for better accuracy
                "language": "en",
                "condition_on_previous_text": False
            }
            
            try:
                # Transcribe
                segments, info = self.model.transcribe(chunk, **params)
                text = "".join(seg.text for seg in segments).strip()
                
                # Post-process text
                import re
                text = re.sub(r'(\w)(\s*-\s*\1){3,}', r'\1...', text)
                
                if text and len(text) >= 2:  # Minimum length check
                    self.result_queue.put((text, filename, "microphone", 0.8))
                else:
                    # Clean up file if no text
                    if not self.keep_files and filename and os.path.exists(filename):
                        os.remove(filename)
                    
            except Exception as e:
                print(f"Microphone transcription error: {str(e)}")
                # Clean up file on error
                if not self.keep_files and filename and os.path.exists(filename):
                    try:
                        os.remove(filename)
                    except:
                        pass
                
        except Exception as e:
            print(f"Microphone processing error: {str(e)}")
        finally:
            self.active_threads -= 1

    def save_audio(self, chunk):
        """Save audio chunk to file and return filename"""
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = os.path.join(self.SAVE_DIR, f"microphone_{timestamp}.wav")
        sf.write(filename, chunk, self.FS, subtype='PCM_16')
        self.saved_files.append(filename)
        return filename

    def output_worker(self):
        """Process and display transcription results"""
        while not self.stop_event.is_set():
            try:
                if not self.result_queue.empty():
                    text, filename, audio_type, confidence = self.result_queue.get()
                    
                    if text:
                        # Print in the required format
                        print(f"[Microphone Input] {text}", flush=True)

                        # Clean up file after processing
                        if not self.keep_files and filename and os.path.exists(filename):
                            try: 
                                os.remove(filename)
                            except Exception as e: 
                                print(f"Error removing file: {str(e)}")
                    
                    self.result_queue.task_done()
                time.sleep(0.05)
            except Exception as e:
                print(f"Microphone output worker error: {str(e)}")

    def run(self):
        """Start the audio stream and worker threads"""
        print("DEBUG: Starting run method")
        print(f"DEBUG: hasattr CHUNK_DURATION: {hasattr(self, 'CHUNK_DURATION')}")
        print(f"DEBUG: hasattr OVERLAP: {hasattr(self, 'OVERLAP')}")
        
        if hasattr(self, 'CHUNK_DURATION'):
            print(f"DEBUG: CHUNK_DURATION value: {self.CHUNK_DURATION}")
        if hasattr(self, 'OVERLAP'):
            print(f"DEBUG: OVERLAP value: {self.OVERLAP}")
            
        print(f"Model: {self.MODEL_SIZE.upper()} | Device: {self.DEVICE.upper()}")
        print(f"Microphone Chunk: {self.CHUNK_DURATION}s with {self.OVERLAP}s overlap")

        output_thread = Thread(target=self.output_worker, daemon=True)
        output_thread.start()
        
        try:
            # Use even smaller blocksize for more responsive processing
            blocksize = self.FS // 40  # 25ms blocks for very responsive microphone input
            
            with sd.InputStream(
                device=MICROPHONE_DEVICE_ID,
                samplerate=self.FS,
                channels=CHANNELS,
                callback=self.audio_callback,
                blocksize=blocksize,
                dtype='float32'
            ):
                print("🎤 Listening to microphone with improved real-time processing...")
                while not self.stop_event.is_set():
                    time.sleep(0.1)
                    
        except KeyboardInterrupt:
            print("\nReceived interrupt, stopping microphone transcriber...")
        finally:
            self.stop_event.set()
            print("\nShutting down microphone transcriber...")
            if not self.keep_files:
                time.sleep(0.5)
                for filename in self.saved_files:
                     if os.path.exists(filename):
                        try: 
                            os.remove(filename)
                        except: 
                            pass
            print("🎤 Microphone transcription stopped.")


def transcribe_microphone():
    """Main entry point function for hearing.py to call"""
    try:
        print("Creating MicrophoneTranscriber instance...")
        transcriber = MicrophoneTranscriber()
        print("Running transcriber...")
        transcriber.run()
    except Exception as e:
        print(f"A critical error occurred in the microphone transcriber: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    try:
        transcribe_microphone()
    except KeyboardInterrupt:
        print("\nStopping microphone listener...")
        stop_event.set()