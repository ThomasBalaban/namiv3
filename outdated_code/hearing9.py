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
MAX_THREADS = 3  # Limit concurrent processing threads

class SpeechMusicClassifier:
    """Simple classifier to detect speech vs music"""
    
    def __init__(self):
        # Track the current audio type and history
        self.current_type = "speech"  # Default to speech
        self.history = []
        self.max_history = 3  # Track last 5 chunks
        self.min_confidence = 0.2  # Minimum confidence to change state
        
    def classify(self, audio_chunk):
        """Classify audio chunk as speech or music using simple features"""
        try:
            # Convert to numpy if tensor
            if torch.is_tensor(audio_chunk):
                audio_chunk = audio_chunk.cpu().numpy()
                
            # Normalize the audio
            audio_chunk = audio_chunk / (np.max(np.abs(audio_chunk)) + 1e-10)
            
            # Extract key features that differentiate speech and music
            
            # 1. Zero-crossing rate
            # Speech typically has moderate zero-crossing rate
            # Music often has higher or more consistent zero-crossing rate
            zero_crossings = np.sum(np.diff(np.signbit(audio_chunk)) != 0)
            zc_rate = zero_crossings / len(audio_chunk)
            
            # 2. Calculate spectral features
            # Get the frequency spectrum
            spectrum = np.abs(np.fft.rfft(audio_chunk))
            freqs = np.fft.rfftfreq(len(audio_chunk), 1/FS)
            
            # 3. Analyze energy in different frequency bands
            # Speech energy is typically concentrated in 300-3000 Hz
            # Music has wider frequency distribution
            
            # Define frequency bands
            bands = [0, 300, 1000, 3000, 8000]
            band_energy = []
            
            for i in range(len(bands)-1):
                mask = (freqs >= bands[i]) & (freqs < bands[i+1])
                band_energy.append(np.sum(spectrum[mask]))
                
            # Normalize band energies
            total_energy = sum(band_energy) + 1e-10
            band_energy_ratio = [e/total_energy for e in band_energy]
            
            # 4. Calculate spectral flux (frame-to-frame spectral change)
            # Split the audio into frames
            frame_size = 400  # 25ms frames
            hop_size = 160    # 10ms hop
            num_frames = (len(audio_chunk) - frame_size) // hop_size
            
            frame_specs = []
            for i in range(num_frames):
                frame = audio_chunk[i*hop_size:i*hop_size+frame_size]
                frame_spec = np.abs(np.fft.rfft(frame))
                frame_specs.append(frame_spec)
                
            # Calculate spectral flux between consecutive frames
            spectral_flux = []
            for i in range(1, len(frame_specs)):
                # Normalize spectra
                spec1 = frame_specs[i-1] / (np.sum(frame_specs[i-1]) + 1e-10)
                spec2 = frame_specs[i] / (np.sum(frame_specs[i]) + 1e-10)
                # Calculate flux
                flux = np.sum((spec2 - spec1)**2)
                spectral_flux.append(flux)
                
            # Average spectral flux
            avg_flux = np.mean(spectral_flux) if spectral_flux else 0
            
            # Collect decision features
            speech_features = 0
            music_features = 0
            
            # Feature 1: Zero crossing rate
            if 0.01 < zc_rate < 0.1:
                speech_features += 1
            elif zc_rate >= 0.1:
                music_features += 1
                
            # Feature 2: Energy in speech band (1000-3000 Hz)
            speech_band_energy = band_energy_ratio[2]  # 1000-3000 Hz band
            if speech_band_energy > 0.5:
                speech_features += 1
            elif band_energy_ratio[1] + band_energy_ratio[3] > 0.6:  # More energy outside speech band
                music_features += 1
                
            # Feature 3: Spectral flux
            # Speech has higher frame-to-frame variation
            if avg_flux > 0.02:
                speech_features += 1
            elif avg_flux < 0.01:
                music_features += 1
                
           # Swap the decision logic
            if speech_features > music_features:
                detected_type = "music"  # Changed from "speech"
                confidence = 0.5 + 0.1 * speech_features
            else:
                detected_type = "speech"  # Changed from "music"
                confidence = 0.5 + 0.1 * music_features
                
            # Update history
            self.history.append(detected_type)
            if len(self.history) > self.max_history:
                self.history.pop(0)
                
            # Only change type if we have consistent evidence
            speech_count = self.history.count("speech")
            music_count = self.history.count("music")
            
            # Require at least 60% agreement to change state
            if speech_count >= 0.6 * len(self.history) and self.current_type != "speech":
                print(f"Audio type changed: {self.current_type} → speech")
                self.current_type = "speech"
            elif music_count >= 0.6 * len(self.history) and self.current_type != "music":
                print(f"Audio type changed: {self.current_type} → music")
                self.current_type = "music"
                
            return self.current_type, confidence
            
        except Exception as e:
            # If any error occurs during classification, stick with current type
            print(f"Classification error: {str(e)}")
            return self.current_type, 0.5


class SpeechMusicTranscriber:
    def __init__(self, keep_files=False, auto_detect=True):
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
        self.debug_mode = False
        
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
                            print(f"\n[{time.strftime('%H:%M:%S')} | {latency:.1f}s] [{audio_type.upper()} {confidence:.2f}] {text}", flush=True)
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
        print(f"SPEECH/MUSIC AUTO-DETECTING TRANSCRIBER")
        print(f"Model: {MODEL_SIZE.upper()} | Device: {DEVICE.upper()}")
        print(f"Chunk: {CHUNK_DURATION}s with {OVERLAP}s overlap")
        print(f"Current audio type: {self.classifier.current_type.upper()}")
        print(f"Auto-detection: {'ON' if self.auto_detect else 'OFF'}")
        print(f"Debug mode: {'OFF'}")
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
                print("Listening... [Speak now]")
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

if __name__ == "__main__":
    # Set keep_files=True if you want to retain the audio files
    transcriber = SpeechMusicTranscriber(keep_files=False, auto_detect=True)
    transcriber.run()