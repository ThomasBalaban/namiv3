import os
import sys
import azure.cognitiveservices.speech as speechsdk
import threading

# Add the root directory to the path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import config
except ImportError:
    print("\033[91m[WARNING] Could not import config module.\033[0m")
    config = None

class AzureTTS:
    def __init__(self, voice_name="en-US-JennyNeural"):
        """
        Initialize Azure TTS with the given voice.
        
        Retrieves Azure Speech Service credentials from config.py
        Falls back to environment variables if not found in config
        """
        # First try to get credentials from config.py
        self.speech_key = None
        self.speech_region = None
        
        # Try to get from config module
        if config:
            self.speech_key = getattr(config, 'AZURE_SPEECH_KEY', None)
            self.speech_region = getattr(config, 'AZURE_SPEECH_REGION', None)
        
        # Fall back to environment variables if not in config
        if not self.speech_key:
            self.speech_key = os.environ.get('AZURE_SPEECH_KEY')
        if not self.speech_region:
            self.speech_region = os.environ.get('AZURE_SPEECH_REGION')
        
        if not self.speech_key or not self.speech_region:
            print("\033[91m[WARNING] Azure Speech credentials not found in config.py or environment variables.\033[0m")
            print("\033[91mPlease add AZURE_SPEECH_KEY and AZURE_SPEECH_REGION to your config.py file.\033[0m")
            self.enabled = False
        else:
            self.enabled = True
        
        # Set fixed voice (will not change)
        self.voice_name = voice_name
        
        # TTS is always enabled
        self.tts_enabled = True
        
        print(f"\033[92m[TTS] Azure TTS initialized with voice: {voice_name}\033[0m")
    
    def speak(self, text, blocking=False):
        """
        Convert text to speech using Azure TTS.
        
        Args:
            text: The text to convert to speech
            blocking: If True, wait for the speech to complete before returning
        """
        if not self.enabled or not self.tts_enabled:
            return False
        
        # Define a function that will run in a thread
        def speak_in_thread():
            try:
                # Configure speech config
                speech_config = speechsdk.SpeechConfig(subscription=self.speech_key, region=self.speech_region)
                speech_config.speech_synthesis_voice_name = self.voice_name
                
                # Create a speech synthesizer
                speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)
                
                # Start speech synthesis
                result = speech_synthesizer.speak_text_async(text).get()
                
                # Check result
                if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                    print("\033[92m[TTS] Speech synthesis completed.\033[0m")
                elif result.reason == speechsdk.ResultReason.Canceled:
                    cancellation_details = result.cancellation_details
                    print(f"\033[91m[TTS] Speech synthesis canceled: {cancellation_details.reason}\033[0m")
                    if cancellation_details.reason == speechsdk.CancellationReason.Error:
                        print(f"\033[91m[TTS] Error details: {cancellation_details.error_details}\033[0m")
            except Exception as e:
                print(f"\033[91m[TTS] Error in speech synthesis: {str(e)}\033[0m")
        
        # Run in a separate thread if non-blocking
        if not blocking:
            thread = threading.Thread(target=speak_in_thread)
            thread.daemon = True
            thread.start()
            return True
        else:
            speak_in_thread()
            return True
    
    def set_voice(self, voice_name):
        """Change the voice used for TTS"""
        self.voice_name = voice_name
        print(f"\033[93m[TTS] Voice set to: {voice_name}\033[0m")
        
    def enable(self, enabled=True):
        """Enable or disable TTS"""
        self.tts_enabled = enabled
        status = "enabled" if enabled else "disabled"
        print(f"\033[93m[TTS] Text-to-speech {status}\033[0m")
        
    def is_enabled(self):
        """Check if TTS is enabled and properly configured"""
        return self.enabled and self.tts_enabled

# Singleton instance
tts_engine = AzureTTS()

def speak(text, blocking=False):
    """Helper function to use the singleton TTS instance"""
    return tts_engine.speak(text, blocking)

def set_voice(voice_name):
    """Helper function to set the voice of the singleton TTS instance"""
    tts_engine.set_voice(voice_name)
    
def enable_tts(enabled=True):
    """Helper function to enable/disable the singleton TTS instance"""
    tts_engine.enable(enabled)
    
def is_tts_enabled():
    """Helper function to check if TTS is enabled"""
    return tts_engine.is_enabled()
import os
import sys
import azure.cognitiveservices.speech as speechsdk
import threading

# Add the root directory to the path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import config
except ImportError:
    print("\033[91m[WARNING] Could not import config module.\033[0m")
    config = None

class AzureTTS:
    def __init__(self, voice_name="en-US-JennyNeural"):
        """
        Initialize Azure TTS with the given voice.
        
        Retrieves Azure Speech Service credentials from config.py
        Falls back to environment variables if not found in config
        """
        # First try to get credentials from config.py
        self.speech_key = None
        self.speech_region = None
        
        # Try to get from config module
        if config:
            self.speech_key = getattr(config, 'AZURE_SPEECH_KEY', None)
            self.speech_region = getattr(config, 'AZURE_SPEECH_REGION', None)
        
        # Fall back to environment variables if not in config
        if not self.speech_key:
            self.speech_key = os.environ.get('AZURE_SPEECH_KEY')
        if not self.speech_region:
            self.speech_region = os.environ.get('AZURE_SPEECH_REGION')
        
        if not self.speech_key or not self.speech_region:
            print("\033[91m[WARNING] Azure Speech credentials not found in config.py or environment variables.\033[0m")
            print("\033[91mPlease add AZURE_SPEECH_KEY and AZURE_SPEECH_REGION to your config.py file.\033[0m")
            self.enabled = False
        else:
            self.enabled = True
        
        # Set fixed voice (will not change)
        self.voice_name = voice_name
        
        # TTS is always enabled
        self.tts_enabled = True
        
        print(f"\033[92m[TTS] Azure TTS initialized with voice: {voice_name}\033[0m")
    
    def speak(self, text, blocking=False):
        """
        Convert text to speech using Azure TTS.
        
        Args:
            text: The text to convert to speech
            blocking: If True, wait for the speech to complete before returning
        """
        if not self.enabled or not self.tts_enabled:
            return False
        
        # Define a function that will run in a thread
        def speak_in_thread():
            try:
                # Configure speech config
                speech_config = speechsdk.SpeechConfig(subscription=self.speech_key, region=self.speech_region)
                speech_config.speech_synthesis_voice_name = self.voice_name
                
                # Create a speech synthesizer
                speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)
                
                # Start speech synthesis
                result = speech_synthesizer.speak_text_async(text).get()
                
                # Check result
                if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                    print("\033[92m[TTS] Speech synthesis completed.\033[0m")
                elif result.reason == speechsdk.ResultReason.Canceled:
                    cancellation_details = result.cancellation_details
                    print(f"\033[91m[TTS] Speech synthesis canceled: {cancellation_details.reason}\033[0m")
                    if cancellation_details.reason == speechsdk.CancellationReason.Error:
                        print(f"\033[91m[TTS] Error details: {cancellation_details.error_details}\033[0m")
            except Exception as e:
                print(f"\033[91m[TTS] Error in speech synthesis: {str(e)}\033[0m")
        
        # Run in a separate thread if non-blocking
        if not blocking:
            thread = threading.Thread(target=speak_in_thread)
            thread.daemon = True
            thread.start()
            return True
        else:
            speak_in_thread()
            return True
    
    def set_voice(self, voice_name):
        """Change the voice used for TTS"""
        self.voice_name = voice_name
        print(f"\033[93m[TTS] Voice set to: {voice_name}\033[0m")
        
    def enable(self, enabled=True):
        """Enable or disable TTS"""
        self.tts_enabled = enabled
        status = "enabled" if enabled else "disabled"
        print(f"\033[93m[TTS] Text-to-speech {status}\033[0m")
        
    def is_enabled(self):
        """Check if TTS is enabled and properly configured"""
        return self.enabled and self.tts_enabled

# Singleton instance
tts_engine = AzureTTS()

def speak(text, blocking=False):
    """Helper function to use the singleton TTS instance"""
    return tts_engine.speak(text, blocking)

def set_voice(voice_name):
    """Helper function to set the voice of the singleton TTS instance"""
    tts_engine.set_voice(voice_name)
    
def enable_tts(enabled=True):
    """Helper function to enable/disable the singleton TTS instance"""
    tts_engine.enable(enabled)
    
def is_tts_enabled():
    """Helper function to check if TTS is enabled"""
    return tts_engine.is_enabled()