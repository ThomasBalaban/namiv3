import azure.cognitiveservices.speech as speechsdk
from xml.sax.saxutils import escape
import sounddevice as sd
import soundfile as sf
import tempfile
import os
from config import (
    AZURE_SPEECH_KEY,
    AZURE_SPEECH_REGION,
    AZURE_VOICE_NAME,
    SPEECH_OUTPUT_SOUND_DEVICE
)

# Set the device ID to the configured value
PREFERRED_SPEAKER_ID = SPEECH_OUTPUT_SOUND_DEVICE

# Your favorite voice settings as defaults
DEFAULT_STYLE = "excited"
DEFAULT_STYLE_DEGREE = 1.7
DEFAULT_PITCH = 6
DEFAULT_RATE = 1.05

def text_to_speech_file(text, style=DEFAULT_STYLE, style_degree=DEFAULT_STYLE_DEGREE, rate=DEFAULT_RATE, pitch=DEFAULT_PITCH):
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
        
        # Set voice and print the voice we're using for debugging
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

def speak_text(text, style=DEFAULT_STYLE, style_degree=DEFAULT_STYLE_DEGREE, rate=DEFAULT_RATE, pitch=DEFAULT_PITCH, device_id=PREFERRED_SPEAKER_ID):
    """
    Main function to generate speech and play it through the specified device
    """
    # Generate speech to file
    audio_file = text_to_speech_file(text, style, style_degree, rate, pitch)
    if not audio_file:
        print("❌ Failed to generate speech audio file")
        return False
        
    # Play the file through specified device
    return play_audio_file(audio_file, device_id)

if __name__ == "__main__":
    # Check if required libraries are installed
    missing_libs = []
    try:
        import soundfile
    except ImportError:
        missing_libs.append("soundfile")
        
    try:
        import scipy
    except ImportError:
        missing_libs.append("scipy")
    
    if missing_libs:
        print("❌ The following libraries are recommended for optimal audio quality:")
        for lib in missing_libs:
            print(f"pip install {lib}")
        if "soundfile" in missing_libs:
            exit(1)
    
    # Direct input mode - just keep asking for text until the user types 'exit'
    print("🎙️ Azure TTS ready! Type 'exit' to quit.")
    
    while True:
        text = input("> ")
        if text.lower() == 'exit':
            print("Goodbye! 👋")
            break
        
        # Speak with the optimal parameters
        speak_text(text)