import sounddevice as sd
import soundfile as sf
import os
from .voice_config import PREFERRED_SPEAKER_ID

def play_audio_file(filename, device_id=PREFERRED_SPEAKER_ID):
    """
    Play an audio file through the specified output device
    """
    try:
        if not os.path.exists(filename):
            print(f"❌ Audio file not found: {filename}")
            return False
            
        # Get device info for proper configuration
        device_info = sd.query_devices(device_id)
        if not device_info or device_info['max_output_channels'] <= 0:
            print(f"❌ Invalid output device: {device_id}")
            return False
            
        # Load audio file
        print(f"🔊 Playing through device ID {device_id}: {device_info['name']}")
        data, samplerate = sf.read(filename)
        
        # Handle sample rate mismatch - this is critical for macOS quality
        if samplerate != device_info['default_samplerate']:
            print(f"ℹ️ Resampling audio from {samplerate}Hz to {device_info['default_samplerate']}Hz")
            try:
                # Try to use scipy for better quality resampling if available
                from scipy import signal
                new_length = int(len(data) * device_info['default_samplerate'] / samplerate)
                data = signal.resample(data, new_length)
                samplerate = device_info['default_samplerate']
                print("✅ Resampling complete using scipy (high quality)")
            except ImportError:
                print("⚠️ scipy not available, audio quality may be affected")
                # If scipy is not available, we'll use the default sample rate anyway

        # Play the audio file through specified device
        print("🎵 Now playing audio...")
        sd.play(data, samplerate, device=device_id, blocking=True)
        print("✅ Audio playback complete")
        
        return True
    except Exception as e:
        print(f"❌ Error playing audio file: {str(e)}")
        return False
    finally:
        # Always clean up the temporary file
        try:
            os.unlink(filename)
            print(f"🧹 Temporary file removed: {filename}")
        except:
            pass