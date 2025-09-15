# Create this as nami/tts_utils/text_utils.py

import re

def strip_sound_effects(text):
    """
    Remove sound effect markers from text for Twitch chat display.
    
    Args:
        text (str): Text that may contain *EFFECTNAME* markers
        
    Returns:
        str: Text with sound effect markers removed and extra spaces cleaned up
        
    Example:
        Input:  "Here is your stupid airhorn *AIRHORN*, okay?"
        Output: "Here is your stupid airhorn , okay?"
    """
    # Remove *EFFECTNAME* patterns
    pattern = r'\*[A-Za-z]+\*'
    cleaned_text = re.sub(pattern, '', text)
    
    # Clean up multiple spaces that might be left behind
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
    
    # Clean up spaces before punctuation
    cleaned_text = re.sub(r'\s+([,.!?;:])', r'\1', cleaned_text)
    
    return cleaned_text.strip()

def has_sound_effects(text):
    """
    Check if text contains any sound effect markers.
    
    Args:
        text (str): Text to check
        
    Returns:
        bool: True if text contains sound effect markers
    """
    pattern = r'\*[A-Za-z]+\*'
    return bool(re.search(pattern, text))

def get_sound_effects_from_text(text):
    """
    Extract all sound effect names from text.
    
    Args:
        text (str): Text that may contain *EFFECTNAME* markers
        
    Returns:
        list: List of effect names found in the text
        
    Example:
        Input:  "That was *AIRHORN* amazing *BONK*!"
        Output: ['AIRHORN', 'BONK']
    """
    pattern = r'\*([A-Za-z]+)\*'
    matches = re.findall(pattern, text)
    return [match.upper() for match in matches]

# Test function
def test_sound_effect_processing():
    """Test the sound effect text processing functions"""
    test_cases = [
        "Here is your stupid airhorn *AIRHORN*, okay?",
        "That was *AIRHORN* amazing *BONK*!",
        "Multiple effects: *AIRHORN* and then *BONK* boom!",
        "No effects in this text",
        "Just *FART* at the end",
        "*BONK* at the beginning only",
        "Spaced out *AIRHORN* text *BONK* here"
    ]
    
    print("=== Sound Effect Text Processing Test ===")
    for test in test_cases:
        cleaned = strip_sound_effects(test)
        effects = get_sound_effects_from_text(test)
        has_effects = has_sound_effects(test)
        
        print(f"Original:    {test}")
        print(f"Cleaned:     {cleaned}")
        print(f"Effects:     {effects}")
        print(f"Has Effects: {has_effects}")
        print()

if __name__ == "__main__":
    test_sound_effect_processing()