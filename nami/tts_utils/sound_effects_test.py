# Create this as nami/tts_utils/sound_effects_test.py

import sys
import os
from pathlib import Path

# Add the nami directory to Python path
nami_dir = Path(__file__).parent.parent
sys.path.insert(0, str(nami_dir))

def test_sound_effects():
    """Test the sound effects processing and TTS generation"""
    
    # Test 1: Check if audio files exist
    print("=== Testing Audio Files ===")
    audio_effects_dir = nami_dir / "audio_effects"
    print(f"Looking for audio files in: {audio_effects_dir}")
    
    required_files = ['airhorn.wav', 'bonk.wav', 'fart.wav']
    all_files_exist = True
    
    for filename in required_files:
        file_path = audio_effects_dir / filename
        if file_path.exists():
            size = file_path.stat().st_size
            print(f"✅ {filename} - {size:,} bytes")
        else:
            print(f"❌ {filename} - NOT FOUND")
            all_files_exist = False
    
    if not all_files_exist:
        print("\n🚨 Some audio files are missing!")
        print("Run: python nami/setup_audio_effects.py")
        return False
    
    # Test 2: Check sound effect processing
    print("\n=== Testing Sound Effect Processing ===")
    try:
        from tts_utils.tts_engine import process_sound_effects, test_sound_effect_processing
        test_sound_effect_processing()
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    
    # Test 3: Test actual TTS generation (if Azure credentials are available)
    print("\n=== Testing TTS Generation ===")
    try:
        from tts_utils.tts_engine import text_to_speech_file
        from tts_utils.voice_config import AZURE_SPEECH_KEY, AZURE_SPEECH_REGION
        
        if not AZURE_SPEECH_KEY or not AZURE_SPEECH_REGION:
            print("⚠️ Azure credentials not configured - skipping TTS test")
            print("   (Sound effect processing still works for text display)")
            return True
        
        test_text = "Here's your stupid airhorn *AIRHORN*, okay?"
        print(f"Testing with: {test_text}")
        
        audio_file = text_to_speech_file(test_text)
        if audio_file:
            print(f"✅ TTS generation successful: {audio_file}")
            
            # Clean up the test file
            try:
                os.unlink(audio_file)
                print("🧹 Test file cleaned up")
            except:
                pass
            
            return True
        else:
            print("❌ TTS generation failed")
            return False
            
    except Exception as e:
        print(f"❌ TTS test error: {e}")
        return False

def test_ui_server_audio_serving():
    """Test if the UI server can serve audio files"""
    print("\n=== Testing UI Server Audio Serving ===")
    try:
        import requests
        
        # Test if the UI server is running and can serve audio files
        test_urls = [
            'http://localhost:8002/audio_effects/airhorn.wav',
            'http://localhost:8002/audio_effects/bonk.wav',
            'http://localhost:8002/audio_effects/fart.wav'
        ]
        
        for url in test_urls:
            try:
                response = requests.head(url, timeout=2)
                if response.status_code == 200:
                    print(f"✅ {url} - accessible")
                else:
                    print(f"❌ {url} - status {response.status_code}")
            except requests.exceptions.ConnectionError:
                print(f"⚠️ {url} - UI server not running")
            except Exception as e:
                print(f"❌ {url} - error: {e}")
                
    except ImportError:
        print("⚠️ requests library not available for testing URL access")

if __name__ == "__main__":
    print("🎵 Sound Effects System Test\n")
    
    success = test_sound_effects()
    test_ui_server_audio_serving()
    
    if success:
        print("\n🎉 Sound effects system is ready!")
        print("\nTo use in your bot responses:")
        print('  "That was *AIRHORN* amazing!"')
        print('  "You deserve a *BONK* for that"')
        print('  "What a load of *FART*"')
    else:
        print("\n❌ Some tests failed. Check the output above for details.")