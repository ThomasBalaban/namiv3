# nami/tts_utils/sfx_player.py
import os
import threading
import sounddevice as sd
import soundfile as sf
from .voice_config import PREFERRED_SPEAKER_ID

# A simple dictionary to map sound effect names to file paths
SOUND_EFFECTS = {
    'airhorn': 'audio_effects/airhorn.wav',
    'fart': 'audio_effects/fart.wav',
    'bonk': 'audio_effects/bonk.wav',
    # Add other sound effects here
}

def play_sound_effect_threaded(sfx_name: str):
    """
    Plays a pre-defined sound effect in a non-blocking thread.
    This is necessary to not halt the main program loop.
    """
    sfx_path = SOUND_EFFECTS.get(sfx_name.lower())
    if not sfx_path:
        print(f"❌ Sound effect '{sfx_name}' not found.")
        print(f"Available effects: {list(SOUND_EFFECTS.keys())}")
        return False
    
    # Construct full path - go up from tts_utils to nami root
    full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), sfx_path)
    
    if not os.path.exists(full_path):
        print(f"❌ Sound effect file not found at path: {full_path}")
        return False

    print(f"🔊 Activating sound effect: {sfx_name}")
    
    # Use threading to play the sound without blocking
    def play_sound():
        try:
            # Load and play the audio file
            data, samplerate = sf.read(full_path)
            sd.play(data, samplerate, device=PREFERRED_SPEAKER_ID)
            sd.wait()  # Wait until sound is finished
            print(f"✅ Sound effect '{sfx_name}' completed")
        except Exception as e:
            print(f"❌ Error playing sound effect '{sfx_name}': {e}")
    
    threading.Thread(target=play_sound, daemon=True).start()
    return True

def get_available_sound_effects():
    """
    Returns a list of all available sound effects.
    """
    return list(SOUND_EFFECTS.keys())

def test_sound_effects():
    """Test all available sound effects"""
    print("🎵 Testing all sound effects...")
    for effect_name in SOUND_EFFECTS.keys():
        print(f"Testing {effect_name}...")
        play_sound_effect_threaded(effect_name)
        # Small delay between tests
        import time
        time.sleep(2)

if __name__ == "__main__":
    test_sound_effects()