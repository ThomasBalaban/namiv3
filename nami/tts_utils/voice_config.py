# Configuration settings for Azure TTS

try:
    from ..config import (
        AZURE_SPEECH_KEY,
        AZURE_SPEECH_REGION,
        AZURE_VOICE_NAME,
        SPEECH_OUTPUT_SOUND_DEVICE
    )
except (ImportError, ModuleNotFoundError):
    # Fallback to environment variables if needed
    import os
    AZURE_SPEECH_KEY = os.environ.get("AZURE_SPEECH_KEY")
    AZURE_SPEECH_REGION = os.environ.get("AZURE_SPEECH_REGION")
    AZURE_VOICE_NAME = os.environ.get("AZURE_VOICE_NAME", "en-US-JennyMultilingualNeural")
    SPEECH_OUTPUT_SOUND_DEVICE = os.environ.get("SPEECH_OUTPUT_SOUND_DEVICE", 0)

# Default voice settings
DEFAULT_STYLE = "excited"
DEFAULT_STYLE_DEGREE = 1.7
DEFAULT_PITCH = 6
DEFAULT_RATE = 1.05

# Set the device ID to the configured value
PREFERRED_SPEAKER_ID = SPEECH_OUTPUT_SOUND_DEVICE