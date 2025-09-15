# Updated nami/tts_utils/content_filter.py - Fix the censored text

import re
import os
from pathlib import Path

def load_banned_words():
    """
    Load banned words from the hard_filter.py file.
    Returns a list of banned words/phrases.
    """
    try:
        # Try to import from the new location first
        from .hard_filter import banned_words
        return [word.lower() for word in banned_words]
    except ImportError:
        print("⚠️ Warning: Could not load banned words list")
        return []

def contains_banned_content(text):
    """
    Check if text contains any banned words or phrases.
    
    Args:
        text (str): Text to check
        
    Returns:
        bool: True if banned content is found
    """
    if not text:
        return False
        
    banned_words = load_banned_words()
    text_lower = text.lower()
    
    for banned_word in banned_words:
        # Use word boundaries to avoid false positives
        # For multi-word phrases, check direct containment
        if ' ' in banned_word:
            if banned_word in text_lower:
                return True
        else:
            # For single words, use word boundaries
            pattern = r'\b' + re.escape(banned_word) + r'\b'
            if re.search(pattern, text_lower):
                return True
    
    return False

def get_censored_versions(original_text):
    """
    Get different versions of a censored response for different outputs.
    
    Args:
        original_text (str): The original text that contains banned content
        
    Returns:
        dict: Dictionary with different versions for different outputs
    """
    return {
        'tts_version': 'censored',              # What TTS will say (no asterisks)
        'twitch_version': '*censored*',           # What appears in Twitch chat (no asterisks)
        'ui_version': original_text,            # Original text for UI (with special styling)
        'is_censored': True                     # Flag to indicate censoring occurred
    }

def process_response_for_content(text):
    """
    Process a response text and return appropriate versions for different outputs.
    
    Args:
        text (str): Original response text
        
    Returns:
        dict: Dictionary containing versions for different outputs
    """
    if contains_banned_content(text):
        print(f"🚨 Content filter triggered for: {text[:50]}...")
        return get_censored_versions(text)
    else:
        return {
            'tts_version': text,
            'twitch_version': text,
            'ui_version': text,
            'is_censored': False
        }

# Test function
def test_content_filter():
    """Test the content filtering system"""
    test_cases = [
        "This is a normal message",
        "This contains a bad word: damn",  # Assuming 'damn' might be in your list
        "Multiple bad words here",
        "Edge case with partial matches",
        ""
    ]
    
    print("=== Content Filter Test ===")
    banned_words = load_banned_words()
    print(f"Loaded {len(banned_words)} banned words/phrases")
    print()
    
    for test in test_cases:
        is_banned = contains_banned_content(test)
        processed = process_response_for_content(test)
        
        print(f"Original: {test}")
        print(f"Contains banned content: {is_banned}")
        print(f"TTS version: {processed['tts_version']}")
        print(f"Twitch version: {processed['twitch_version']}")
        print(f"UI version: {processed['ui_version']}")
        print(f"Is censored: {processed['is_censored']}")
        print()

if __name__ == "__main__":
    test_content_filter()