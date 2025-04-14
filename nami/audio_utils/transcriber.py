import os
import time
import numpy as np
import sounddevice as sd
import soundfile as sf
import whisper
import torch
import re
import argparse
from threading import Thread, Event, Timer
from scipy import signal
from queue import Queue
from nami.config import FS, CHUNK_DURATION, OVERLAP, MODEL_SIZE, DEVICE, SAVE_DIR, MAX_THREADS
from nami.audio_utils.classifier import SpeechMusicClassifier

class SpeechMusicTranscriber:
    def __init__(self, keep_files=False, auto_detect=True, debug_mode=False, transcript_manager=None):
        os.makedirs(SAVE_DIR, exist_ok=True)
        
        print(f"Loading Whisper model: {MODEL_SIZE} on {DEVICE}")
        try:            
            self.model = whisper.load_model(MODEL_SIZE)
            
            # Move model to specified device if needed
            if DEVICE == "cuda" and hasattr(self.model, "to"):
                self.model = self.model.to(DEVICE)
                # For CUDA devices, we can use half precision
                self.model = self.model.half()
                
        except Exception as e:
            print(f"Error loading model: {e}")
            print(f"Detailed error information to help fix the issue:")
            import traceback
            traceback.print_exc()
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
        self.last_noise_log = 0  # For throttling noise messages
        
        # Speech/Music classifier
        self.classifier = SpeechMusicClassifier()
        self.auto_detect = auto_detect
        self.debug_mode = debug_mode
        
        # Transcript Manager for persistent storage
        self.transcript_manager = transcript_manager

    def audio_callback(self, indata, frames, timestamp, status):
        """Process incoming audio data with enhanced error handling and noise control"""
        try:
            # Check if we should resume processing
            if not self.processing_lock.is_set() and self.active_threads < MAX_THREADS * 0.5:
                # Resume processing if thread count is low enough
                self.processing_lock.set()
                if self.debug_mode:
                    print("Resuming audio processing")
                    
            if status and self.debug_mode:
                print(f"Audio status: {status}")
            
            # Skip if stopped
            if self.stop_event.is_set():
                return
                
            # Process all incoming audio
            new_audio = np.squeeze(indata).astype(np.float32)
            
            # Skip processing if audio is too quiet (global noise gate)
            rms_amplitude = np.sqrt(np.mean(new_audio**2))
            if rms_amplitude < 0.0003:  # Very quiet audio
                if self.debug_mode and time.time() - self.last_noise_log > 5:
                    print(f"Input too quiet: {rms_amplitude:.6f} RMS, skipping")
                    self.last_noise_log = time.time()
                return
                
            # Check for invalid data early
            if np.isnan(new_audio).any() or np.isinf(new_audio).any():
                print("Warning: Input audio contains NaN or Inf values, replacing with zeros")
                new_audio = np.nan_to_num(new_audio, nan=0.0, posinf=0.0, neginf=0.0)
                
            # Add the new audio to buffer
            self.audio_buffer = np.concatenate([self.audio_buffer, new_audio])
            
            # Limit buffer size to prevent memory issues (max 30 seconds)
            max_buffer_size = FS * 30
            if len(self.audio_buffer) > max_buffer_size:
                # Keep only the most recent data
                self.audio_buffer = self.audio_buffer[-max_buffer_size:]
                if self.debug_mode:
                    print("Warning: Audio buffer too large, trimming")
            
            # Process when buffer reaches target duration and we're not overloaded
            if (self.processing_lock.is_set() and 
                len(self.audio_buffer) >= FS * CHUNK_DURATION and
                self.active_threads < MAX_THREADS):
                    
                # Check overall buffer energy before processing
                buffer_energy = np.abs(self.audio_buffer[:FS*CHUNK_DURATION]).mean()
                if buffer_energy < 0.0005:
                    # Skip low-energy chunks, but still advance buffer
                    self.audio_buffer = self.audio_buffer[FS*(CHUNK_DURATION-OVERLAP):]
                    return
                    
                # Copy chunk to prevent modification during processing
                chunk = self.audio_buffer[:FS*CHUNK_DURATION].copy()
                self.audio_buffer = self.audio_buffer[FS*(CHUNK_DURATION-OVERLAP):]
                    
                self.active_threads += 1
                Thread(target=self.process_chunk, args=(chunk,)).start()
                self.last_processed = time.time()
                
                # If we get too many threads, temporary pause processing
                if self.active_threads >= MAX_THREADS * 0.8:
                    self.processing_lock.clear()
                    if self.debug_mode:
                        print(f"Pausing processing - too many active threads: {self.active_threads}")
                    
        except Exception as e:
            print(f"Audio callback error: {e}")
            # Try to recover
            self.audio_buffer = np.array([], dtype=np.float32)

    def process_chunk(self, chunk):
        """Process audio chunk and transcribe based on type with enhanced error prevention"""
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
                
            # 2. Apply noise gate - filter out very quiet audio completely
            amplitude = np.abs(chunk).mean()
            if amplitude < 0.005:  # Increased threshold for better noise rejection
                if self.debug_mode:
                    print(f"Chunk too quiet ({amplitude:.6f}), skipping")
                self.active_threads -= 1
                return
                
            # 3. Apply dynamic range compression to reduce background noise
            # Simple compression: reduce volume of quiet parts
            threshold = 0.02
            ratio = 0.5  # Compression ratio
            compressed = np.zeros_like(chunk)
            for i in range(len(chunk)):
                if abs(chunk[i]) > threshold:
                    compressed[i] = chunk[i]
                else:
                    compressed[i] = chunk[i] * ratio
            
            # 4. Normalize audio after compression
            max_val = np.max(np.abs(compressed))
            if max_val < 1e-10:  # Avoid division by zero
                self.active_threads -= 1
                return
                
            chunk = compressed / max_val
            
            # 5. Ensure even length
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
                
            # Skip processing completely if confidence is too low
            if confidence < 0.4:
                if self.debug_mode:
                    print(f"Low classification confidence ({confidence:.2f}), skipping")
                self.active_threads -= 1
                
                # Clean up file
                if not self.keep_files and filename and os.path.exists(filename):
                    os.remove(filename)
                return
                
            # Optimize parameters for audio type
            if audio_type == "speech":
                params = {
                    "fp16": (DEVICE == "cuda"),
                    "beam_size": 1,  # Reduced for stability
                    "temperature": 0.0,
                    "no_speech_threshold": 0.6,
                    "condition_on_previous_text": False  # Reset context
                }
            else:  # music
                params = {
                    "fp16": (DEVICE == "cuda"),
                    "beam_size": 1,  # Reduced for stability
                    "temperature": 0.3, 
                    "no_speech_threshold": 0.3,  # Lower to catch words in music
                    "condition_on_previous_text": False  # Reset context
                }
            
            # Transcribe with error handling
            try:
                # Ensure input is properly formatted and has the right shape
                # FIXED: Explicitly use float32 data type (not double/float64)
                whisper_input = chunk.astype(np.float32)
                
                # Verify that the array is not empty
                if whisper_input.size == 0:
                    raise ValueError("Empty audio chunk")
                    
                # Check for NaN or Inf values
                if np.isnan(whisper_input).any() or np.isinf(whisper_input).any():
                    raise ValueError("Audio contains NaN or Inf values")
                
                # Apply low-pass filter to remove high-frequency noise
                try:
                    nyquist = FS / 2.0
                    cutoff = min(8000 / nyquist, 0.99)  # Ensure cutoff is < 1
                    b, a = signal.butter(5, cutoff, 'low')
                    whisper_input = signal.filtfilt(b, a, whisper_input)
                    # FIXED: Ensure it stays as float32 after filtering
                    whisper_input = whisper_input.astype(np.float32)
                except Exception as e:
                    print(f"Filter error: {str(e)}, skipping filtering")
                    # Continue without filtering
                    
                # Ensure sample rate matches what the model expects (16000 Hz for Whisper)
                # If FS is not 16000, we need to resample
                if FS != 16000:
                    try:
                        import librosa
                        whisper_input = librosa.resample(whisper_input, orig_sr=FS, target_sr=16000)
                        # FIXED: Ensure it stays as float32 after resampling
                        whisper_input = whisper_input.astype(np.float32)
                    except ImportError:
                        # Fallback if librosa not available
                        number_of_samples = round(len(whisper_input) * 16000 / FS)
                        whisper_input = signal.resample(whisper_input, number_of_samples)
                        # FIXED: Ensure it stays as float32 after resampling
                        whisper_input = whisper_input.astype(np.float32)
                
                # Check the processed shape
                if whisper_input.size == 0:
                    raise ValueError("Resampled audio is empty")
                
                # FIX FOR NEGATIVE STRIDE ISSUE: Create a contiguous copy of the array with the right dtype
                whisper_input = np.ascontiguousarray(whisper_input, dtype=np.float32)
                    
                # Additional validation - convert to tensor and check
                if torch.is_tensor(whisper_input):
                    if torch.isnan(whisper_input).any() or torch.isinf(whisper_input).any():
                        raise ValueError("Audio tensor contains NaN or Inf values after preprocessing")
                    # FIXED: Ensure tensor has the right dtype
                    whisper_input = whisper_input.to(torch.float32)
                else:
                    # Convert to tensor to check for NaN/Inf in way model will see it
                    # FIXED: Explicitly set the tensor dtype to float32
                    temp_tensor = torch.tensor(whisper_input, dtype=torch.float32)
                    if torch.isnan(temp_tensor).any() or torch.isinf(temp_tensor).any():
                        raise ValueError("Audio tensor contains NaN or Inf values after preprocessing")
                
                # Make sure content meets threshold before processing
                content_energy = np.sqrt(np.mean(whisper_input**2))
                if content_energy < 0.01:
                    if self.debug_mode:
                        print(f"Processed audio energy too low: {content_energy:.6f}")
                    raise ValueError("Processed audio too quiet")
                
                # Run transcription with memory error protection
                try:
                    # FIXED: Convert NumPy array to PyTorch tensor with explicit dtype
                    if not torch.is_tensor(whisper_input):
                        whisper_input = torch.tensor(whisper_input, dtype=torch.float32)
                    
                    # Safe transcription call with proper dtype
                    result = self.model.transcribe(whisper_input, **params)
                except RuntimeError as e:
                    # Check if this is a memory/tensor shape error
                    if "reshape" in str(e) or "size" in str(e) or "shape" in str(e) or "CUDA" in str(e) or "stride" in str(e) or "dtype" in str(e):
                        # Try again with even stricter preprocessing
                        print(f"Transcription runtime error: {str(e)}")
                        print("Attempting fallback transcription...")
                        
                        # More aggressive preprocessing
                        filtered_input = signal.medfilt(whisper_input.cpu().numpy() if torch.is_tensor(whisper_input) else whisper_input, 5)  # Median filter to remove spikes
                        filtered_input = filtered_input[len(filtered_input)//10:-len(filtered_input)//10]  # Trim edges
                        
                        # ADDITIONAL FIX: Ensure contiguous memory layout with correct dtype
                        filtered_input = np.ascontiguousarray(filtered_input, dtype=np.float32)
                        
                        if len(filtered_input) < 8000:  # Need at least 0.5s at 16kHz
                            raise ValueError("Audio too short after filtering")
                        
                        # Try again with simpler params
                        basic_params = {
                            "fp16": False,  # Use fp32 for better numerical stability
                            "beam_size": 1,
                            "temperature": 0.0,
                            "condition_on_previous_text": False
                        }
                        
                        # FIXED: Convert to torch tensor with explicit dtype before transcribing
                        filtered_input_tensor = torch.tensor(filtered_input, dtype=torch.float32)
                        result = self.model.transcribe(filtered_input_tensor, **basic_params)
                    else:
                        # Not a shape error, re-raise
                        raise
                
                # Process the result
                text = result.get("text", "").strip()
                
                # Post-process text - remove repeated characters (like B-B-B-B)
                text = re.sub(r'(\w)(\s*-\s*\1){3,}', r'\1...', text)
                
                # Handle empty or very short results based on audio type
                min_length = 2 if audio_type == "speech" else 4  # Higher threshold for music
                
                if text and len(text) >= min_length:
                    self.result_queue.put((text, filename, audio_type, confidence))
                elif self.debug_mode:
                    # Only report empty text in debug mode
                    self.result_queue.put((f"[Empty or too short: '{text}']", filename, audio_type, confidence))
                else:
                    # Silently clean up files with no text
                    if not self.keep_files and filename and os.path.exists(filename):
                        os.remove(filename)
                    
            except Exception as e:
                print(f"Transcription error: {str(e)}")
                # Continue operation despite errors
                if self.debug_mode:
                    self.result_queue.put((f"[Error: {type(e).__name__}]", filename, audio_type, confidence))
                
                # Clean up file on error
                if not self.keep_files and filename and os.path.exists(filename):
                    try:
                        os.remove(filename)
                    except:
                        pass
                
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
                    timestamp = time.strftime("%H:%M:%S")
                    
                    # Format output based on whether we have text
                    if text:
                        if text.startswith("[Error"):
                            print(f"\n[{timestamp} | {latency:.1f}s] [{audio_type.upper()} {confidence:.2f}] {text}", flush=True)
                        else:
                            if self.debug_mode:
                                print(f"\n[{timestamp} | {latency:.1f}s] [{audio_type.upper()} {confidence:.2f}] {text}", flush=True)
                            else:
                                print(f"[{timestamp} | {latency:.1f}s] [{audio_type.upper()} {confidence:.2f}] {text}", flush=True)
                            
                            # Publish to transcript manager if available
                            if self.transcript_manager:
                                metadata = {
                                    "audio_type": audio_type,
                                    "confidence": float(confidence),
                                    "latency": float(latency)
                                }
                                self.transcript_manager.publish_transcript(
                                    source="desktop",
                                    text=text,
                                    metadata=metadata
                                )
                                
                    elif self.debug_mode:
                        print(f"\n[{timestamp} | {latency:.1f}s] [{audio_type.upper()} {confidence:.2f} - NO TEXT]", flush=True)
                    
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
            print(f"Audio type changed: {prev_type.upper()} → {audio_type.upper()}")
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
        print(f"Debug mode: {'ON' if self.debug_mode else 'OFF'}")

        # Only print detailed info in debug mode
        if self.debug_mode:
            print(f"SPEECH/MUSIC AUTO-DETECTING TRANSCRIBER")
            print(f"Current audio type: {self.classifier.current_type.upper()}")
            print(f"Auto-detection: {'ON' if self.auto_detect else 'OFF'}")
            if self.transcript_manager:
                print(f"Transcript Manager: Connected")

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

# Add this code to make the module executable
def main():
    parser = argparse.ArgumentParser(description="Desktop audio transcription with Whisper")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--keep-files", action="store_true", help="Keep audio files after transcription")
    parser.add_argument("--manual", action="store_true", help="Disable auto-detection of audio type")
    args = parser.parse_args()
    
    try:
        transcriber = SpeechMusicTranscriber(
            keep_files=args.keep_files,
            auto_detect=not args.manual,
            debug_mode=args.debug
        )
        transcriber.run()
    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as e:
        print(f"Error: {str(e)}")

# This will make the module executable when run directly
if __name__ == "__main__":
    main()