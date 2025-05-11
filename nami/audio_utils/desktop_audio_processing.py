import os
import numpy as np
import re
import torch
from scipy import signal
from nami.config import FS, DEVICE

class AudioProcessing:
    def __init__(self, processor):
        self.processor = processor
        
    def process_chunk(self, chunk):
        """Process audio chunk and transcribe based on type with enhanced error prevention"""
        try:
            # Exit early if we're stopping
            if self.processor.transcriber.stop_event.is_set():
                self.processor.transcriber.active_threads -= 1
                return
                
            # Pre-process audio
            # 1. Ensure minimum length
            if len(chunk) < FS * 0.5:
                self.processor.transcriber.active_threads -= 1
                return
                
            # 2. Apply noise gate - filter out very quiet audio completely
            amplitude = np.abs(chunk).mean()
            if amplitude < 0.005:  # Increased threshold for better noise rejection
                self.processor.transcriber.active_threads -= 1
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
                self.processor.transcriber.active_threads -= 1
                return
                
            chunk = compressed / max_val
            
            # 5. Ensure even length
            if len(chunk) % 2 != 0:
                chunk = np.pad(chunk, (0, 1), 'constant')
            
            # Save audio file
            filename = self.processor.save_audio(chunk)
            
            # Classify audio type if auto_detect is enabled
            if self.processor.transcriber.auto_detect:
                audio_type, confidence = self.processor.transcriber.classifier.classify(chunk)
            else:
                audio_type = self.processor.transcriber.classifier.current_type
                confidence = 0.8
                
            # Skip processing completely if confidence is too low
            if confidence < 0.4:
                self.processor.transcriber.active_threads -= 1
                
                # Clean up file
                if not self.processor.transcriber.keep_files and filename and os.path.exists(filename):
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
                # Process and transcribe
                result = self._transcribe_audio(chunk, params)
                text = result.get("text", "").strip()
                
                # Post-process text - remove repeated characters (like B-B-B-B)
                text = re.sub(r'(\w)(\s*-\s*\1){3,}', r'\1...', text)
                
                # Handle empty or very short results based on audio type
                min_length = 2 if audio_type == "speech" else 4  # Higher threshold for music
                
                if text and len(text) >= min_length:
                    self.processor.transcriber.result_queue.put((text, filename, audio_type, confidence))
                else:
                    # Silently clean up files with no text
                    if not self.processor.transcriber.keep_files and filename and os.path.exists(filename):
                        os.remove(filename)
                    
            except Exception as e:
                print(f"Transcription error: {str(e)}")
                
                # Clean up file on error
                if not self.processor.transcriber.keep_files and filename and os.path.exists(filename):
                    try:
                        os.remove(filename)
                    except:
                        pass
                
        except Exception as e:
            print(f"Processing error: {str(e)}")
        finally:
            self.processor.transcriber.active_threads -= 1
            
    def _transcribe_audio(self, chunk, params):
        """Handle the transcription with proper error handling"""
        # Ensure input is properly formatted and has the right shape
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
            raise ValueError("Processed audio too quiet")
        
        # Run transcription with memory error protection
        try:
            # FIXED: Convert NumPy array to PyTorch tensor with explicit dtype
            if not torch.is_tensor(whisper_input):
                whisper_input = torch.tensor(whisper_input, dtype=torch.float32)
            
            # Safe transcription call with proper dtype
            result = self.processor.transcriber.model.transcribe(whisper_input, **params)
            return result
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
                result = self.processor.transcriber.model.transcribe(filtered_input_tensor, **basic_params)
                return result
            else:
                # Not a shape error, re-raise
                raise