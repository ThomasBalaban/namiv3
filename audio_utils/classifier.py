import numpy as np
import torch
from audio_config import FS

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