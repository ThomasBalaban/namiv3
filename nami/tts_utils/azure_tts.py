#!/usr/bin/env python
"""
Azure Text-to-Speech CLI tool
Uses Azure Cognitive Services to convert text to speech and play it through a specified audio device.
"""

from .speaker import speak_text
from .utils import check_dependencies

def main():
    """Main entry point for the CLI application"""
    # Check if required libraries are installed
    missing_libs = check_dependencies()
    
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

if __name__ == "__main__":
    main()