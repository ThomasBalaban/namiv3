# this file is poorly named, it does desktop transcription 
import os
import time
import numpy as np
import sounddevice as sd
import soundfile as sf
import whisper
import torch
from threading import Thread, Event
from queue import Queue

# Use full package imports
from audio_config import FS, CHUNK_DURATION, OVERLAP, MODEL_SIZE, DEVICE, SAVE_DIR, MAX_THREADS
from audio_utils.classifier import SpeechMusicClassifier

class SpeechMusicTranscriber:
    def __init__(self, keep_files=False, auto_detect=True, debug_mode=False):
        os.makedirs(SAVE_DIR, exist_ok=True)
        
        print(f"Loading Whisper model: {MODEL_SIZE} on {DEVICE}")
        try:
            self.model = whisper.load_model(MODEL_SIZE, device=DEVICE)
            if DEVICE == "cuda":
                self.model = self.model.half()
        except Exception as e:
            print(f"Error loading model: {e}")
            raise
            
        self.result_queue = Queue()
        self.stop_event = Event()
        self.audio_buffer = np.array([], dtype=np.float32)
        self.last_processed = time.time()
        self.saved_files = []  # Track saved files for cleanup
        self.keep_files = keep_files  # Flag to control file retention
        self.active_threads = 0  # Track number of active processing threads
        self.processing_lock = Event()  # Used to control processing flow
        self.processing_lock.set()  # Initially allow processing
        
        # Speech/Music classifier
        self.classifier = SpeechMusicClassifier()
        self.auto_detect = auto_detect
        self.debug_mode = debug_mode
        
    def audio_callback(self, indata, frames, timestamp, status):
        """Process incoming audio data with error handling"""
        try:
            if status:
                print(f"Audio status: {status}")
            
            # Skip if stopped
            if self.stop_event.is_set():
                return
                
            # Process all incoming audio
            new_audio = np.squeeze(indata).astype(np.float32)
            self.audio_buffer = np.concatenate([self.audio_buffer, new_audio])
            
            # Process when buffer reaches target duration and we're not overloaded
            if (self.processing_lock.is_set() and 
                len(self.audio_buffer) >= FS * CHUNK_DURATION and
                self.active_threads < MAX_THREADS):
                    
                # Copy chunk to prevent modification during processing
                chunk = self.audio_buffer[:FS*CHUNK_DURATION].copy()
                self.audio_buffer = self.audio_buffer[FS*(CHUNK_DURATION-OVERLAP):]
                
                # Skip very quiet audio
                if np.abs(chunk).mean() < 0.0005:
                    return
                    
                self.active_threads += 1
                Thread(target=self.process_chunk, args=(chunk,)).start()
                self.last_processed = time.time()
        except Exception as e:
            print(f"Audio callback error: {e}")
            # Try to recover
            self.audio_buffer = np.array([], dtype=np.float32)
            
    def process_chunk(self, chunk):
        """Process audio chunk and transcribe based on type"""
        try:
            # Exit early if we're stopping
            if self.stop_event.is_set():
                self.active_threads -= 1
                return
                
            # Pre-process audio
            # 1. Ensure minimum length
            if len(chunk) < FS * 0.5:
                if self.debug_mode:
                    print("Chunk too short, skipping")
                self.active_threads -= 1
                return
                
            # 2. Normalize audio
            max_val = np.max(np.abs(chunk))
            if max_val < 1e-10:  # Avoid division by zero
                if self.debug_mode:
                    print("Chunk is silent, skipping")
                self.active_threads -= 1
                return
                
            chunk = chunk / max_val
            
            # 3. Ensure even length
            if len(chunk) % 2 != 0:
                chunk = np.pad(chunk, (0, 1), 'constant')
            
            # Save audio file
            filename = self.save_audio(chunk)
            
            # Classify audio type if auto_detect is enabled
            if self.auto_detect:
                audio_type, confidence = self.classifier.classify(chunk)
            else:
                audio_type = self.classifier.current_type
                confidence = 0.8
                
            # Optimize parameters for audio type
            if audio_type == "speech":
                params = {
                    "fp16": (DEVICE == "cuda"),
                    "beam_size": 1,  # Reduced for stability
                    "temperature": 0.0,
                    "no_speech_threshold": 0.6
                }
            else:  # music
                params = {
                    "fp16": (DEVICE == "cuda"),
                    "beam_size": 1,  # Reduced for stability
                    "temperature": 0.3, 
                    "no_speech_threshold": 0.4
                }
            
            # Transcribe with error handling
            try:
                # Ensure input is properly formatted
                whisper_input = chunk.astype(np.float32)
                
                # Verify that the array is not empty
                if whisper_input.size == 0:
                    raise ValueError("Empty audio chunk")
                
                # Run transcription
                result = self.model.transcribe(whisper_input, **params)
                
                # Process the result
                text = result.get("text", "").strip()
                if text:
                    self.result_queue.put((text, filename, audio_type, confidence))
                elif self.debug_mode:
                    # Only report empty text in debug mode
                    self.result_queue.put(("", filename, audio_type, confidence))
                else:
                    # Silently clean up files with no text
                    if not self.keep_files and filename and os.path.exists(filename):
                        os.remove(filename)
                    
            except Exception as e:
                print(f"Transcription error: {str(e)}")
                # Continue operation despite errors
                if self.debug_mode:
                    self.result_queue.put((f"[Error: {type(e).__name__}]", filename, audio_type, confidence))
                
        except Exception as e:
            print(f"Processing error: {str(e)}")
        finally:
            self.active_threads -= 1
            
    def output_worker(self):
        """Process and display transcription results"""
        while not self.stop_event.is_set():
            try:
                if not self.result_queue.empty():
                    text, filename, audio_type, confidence = self.result_queue.get()
                    latency = time.time() - self.last_processed
                    
                    # Format output based on whether we have text
                    if text:
                        if text.startswith("[Error"):
                            print(f"\n[{time.strftime('%H:%M:%S')} | {latency:.1f}s] [{audio_type.upper()} {confidence:.2f}] {text}", flush=True)
                        else:
                            if self.debug_mode:
                                print(f"\n[{time.strftime('%H:%M:%S')} | {latency:.1f}s] [{audio_type.upper()} {confidence:.2f}] {text}", flush=True)
                            else:
                                print(f"[{time.strftime('%H:%M:%S')} | {latency:.1f}s] [{audio_type.upper()} {confidence:.2f}] {text}", flush=True)
                    elif self.debug_mode:
                        print(f"\n[{time.strftime('%H:%M:%S')} | {latency:.1f}s] [{audio_type.upper()} {confidence:.2f} - NO TEXT]", flush=True)
                    
                    # Delete the file after processing if not keeping files
                    if not self.keep_files and filename and os.path.exists(filename):
                        try:
                            os.remove(filename)
                        except Exception as e:
                            if self.debug_mode:
                                print(f"Error removing file: {str(e)}")
                    
                    self.result_queue.task_done()
                time.sleep(0.05)
            except Exception as e:
                print(f"Output worker error: {str(e)}")
    
    def set_audio_type(self, audio_type):
        """Manual override of audio type"""
        valid_types = ["speech", "music"]
        if audio_type in valid_types:
            prev_type = self.classifier.current_type
            self.classifier.current_type = audio_type
            # Also set history to this type for persistence
            self.classifier.history = [audio_type] * self.classifier.max_history
            # print(f"Audio type changed: {prev_type.upper()} → {audio_type.upper()}")
            return True
        return False
        
    def toggle_auto_detect(self):
        """Toggle automatic audio type detection"""
        self.auto_detect = not self.auto_detect
        print(f"Automatic detection: {'ON' if self.auto_detect else 'OFF'}")
        
    def toggle_debug(self):
        """Toggle debug mode"""
        self.debug_mode = not self.debug_mode
        print(f"Debug mode: {'ON' if self.debug_mode else 'OFF'}")
        
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
        print(f"Model: {MODEL_SIZE.upper()} | Device: {DEVICE.upper()}")
        print(f"Chunk: {CHUNK_DURATION}s with {OVERLAP}s overlap")
        print(f"Debug mode: {self.debug_mode}")

        # Only print detailed info in debug mode
        if self.debug_mode:
            print(f"SPEECH/MUSIC AUTO-DETECTING TRANSCRIBER")
            print(f"Current audio type: {self.classifier.current_type.upper()}")
            print(f"Auto-detection: {'ON' if self.auto_detect else 'OFF'}")

        print(f"Commands:")
        print(f"  s - Switch to SPEECH mode")
        print(f"  m - Switch to MUSIC mode")
        print(f"  a - Toggle auto-detection")
        print(f"  d - Toggle debug mode")
        print(f"  q - Quit")
        
        # Start output worker thread
        output_thread = Thread(target=self.output_worker, daemon=True)
        output_thread.start()
        
        # Set up keyboard input thread
        def keyboard_handler():
            while not self.stop_event.is_set():
                try:
                    key = input()
                    if key == 's':
                        self.set_audio_type("speech")
                    elif key == 'm':
                        self.set_audio_type("music")
                    elif key == 'a':
                        self.toggle_auto_detect()
                    elif key == 'd':
                        self.toggle_debug()
                    elif key == 'q':
                        self.stop_event.set()
                        break
                except Exception as e:
                    if self.stop_event.is_set():
                        break
                    time.sleep(0.1)
        
        keyboard_thread = Thread(target=keyboard_handler, daemon=True)
        keyboard_thread.start()
        
        try:
            # Start audio input stream
            with sd.InputStream(
                samplerate=FS,
                channels=1,
                callback=self.audio_callback,
                blocksize=FS//10 # 100ms blocks
            ):
                print("Listening to desktop...")
                print("Press Ctrl+C to stop")
                
                # Main loop - just wait for Ctrl+C or 'q'
                while not self.stop_event.is_set():
                    time.sleep(0.1)
                    
        except KeyboardInterrupt:
            print("\nReceived interrupt, stopping...")
        finally:
            self.stop_event.set()
            print("\nShutting down...")
            
            # Final cleanup of any remaining files
            if not self.keep_files:
                self.cleanup_files()