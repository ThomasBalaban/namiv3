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
    """Checks for banned words and returns (is_banned, trigger_word)"""
    if not text:
        return False, None
        
    banned_words = load_banned_words()
    text_lower = text.lower()
    
    for banned_word in banned_words:
        if ' ' in banned_word:
            if banned_word in text_lower:
                return True, banned_word 
        else:
            pattern = r'\b' + re.escape(banned_word) + r'\b'
            if re.search(pattern, text_lower):
                return True, banned_word
    
    return False, None

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

def get_filtered_context(text, trigger_word, context_chars=30):
    """
    Extract the area around the trigger word for display.
    Returns a string with the trigger word and surrounding context.
    """
    if not text or not trigger_word:
        return ""
    
    text_lower = text.lower()
    trigger_lower = trigger_word.lower()
    
    # Find the position of the trigger word
    pos = text_lower.find(trigger_lower)
    if pos == -1:
        return text[:60] + "..." if len(text) > 60 else text
    
    # Get context around the trigger
    start = max(0, pos - context_chars)
    end = min(len(text), pos + len(trigger_word) + context_chars)
    
    # Build the context string
    context = ""
    if start > 0:
        context += "..."
    context += text[start:end]
    if end < len(text):
        context += "..."
    
    return context

def process_response_for_content(text):
    """Updated to include the censorship_reason and filtered_area in the output dict"""
    is_banned, reason = contains_banned_content(text)
    if is_banned:
        filtered_area = get_filtered_context(text, reason)
        print(f"🚨 Content filter triggered: {reason}")
        print(f"   Filtered area: {filtered_area}")
        return {
            'tts_version': 'censored',
            'twitch_version': '*censored*',
            'ui_version': text,
            'is_censored': True,
            'censorship_reason': reason,
            'filtered_area': filtered_area
        }
    return {
        'tts_version': text,
        'twitch_version': text,
        'ui_version': text,
        'is_censored': False,
        'censorship_reason': None,
        'filtered_area': None
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