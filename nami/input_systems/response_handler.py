import time
from nami.bot_core import ask_question
from nami.input_systems.priority_core import InputItem, InputSource

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
        self._max_responses = 15
    
    def set_llm_callback(self, callback):
        """Set the callback function for getting responses from the LLM"""
        self.llm_callback = callback
    
    def set_twitch_send_callback(self, callback):
        """Set the callback function for sending messages to Twitch"""
        self.twitch_send_callback = callback
    
    def handle_prioritized_input(self, item: InputItem):
        """Process an input that has passed the priority threshold"""
        print(f"Processing priority input: {item.source.name} - {item.text[:50]}...")
        
        # Check if we've recently responded to very similar input
        if self._is_too_similar_to_recent(item):
            print(f"Skipping - too similar to recent response")
            return
        
        # Format the input appropriately based on source
        formatted_input = self._format_input(item)
        
        # Get response using appropriate method
        if self.use_bot_core:
            # Use bot_core directly
            print(f"Sending to bot_core: {formatted_input[:50]}...")
            response = ask_question(formatted_input)
        elif self.llm_callback:
            # Use the original LLM callback as fallback
            print(f"Sending to LLM callback: {formatted_input[:50]}...")
            response = self.llm_callback(formatted_input)
        else:
            print(f"No response mechanism available, can't process: {formatted_input[:50]}...")
            return
            
        # Skip if no response
        if not response:
            print(f"No response generated")
            return
        
        # Store this response to avoid repetition
        self._store_recent_response(item, response)
            
        # Display the response in console
        self._display_response(item, response)
    
    def _is_too_similar_to_recent(self, item: InputItem) -> bool:
        """Check if an input is too similar to something we just responded to"""
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
        
        # Only keep the most recent responses
        if len(self._recent_responses) > self._max_responses:
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
        """Display the response in console"""
        # Format with highlighting to make it stand out
        source_type = item.source.name
        if item.source == InputSource.TWITCH_MENTION or item.source == InputSource.TWITCH_CHAT:
            username = item.metadata.get('username', 'Unknown')
            source_info = f" (to {username} in chat)"
        else:
            source_info = ""
            
        # Print with enhanced formatting
        print("\n" + "-" * 50)
        print(f"{response}")
        print("-" * 50 + "\n")
        
        # Reset prompt
        print(f"You: ", end="", flush=True)
        
        # Send the response to Twitch if appropriate and callback is available
        should_send_to_twitch = (
            item.source == InputSource.TWITCH_MENTION or 
            item.source == InputSource.TWITCH_CHAT
        )
        
        if should_send_to_twitch and self.twitch_send_callback:
            try:
                self.twitch_send_callback(response)
            except Exception as e:
                print(f"Error in twitch_send_callback: {str(e)}")
    
    def enable_bot_core(self, enable=True):
        """Enable or disable using bot_core for responses"""
        self.use_bot_core = enable
        status = "enabled" if enable else "disabled"
        print(f"Bot core responses {status}")