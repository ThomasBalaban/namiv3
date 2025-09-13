# nami/tts_utils/sfx_player.py
import os
import threading
from .audio_player import play_audio_file
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
        return False
    
    if not os.path.exists(sfx_path):
        print(f"❌ Sound effect file not found at path: {sfx_path}")
        return False

    print(f"🔊 Activating sound effect: {sfx_name}")
    # Use the existing play_audio_file function to play the sound
    threading.Thread(target=play_audio_file, args=(sfx_path, PREFERRED_SPEAKER_ID), daemon=True).start()
    return True

def get_available_sound_effects():
    """
    Returns a list of all available sound effects.
    """
    return list(SOUND_EFFECTS.keys())