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
            
        device_info = sd.query_devices(device_id)
        if not device_info or device_info['max_output_channels'] <= 0:
            print(f"❌ Invalid output device: {device_id}")
            return False
            
        print(f"🔊 Playing through device ID {device_id}: {device_info['name']}")
        data, samplerate = sf.read(filename)
        
        # Calculate expected duration for logging
        duration_seconds = len(data) / samplerate
        print(f"🔊 Audio duration: {duration_seconds:.1f} seconds")
        
        # Handle sample rate mismatch
        if samplerate != device_info['default_samplerate']:
            print(f"ℹ️ Resampling audio from {samplerate}Hz to {device_info['default_samplerate']}Hz")
            try:
                from scipy import signal
                new_length = int(len(data) * device_info['default_samplerate'] / samplerate)
                data = signal.resample(data, new_length)
                samplerate = device_info['default_samplerate']
            except ImportError:
                print("⚠️ scipy not available, audio quality may be affected")

        # Play the audio - blocking=True should wait until complete
        print("🎵 Now playing audio (blocking)...")
        sd.play(data, samplerate, device=device_id)
        sd.wait()  # Explicitly wait for playback to finish
        print("✅ Audio playback COMPLETE (sd.wait() returned)")
        
        return True
    except Exception as e:
        print(f"❌ Error playing audio file: {str(e)}")
        return False
    finally:
        try:
            os.unlink(filename)
            print(f"🧹 Temporary file removed: {filename}")
        except:
            pass