import os
import time
import numpy as np
import soundfile as sf
import re
from threading import Thread
from scipy import signal

class AudioProcessor:
    def __init__(self, transcriber):
        self.transcriber = transcriber
        self.audio_buffer = np.array([], dtype=np.float32)
        self.last_noise_log = 0  # For throttling noise messages
        
    def audio_callback(self, indata, frames, timestamp, status):
        """Process incoming audio data with enhanced error handling and noise control"""
        try:
            # Import here to avoid circular imports
            try:
                from nami.config import FS, CHUNK_DURATION, OVERLAP, MAX_THREADS
            except ImportError:
                FS = 16000
                CHUNK_DURATION = 3
                OVERLAP = 0.5
                MAX_THREADS = 4
                
            # Check if we should resume processing
            if not self.transcriber.processing_lock.is_set() and self.transcriber.active_threads < MAX_THREADS * 0.5:
                # Resume processing if thread count is low enough
                self.transcriber.processing_lock.set()
                    
            if status:
                print(f"Audio status: {status}")
            
            # Skip if stopped
            if self.transcriber.stop_event.is_set():
                return
                
            # Process all incoming audio
            new_audio = np.squeeze(indata).astype(np.float32)
            
            # Skip processing if audio is too quiet (global noise gate)
            rms_amplitude = np.sqrt(np.mean(new_audio**2))
            if rms_amplitude < 0.0003:  # Very quiet audio
                if time.time() - self.last_noise_log > 5:
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
                print("Warning: Audio buffer too large, trimming")
            
            # Process when buffer reaches target duration and we're not overloaded
            if (self.transcriber.processing_lock.is_set() and 
                len(self.audio_buffer) >= FS * CHUNK_DURATION and
                self.transcriber.active_threads < MAX_THREADS):
                    
                # Check overall buffer energy before processing
                buffer_energy = np.abs(self.audio_buffer[:FS*CHUNK_DURATION]).mean()
                if buffer_energy < 0.0005:
                    # Skip low-energy chunks, but still advance buffer
                    self.audio_buffer = self.audio_buffer[FS*(CHUNK_DURATION-OVERLAP):]
                    return
                    
                # Copy chunk to prevent modification during processing
                chunk = self.audio_buffer[:FS*CHUNK_DURATION].copy()
                self.audio_buffer = self.audio_buffer[FS*(CHUNK_DURATION-OVERLAP):]
                    
                self.transcriber.active_threads += 1
                Thread(target=self.process_chunk, args=(chunk,)).start()
                self.transcriber.last_processed = time.time()
                
                # If we get too many threads, temporary pause processing
                if self.transcriber.active_threads >= MAX_THREADS * 0.8:
                    self.transcriber.processing_lock.clear()
                    print(f"Pausing processing - too many active threads: {self.transcriber.active_threads}")
                    
        except Exception as e:
            print(f"Audio callback error: {e}")
            # Try to recover
            self.audio_buffer = np.array([], dtype=np.float32)
    
    def process_chunk(self, chunk):
        """Process audio chunk and transcribe based on type with enhanced error prevention"""
        try:
            # Exit early if we're stopping
            if self.transcriber.stop_event.is_set():
                self.transcriber.active_threads -= 1
                return
                
            # Pre-process audio
            # 1. Ensure minimum length
            if len(chunk) < 8000:  # Need at least 0.5 second at 16kHz
                self.transcriber.active_threads -= 1
                return
                
            # 2. Apply noise gate - filter out very quiet audio completely
            amplitude = np.abs(chunk).mean()
            if amplitude < 0.005:  # Increased threshold for better noise rejection
                self.transcriber.active_threads -= 1
                return
                
            # 3. Normalize audio
            max_val = np.max(np.abs(chunk))
            if max_val < 1e-10:  # Avoid division by zero
                self.transcriber.active_threads -= 1
                return
                
            chunk = chunk / max_val
            
            # Save audio file
            filename = self.save_audio(chunk)
            
            # Classify audio type if auto_detect is enabled
            if self.transcriber.auto_detect:
                audio_type, confidence = self.transcriber.classifier.classify(chunk)
            else:
                audio_type = self.transcriber.classifier.current_type
                confidence = 0.8
                
            # Skip processing completely if confidence is too low
            if confidence < 0.4:
                self.transcriber.active_threads -= 1
                
                # Clean up file
                if not self.transcriber.keep_files and filename and os.path.exists(filename):
                    os.remove(filename)
                return
                
            # Use ONLY parameters that faster-whisper definitely supports
            params = {
                "beam_size": 1,  # Simple beam search
                "language": "en"  # Force English
            }
            
            # Transcribe with error handling
            try:
                # Process and transcribe
                result = self._transcribe_audio(chunk, params)
                
                # Extract text from faster-whisper result
                if hasattr(result, '__iter__') and len(result) == 2:
                    # result is (segments, info) tuple from faster-whisper
                    segments, info = result
                    text = " ".join([segment.text for segment in segments]).strip()
                else:
                    # Fallback
                    text = str(result).strip()
                
                # Post-process text - remove repeated characters (like B-B-B-B)
                text = re.sub(r'(\w)(\s*-\s*\1){3,}', r'\1...', text)
                
                # Handle empty or very short results
                min_length = 2
                
                if text and len(text) >= min_length:
                    self.transcriber.result_queue.put((text, filename, audio_type, confidence))
                    print(f"✅ Transcribed ({audio_type}): {text[:50]}...")
                else:
                    # Silently clean up files with no text
                    if not self.transcriber.keep_files and filename and os.path.exists(filename):
                        os.remove(filename)
                    
            except Exception as e:
                print(f"❌ Transcription error: {str(e)}")
                
                # Clean up file on error
                if not self.transcriber.keep_files and filename and os.path.exists(filename):
                    try:
                        os.remove(filename)
                    except:
                        pass
                
        except Exception as e:
            print(f"❌ Processing error: {str(e)}")
        finally:
            self.transcriber.active_threads -= 1
            
    def _transcribe_audio(self, chunk, params):
        """Handle the transcription with proper error handling for faster-whisper"""
        
        # Import FS here to avoid circular imports
        try:
            from nami.config import FS
        except ImportError:
            FS = 16000  # Default sample rate
        
        # Ensure input is properly formatted and has the right shape
        whisper_input = chunk.astype(np.float32)
        
        # Verify that the array is not empty
        if whisper_input.size == 0:
            raise ValueError("Empty audio chunk")
            
        # Check for NaN or Inf values
        if np.isnan(whisper_input).any() or np.isinf(whisper_input).any():
            raise ValueError("Audio contains NaN or Inf values")
        
        # Ensure sample rate matches what the model expects (16000 Hz for Whisper)
        if FS != 16000:
            try:
                # Use scipy for resampling
                number_of_samples = round(len(whisper_input) * 16000 / FS)
                whisper_input = signal.resample(whisper_input, number_of_samples)
                whisper_input = whisper_input.astype(np.float32)
            except Exception as e:
                print(f"⚠️ Resampling error: {str(e)}")
                # Continue with original sample rate
        
        # Check the processed shape
        if whisper_input.size == 0:
            raise ValueError("Resampled audio is empty")
        
        # Create a contiguous copy of the array with the right dtype
        whisper_input = np.ascontiguousarray(whisper_input, dtype=np.float32)
            
        # Make sure content meets threshold before processing
        content_energy = np.sqrt(np.mean(whisper_input**2))
        if content_energy < 0.01:
            raise ValueError("Processed audio too quiet")
        
        # Run transcription with faster-whisper
        try:
            # Call faster-whisper transcribe method with minimal, safe parameters
            result = self.transcriber.model.transcribe(whisper_input, **params)
            return result
            
        except Exception as e:
            # If any parameters cause issues, try with absolute minimum
            if "unexpected keyword argument" in str(e):
                print(f"⚠️ Parameter error, trying with no parameters: {str(e)}")
                
                try:
                    # Try with absolutely no parameters
                    result = self.transcriber.model.transcribe(whisper_input)
                    return result
                except Exception as e2:
                    print(f"❌ Even minimal transcription failed: {str(e2)}")
                    raise e2
            else:
                # Re-raise other errors
                raise e
                
    def save_audio(self, chunk):
        # Import here to avoid circular imports
        try:
            from nami.config import FS, SAVE_DIR
        except ImportError:
            FS = 16000
            SAVE_DIR = "audio_captures"
            
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = os.path.join(SAVE_DIR, f"fixed_{timestamp}.wav")
        sf.write(filename, chunk, FS, subtype='PCM_16')
        self.transcriber.saved_files.append(filename)
        return filename