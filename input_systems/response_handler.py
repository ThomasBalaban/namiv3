import threading
import time
from typing import Dict, Any, Optional, List, Tuple, Callable
from bot_core import ask_question  # Import the ask_question function
from .priority_core import InputItem, InputSource
from .azure_tts import speak, enable_tts, set_voice, is_tts_enabled  # Import Azure TTS functions

max_responses_stored = 15

# ANSI color codes for highlighting console output
class Colors:
    HEADER = '\033[95m'  # Magenta
    BLUE = '\033[94m'    # Blue
    GREEN = '\033[92m'   # Green
    YELLOW = '\033[93m'  # Yellow
    RED = '\033[91m'     # Red
    BOLD = '\033[1m'     # Bold
    UNDERLINE = '\033[4m'# Underline
    END = '\033[0m'      # Reset

class ResponseHandler:
    def __init__(self, bot_name="peepingnami"):
        self.bot_name = bot_name
        self.llm_callback = None
        # Flag to control using bot_core directly
        self.use_bot_core = True
        # Callback for sending to Twitch
        self.twitch_send_callback = None
        # Recent responses for deduplication
        self._recent_responses = []
        # TTS is always enabled with fixed voice
        self.use_tts = True
        
        # Try to import config to get voice preference
        try:
            import sys
            import os
            sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            import config
            voice_name = getattr(config, 'AZURE_VOICE_NAME', "en-US-JennyNeural")
        except (ImportError, AttributeError):
            voice_name = "en-US-JennyNeural"
            
        # Set the voice
        set_voice(voice_name)
    
    def set_llm_callback(self, callback):
        """Set the callback function for getting responses from the LLM (fallback)"""
        self.llm_callback = callback
    
    def set_twitch_send_callback(self, callback):
        """Set the callback function for sending messages to Twitch"""
        self.twitch_send_callback = callback
        print(f"{Colors.GREEN}Twitch send callback registered with ResponseHandler{Colors.END}")
    
    def handle_prioritized_input(self, item: InputItem):
        """Process an input that has passed the priority threshold"""
        print(f"\n{Colors.YELLOW}[PRIORITY] Processing input: {item.source.name} - {item.text[:50]}...{Colors.END}")
        
        # Check if we've recently responded to very similar input (to prevent loops)
        if self._is_too_similar_to_recent(item):
            print(f"{Colors.RED}[PRIORITY] Skipping - too similar to recent response{Colors.END}")
            return
        
        # Format the input appropriately based on source
        formatted_input = self._format_input(item)
        
        # Get response using appropriate method
        if self.use_bot_core:
            # Use bot_core directly
            print(f"{Colors.BLUE}[BOT_CORE] Sending to bot_core: {formatted_input}{Colors.END}")
            response = ask_question(formatted_input)
        elif self.llm_callback:
            # Use the original LLM callback as fallback
            print(f"{Colors.BLUE}[LLM] Sending to LLM callback: {formatted_input}{Colors.END}")
            response = self.llm_callback(formatted_input)
        else:
            print(f"{Colors.RED}[WARNING] No response mechanism available, can't process: {formatted_input}{Colors.END}")
            return
            
        # Skip if no response
        if not response:
            print(f"{Colors.RED}[WARNING] No response generated for: {formatted_input}{Colors.END}")
            return
        
        # Store this response to avoid repetition
        self._store_recent_response(item, response)
            
        # Display the response in console and use TTS if enabled
        self._display_response(item, response)
    
    def _is_too_similar_to_recent(self, item: InputItem) -> bool:
        """Check if an input is too similar to something we just responded to"""
        # Implement a simple check to avoid responding to nearly identical inputs
        # For now, just check text similarity of the first 50 chars for items of the same source type
        if not self._recent_responses:
            return False
            
        # Get normalized text for comparison
        current_text = item.text[:50].lower().strip()
        
        # Only avoid repetition for the same source type
        for past_source, past_text, _ in self._recent_responses:
            if past_source == item.source and past_text == current_text:
                # Too similar, don't respond
                return True
                
        return False
        
    def _store_recent_response(self, item: InputItem, response: str):
        """Store a response to avoid repetition"""
        # Store the source type, first 50 chars of text, and timestamp
        self._recent_responses.append((
            item.source,
            item.text[:50].lower().strip(),
            time.time()
        ))
        
        # Only keep the last N responses
        if len(self._recent_responses) > max_responses_stored:
            self._recent_responses.pop(0)
    
    def _format_input(self, item: InputItem) -> str:
        """Format the input appropriately based on source"""
        # Direct interactions - formatted as questions/commands
        if item.source == InputSource.DIRECT_MICROPHONE:
            return f"You said: {item.text}"
        elif item.source == InputSource.TWITCH_MENTION:
            username = item.metadata.get('username', 'Someone')
            return f"{username} in chat: {item.text}"
        
        # Ambient audio - what the bot is hearing
        elif item.source == InputSource.AMBIENT_AUDIO:
            audio_type = item.metadata.get('source_type', 'AUDIO')
            if audio_type == "MUSIC":
                return f"You're hearing music: {item.text}. React to this if you find it interesting."
            else:
                return f"You're overhearing: {item.text}. React to this if you find it interesting."
                
        # Visual inputs - what the bot is seeing
        elif item.source == InputSource.VISUAL_CHANGE:
            if item.metadata.get('is_summary', False):
                return f"You're seeing: {item.text}. React to what you're seeing if you find it interesting."
            else:
                return f"You notice: {item.text}. React to what you're seeing if you find it interesting."
                
        # Regular chat messages that aren't directed at the bot
        elif item.source == InputSource.TWITCH_CHAT:
            username = item.metadata.get('username', 'Someone')
            return f"You see {username} chatting: {item.text}. React to this if you find it interesting."
        else:
            return item.text
    
    def _display_response(self, item: InputItem, response: str):
        """Display the response in console and activate TTS"""
        
        # Format with highlighting to make it stand out
        source_type = item.source.name
        if item.source == InputSource.TWITCH_MENTION or item.source == InputSource.TWITCH_CHAT:
            username = item.metadata.get('username', 'Unknown')
            source_info = f" (to {username} in chat)"
        else:
            source_info = ""
            
        # Simple border with dashes
        border = "-" * 50
        
        # Print with enhanced formatting
        print("\n")  # Add extra spacing
        print(f"{Colors.BOLD}{Colors.BLUE}{border}{Colors.END}")
        print(f"{Colors.GREEN}{response}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.BLUE}{border}{Colors.END}")
        print("\n")  # Add extra spacing
        
        # Always activate TTS for all responses
        if is_tts_enabled():
            print(f"{Colors.YELLOW}[TTS] Speaking response...{Colors.END}")
            speak(response, blocking=False)  # Non-blocking to avoid delaying the conversation
        
        # Reset prompt
        print(f"{Colors.BOLD}You: {Colors.END}", end="", flush=True)
        
        # Send the response to Twitch if appropriate and callback is available
        should_send_to_twitch = (
            item.source == InputSource.TWITCH_MENTION or 
            item.source == InputSource.TWITCH_CHAT or
            getattr(item, 'broadcast_response', False)
        )
        
        if should_send_to_twitch and self.twitch_send_callback:
            try:
                self.twitch_send_callback(response)
            except Exception as e:
                print(f"{Colors.RED}Error in twitch_send_callback: {str(e)}{Colors.END}")
    
    def enable_bot_core(self, enable=True):
        """Enable or disable using bot_core for responses"""
        self.use_bot_core = enable
        status = "enabled" if enable else "disabled"
        print(f"{Colors.YELLOW}Bot core responses {status}{Colors.END}")