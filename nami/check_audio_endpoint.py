# Save this as nami/check_audio_endpoint.py

from pathlib import Path

# Save this as nami/test_azure_access.py

import azure.cognitiveservices.speech as speechsdk
import tempfile
import os
from pathlib import Path

def test_azure_audio_access():
    """Test if Azure TTS can actually access our local audio files"""
    
    print("🔍 Testing Azure TTS Audio Access")
    print("=" * 50)
    
    # Get Azure credentials
    try:
        from tts_utils.voice_config import AZURE_SPEECH_KEY, AZURE_SPEECH_REGION, AZURE_VOICE_NAME
        if not AZURE_SPEECH_KEY or not AZURE_SPEECH_REGION:
            print("❌ Azure credentials not configured")
            return
    except ImportError:
        print("❌ Could not import Azure credentials")
        return
    
    # Configure Azure TTS
    speech_config = speechsdk.SpeechConfig(
        subscription=AZURE_SPEECH_KEY,
        region=AZURE_SPEECH_REGION
    )
    speech_config.speech_synthesis_voice_name = AZURE_VOICE_NAME
    
    # Create temp file for output
    temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    temp_file.close()
    
    audio_config = speechsdk.audio.AudioOutputConfig(filename=temp_file.name)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
    
    # Test 1: Simple text without audio tags
    print("=== Test 1: Simple Text ===")
    simple_ssml = f'''<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">
        <voice name="{AZURE_VOICE_NAME}">
            Hello, this is a simple test without audio effects.
        </voice>
    </speak>'''
    
    result = synthesizer.speak_ssml_async(simple_ssml).get()
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        print("✅ Simple text synthesis works")
    else:
        print(f"❌ Simple text failed: {result.reason}")
        return
    
    # Test 2: SSML with local audio URL
    print("\n=== Test 2: SSML with Local Audio URL ===")
    local_audio_ssml = f'''<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">
        <voice name="{AZURE_VOICE_NAME}">
            Here is the test <audio src="http://localhost:8002/audio_effects/airhorn.wav">AIRHORN</audio> sound effect.
        </voice>
    </speak>'''
    
    print("SSML being sent to Azure:")
    print(local_audio_ssml)
    print()
    
    result = synthesizer.speak_ssml_async(local_audio_ssml).get()
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        print("✅ Local audio URL synthesis completed")
        print("   (But this doesn't mean the audio was actually included)")
    else:
        print(f"❌ Local audio URL failed: {result.reason}")
        if result.reason == speechsdk.ResultReason.Canceled:
            cancellation = result.cancellation_details
            print(f"Cancellation reason: {cancellation.reason}")
            if cancellation.reason == speechsdk.CancellationReason.Error:
                print(f"Error details: {cancellation.error_details}")
    
    # Test 3: Try with a public URL (if available)
    print("\n=== Test 3: SSML with Public URL ===")
    # Using a known public audio file for testing
    public_audio_ssml = f'''<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">
        <voice name="{AZURE_VOICE_NAME}">
            Here is a test with public audio <audio src="https://www2.cs.uic.edu/~i101/SoundFiles/CantinaBand3.wav">music</audio> file.
        </voice>
    </speak>'''
    
    result = synthesizer.speak_ssml_async(public_audio_ssml).get()
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        print("✅ Public audio URL synthesis completed")
    else:
        print(f"❌ Public audio URL failed: {result.reason}")
        if result.reason == speechsdk.ResultReason.Canceled:
            cancellation = result.cancellation_details
            print(f"Cancellation reason: {cancellation.reason}")
            if cancellation.reason == speechsdk.CancellationReason.Error:
                print(f"Error details: {cancellation.error_details}")
    
    # Clean up
    try:
        os.unlink(temp_file.name)
    except:
        pass
    
    print("\n=== Analysis ===")
    print("If Test 2 fails but Test 3 succeeds, Azure TTS cannot access localhost URLs.")
    print("This is expected - Azure's cloud servers can't reach your local machine.")
    print("\nSolutions:")
    print("1. Use a public URL to host the audio files")
    print("2. Use a tunneling service like ngrok")
    print("3. Upload files to Azure Blob Storage or similar")

if __name__ == "__main__":
    test_azure_audio_access()
