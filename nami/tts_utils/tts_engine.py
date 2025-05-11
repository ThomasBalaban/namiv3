import azure.cognitiveservices.speech as speechsdk
from xml.sax.saxutils import escape
import tempfile
import os
from .voice_config import (
    AZURE_SPEECH_KEY,
    AZURE_SPEECH_REGION,
    AZURE_VOICE_NAME,
    DEFAULT_STYLE,
    DEFAULT_STYLE_DEGREE,
    DEFAULT_PITCH,
    DEFAULT_RATE
)

def text_to_speech_file(text, style=DEFAULT_STYLE, style_degree=DEFAULT_STYLE_DEGREE, 
                        rate=DEFAULT_RATE, pitch=DEFAULT_PITCH):
    """
    Convert text to speech and save as a WAV file
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

        # Build SSML with proper escaping
        ssml = _build_ssml(text, style, style_degree, rate, pitch)

        # Synthesize with detailed error handling
        print("🎵 Generating speech to file...")
        result = synthesizer.speak_ssml_async(ssml).get()

        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            print("✅ Synthesis to file successful")
            return temp_file.name
        else:
            print(f"❌ Synthesis to file failed: {result.reason}")
            if result.reason == speechsdk.ResultReason.Canceled:
                cancellation = result.cancellation_details
                print(f"Reason: {cancellation.reason}")
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
    """Helper to build SSML markup for Azure TTS"""
    ssml = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" 
          xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="en-US">
        <voice name="{AZURE_VOICE_NAME}">
            <prosody rate="{rate}" pitch="{pitch}%">"""

    if style:
        ssml += f'<mstts:express-as style="{style}" styledegree="{style_degree}">'
        ssml += escape(text)
        ssml += '</mstts:express-as>'
    else:
        ssml += escape(text)

    ssml += "</prosody></voice></speak>"
    return ssml