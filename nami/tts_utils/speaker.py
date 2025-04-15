from .tts_engine import text_to_speech_file
from .audio_player import play_audio_file
from .voice_config import (
    DEFAULT_STYLE,
    DEFAULT_STYLE_DEGREE,
    DEFAULT_RATE,
    DEFAULT_PITCH,
    PREFERRED_SPEAKER_ID
)

def speak_text(text, style=DEFAULT_STYLE, style_degree=DEFAULT_STYLE_DEGREE, 
              rate=DEFAULT_RATE, pitch=DEFAULT_PITCH, device_id=PREFERRED_SPEAKER_ID):
    """
    Main function to generate speech and play it through the specified device
    
    Args:
        text (str): The text to convert to speech
        style (str): Azure voice style (e.g., "excited", "cheerful")
        style_degree (float): How strongly to apply the style (0.0-2.0)
        rate (float): Speaking rate (1.0 is normal)
        pitch (int): Voice pitch adjustment in percentage
        device_id (int/str): Audio output device ID
        
    Returns:
        bool: True if successful, False if there was an error
    """
    # Generate speech to file
    audio_file = text_to_speech_file(text, style, style_degree, rate, pitch)
    if not audio_file:
        print("❌ Failed to generate speech audio file")
        return False
        
    # Play the file through specified device
    return play_audio_file(audio_file, device_id)