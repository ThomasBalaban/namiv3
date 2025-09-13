# Updated nami/tts_utils/tts_engine.py

import azure.cognitiveservices.speech as speechsdk
from xml.sax.saxutils import escape
import tempfile
import os
import re
from .voice_config import (
    AZURE_SPEECH_KEY,
    AZURE_SPEECH_REGION,
    AZURE_VOICE_NAME,
    DEFAULT_STYLE,
    DEFAULT_STYLE_DEGREE,
    DEFAULT_PITCH,
    DEFAULT_RATE
)

# Sound effect URL base - serving locally from your UI server
SOUND_EFFECTS_BASE_URL = "http://localhost:8002/audio_effects"

# Map of effect names to files and fallback text
# Temporary public URLs for testing
SOUND_EFFECT_MAP = {
    'airhorn': {'file': 'https://www2.cs.uic.edu/~i101/SoundFiles/CantinaBand3.wav', 'fallback': '*AIRHORN*'},
    'bonk': {'file': 'https://www2.cs.uic.edu/~i101/SoundFiles/CantinaBand3.wav', 'fallback': '*BONK*'},
    'fart': {'file': 'https://www2.cs.uic.edu/~i101/SoundFiles/CantinaBand3.wav', 'fallback': '*FART*'}
}

def process_sound_effects(text):
    """
    Process text to convert *EFFECTNAME* markers into SSML audio tags.
    """
    def replace_effect(match):
        effect_name = match.group(1).lower()
        if effect_name in SOUND_EFFECT_MAP:
            effect_info = SOUND_EFFECT_MAP[effect_name]
            # Use your local server instead of Google Drive
            audio_url = f"{SOUND_EFFECTS_BASE_URL}/{effect_info['file']}"
            fallback = effect_info['fallback']
            return f'<audio src="{audio_url}">{fallback}</audio>'
        else:
            # Unknown effect, leave as is
            return match.group(0)
    
    # Find *EFFECTNAME* patterns and replace with SSML audio tags
    pattern = r'\*([A-Za-z]+)\*'
    processed_text = re.sub(pattern, replace_effect, text)
    
    return processed_text

def text_to_speech_file(text, style=DEFAULT_STYLE, style_degree=DEFAULT_STYLE_DEGREE, 
                        rate=DEFAULT_RATE, pitch=DEFAULT_PITCH):
    """
    Convert text to speech and save as a WAV file, with sound effect support
    Returns the filename if successful, None if failed
    """
    try:
        # Validate core configuration
        if not AZURE_SPEECH_KEY or not AZURE_SPEECH_REGION:
            raise ValueError("Azure credentials not configured properly")
            
        # Configure speech config
        speech_config = speechsdk.SpeechConfig(
            subscription=AZURE_SPEECH_KEY,
            region=AZURE_SPEECH_REGION
        )
        
        # Set voice and print the voice we're using
        speech_config.speech_synthesis_voice_name = AZURE_VOICE_NAME
        print(f"🗣️ Using voice: {AZURE_VOICE_NAME}")
        
        # Set high-quality audio format - Mac optimized (48kHz)
        speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Riff48Khz16BitMonoPcm)
        print("🔊 Using high-quality 48kHz audio format")
        
        # Create a temporary file to store the audio
        temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        temp_file.close()
        
        # Configure audio output to file
        audio_config = speechsdk.audio.AudioOutputConfig(filename=temp_file.name)
        print(f"📝 Saving speech to temporary file: {temp_file.name}")
        
        # Create synthesizer with file output
        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config,
            audio_config=audio_config
        )

        # Process sound effects and build SSML
        processed_text = process_sound_effects(text)
        print(f"🎵 Original text: {text}")
        print(f"🎵 Processed text: {processed_text}")
        
        ssml = _build_ssml(processed_text, style, style_degree, rate, pitch)
        print(f"🎵 Generated SSML: {ssml[:200]}...")

        # Synthesize with detailed error handling
        print("🎵 Generating speech with sound effects to file...")
        result = synthesizer.speak_ssml_async(ssml).get()

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            print("✅ Synthesis with sound effects successful")
            return temp_file.name
        else:
            print(f"❌ Synthesis to file failed: {result.reason}")
            if result.reason == speechsdk.ResultReason.Canceled:
                cancellation = result.cancellation_details
                print(f"Cancellation reason: {cancellation.reason}")
                if cancellation.reason == speechsdk.CancellationReason.Error:
                    print(f"Error details: {cancellation.error_details}")
            
            # Try to clean up the file if synthesis failed
            try:
                os.unlink(temp_file.name)
            except:
                pass
                
            return None

    except Exception as e:
        print(f"🔥 Critical error in synthesis: {str(e)}")
        return None

def _build_ssml(text, style, style_degree, rate, pitch):
    """Helper to build SSML markup for Azure TTS with sound effect support"""
    ssml = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" 
          xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="en-US">
        <voice name="{AZURE_VOICE_NAME}">
            <prosody rate="{rate}" pitch="{pitch}%">"""

    if style:
        ssml += f'<mstts:express-as style="{style}" styledegree="{style_degree}">'
        # Note: We don't escape the text here because it now contains SSML audio tags
        ssml += text
        ssml += '</mstts:express-as>'
    else:
        # Note: We don't escape the text here because it now contains SSML audio tags
        ssml += text

    ssml += "</prosody></voice></speak>"
    return ssml

def get_available_sound_effects():
    """Returns a list of available sound effect names"""
    return list(SOUND_EFFECT_MAP.keys())

def test_sound_effect_processing():
    """Test function to see how sound effect processing works"""
    test_cases = [
        "That's absolutely *AIRHORN* hilarious!",
        "You're such a *BONK* idiot sometimes",
        "Well that was a load of *FART* if I've ever heard one",
        "Multiple effects: *AIRHORN* and then *BONK* boom!",
        "Unknown effect *EXPLOSION* should stay as is"
    ]
    
    print("=== Sound Effect Processing Test ===")
    for test in test_cases:
        processed = process_sound_effects(test)
        print(f"Original:  {test}")
        print(f"Processed: {processed}")
        print()

if __name__ == "__main__":
    test_sound_effect_processing()