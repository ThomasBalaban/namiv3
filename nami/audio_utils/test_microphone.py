#!/usr/bin/env python3
"""
Test script to verify microphone transcription is working
"""

import numpy as np
import sounddevice as sd
import time
from faster_whisper import WhisperModel

def test_microphone():
    """Test microphone input and transcription"""
    
    # Configuration
    SAMPLE_RATE = 16000
    DURATION = 3  # seconds
    DEVICE_ID = 4  # Your Scarlett Solo 4th Gen
    
    print("🎤 Microphone Test")
    print("=" * 30)
    
    # List available devices
    print("📱 Available input devices:")
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            marker = " ← SELECTED" if i == DEVICE_ID else ""
            print(f"  {i}: {device['name']}{marker}")
    
    # Initialize Whisper model
    print(f"\n🤖 Loading Whisper model...")
    try:
        model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
        print("✅ Model loaded successfully")
    except Exception as e:
        print(f"❌ Error loading model: {e}")
        return False
    
    # Test recording
    print(f"\n🎤 Testing microphone recording...")
    print(f"   Device: {DEVICE_ID}")
    print(f"   Sample Rate: {SAMPLE_RATE} Hz")
    print(f"   Duration: {DURATION} seconds")
    
    try:
        print("\n🔴 Recording... Speak now!")
        audio = sd.rec(
            int(DURATION * SAMPLE_RATE), 
            samplerate=SAMPLE_RATE, 
            channels=1, 
            device=DEVICE_ID,
            dtype='float32'
        )
        sd.wait()  # Wait until recording is finished
        print("⏹️ Recording finished")
        
        # Check audio level
        audio_flat = audio.flatten()
        rms_level = np.sqrt(np.mean(audio_flat**2))
        max_level = np.max(np.abs(audio_flat))
        
        print(f"\n📊 Audio Analysis:")
        print(f"   RMS Level: {rms_level:.4f}")
        print(f"   Max Level: {max_level:.4f}")
        print(f"   Length: {len(audio_flat)} samples ({len(audio_flat)/SAMPLE_RATE:.1f}s)")
        
        if rms_level < 0.001:
            print("⚠️ Audio level very low - check microphone connection/gain")
            return False
        elif rms_level < 0.01:
            print("⚠️ Audio level low - you might need to speak louder or increase gain")
        else:
            print("✅ Audio level good")
        
        # Test transcription
        print(f"\n🔄 Transcribing...")
        try:
            segments, info = model.transcribe(
                audio_flat,
                beam_size=1,
                language="en"
            )
            
            text = "".join(segment.text for segment in segments).strip()
            
            print(f"\n📝 Transcription Results:")
            print(f"   Language: {info.language} (probability: {info.language_probability:.2f})")
            print(f"   Text: '{text}'")
            
            if text:
                print("✅ Transcription successful!")
                return True
            else:
                print("⚠️ No text transcribed - try speaking louder or closer to microphone")
                return False
                
        except Exception as e:
            print(f"❌ Transcription error: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Recording error: {e}")
        return False

def main():
    success = test_microphone()
    
    if success:
        print("\n🎉 Microphone test successful!")
        print("Your microphone should work with the full system.")
    else:
        print("\n❌ Microphone test failed.")
        print("Check your microphone connection and try adjusting the device ID in config.py")

if __name__ == "__main__":
    main()