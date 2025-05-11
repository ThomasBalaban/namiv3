from typing import Callable, Optional
from nami.input_systems.priority_core import PrioritySystem, ConversationState, InputSource, InputItem
from nami.input_systems.input_handlers import set_priority_system, handle_console_input
from nami.input_systems.response_handler import ResponseHandler

# Global instances
priority_system = None
response_handler = None
input_funnel = None

def init_priority_system(
    llm_callback: Optional[Callable[[str], str]] = None,
    bot_name: str = "bot",
    enable_bot_core: bool = True,
    response_handler_instance: Optional[ResponseHandler] = None,
    funnel_instance = None
) -> PrioritySystem:
    """
    Initialize the priority system.
    
    Args:
        llm_callback: Function to call to get LLM responses
        bot_name: Name of the bot
        enable_bot_core: Whether to use bot_core for responses
        response_handler_instance: Optional pre-configured ResponseHandler instance
        funnel_instance: Optional InputFunnel instance
        
    Returns:
        The initialized priority system
    """
    global priority_system, response_handler, input_funnel
    
    # Store the funnel reference if provided
    if funnel_instance:
        input_funnel = funnel_instance
        print("Input funnel connected to priority system")
    
    # Create priority system
    priority_system = PrioritySystem()
    
    # If an input funnel is provided, use it as the target for priority items
    if input_funnel:
        # Create a bridge function to send priority items to the funnel
        def priority_to_funnel(item: InputItem):
            # Convert priority score to funnel priority (lower = higher priority)
            priority_value = 1.0 - item.score
            
            # Create source info with all metadata
            source_info = {
                'source': item.source.name,
                'timestamp': item.timestamp,
                'use_tts': item.source == InputSource.DIRECT_MICROPHONE,
                **item.metadata
            }
            
            # Format the input based on source
            formatted_input = _format_input_for_funnel(item)
            
            # Add to funnel with appropriate priority
            input_funnel.add_input(
                content=formatted_input,
                priority=priority_value,
                source_info=source_info
            )
            
            print(f"Priority item sent to funnel: {item.source.name} (score: {item.score:.2f})")
        
        # Register the bridge function as the priority callback
        priority_system.set_response_callback(priority_to_funnel)
        print("Priority system initialized with funnel integration")
    else:
        # Use provided response handler or create a new one
        if response_handler_instance:
            response_handler = response_handler_instance
        else:
            # Create response handler
            response_handler = ResponseHandler(bot_name=bot_name)
            
            # Configure response handler
            if llm_callback:
                response_handler.set_llm_callback(llm_callback)
            
            # Enable or disable bot_core usage
            response_handler.enable_bot_core(enable_bot_core)
        
        # Register traditional response handler
        priority_system.set_response_callback(response_handler.handle_prioritized_input)
        print("Priority system initialized with traditional response handler")
    
    # Set the priority system in the input handlers
    set_priority_system(priority_system)
    
    return priority_system

def _format_input_for_funnel(item: InputItem) -> str:
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

def set_conversation_state(state: ConversationState):
    """Set the conversation state"""
    global priority_system
    if priority_system:
        priority_system.set_state(state)

def process_console_command(command: str) -> bool:
    """Process a console command, return True if exit requested"""
    global priority_system, response_handler, input_funnel
    
    # Skip empty commands
    if not command.strip():
        return False
    
    if command.lower() == "exit":
        return True  # Signal to exit

    elif command.lower() == "status":
        _show_status()
    else:
        # Treat as direct input to the bot
        if input_funnel:
            # Send directly to funnel if available
            input_funnel.add_input(
                content=command,
                priority=0.0,  # Highest priority
                source_info={
                    'source': 'CONSOLE',
                    'use_tts': False
                }
            )
        else:
            # Use traditional handler
            handle_console_input(command)
    
    return False  # Don't exit

def _show_status():
    """Show the system status"""
    global priority_system, input_funnel
    from nami.input_systems.input_handlers import ENABLE_DESKTOP_AUDIO, ENABLE_VISION
    
    print("\nSystem Status:")
    print(f"  Priority System: {'Active' if priority_system else 'Inactive'}")
    print(f"  Input Funnel: {'Active' if input_funnel else 'Inactive'}")
    print(f"  Desktop Audio: {'Enabled' if ENABLE_DESKTOP_AUDIO else 'Disabled'}")
    print(f"  Vision: {'Enabled' if ENABLE_VISION else 'Disabled'}")

def shutdown_priority_system():
    """Shut down the priority system"""
    global priority_system, input_funnel
    
    # First stop the input funnel if it exists
    if input_funnel and hasattr(input_funnel, 'stop'):
        try:
            input_funnel.stop()
        except Exception as e:
            print(f"Error stopping input funnel: {e}")
    
    # Then stop the priority system
    if priority_system:
        priority_system.stop_processing()
        print("Priority system shut down")