from typing import Callable, Optional
from nami.input_systems.priority_core import PrioritySystem, ConversationState
from nami.input_systems.input_handlers import set_priority_system, handle_console_input
from nami.input_systems.response_handler import ResponseHandler

# Priority system instance
priority_system = None
response_handler = None

def init_priority_system(
    llm_callback: Optional[Callable[[str], str]] = None,
    twitch_callback: Optional[Callable[[str], None]] = None,  # Keep for backward compatibility
    bot_name: str = "bot",
    enable_twitch_responses: bool = True,  # Keep for backward compatibility
    enable_bot_core: bool = True,
    response_handler_instance: Optional[ResponseHandler] = None
) -> PrioritySystem:
    """
    Initialize the priority system.
    
    Args:
        llm_callback: Function to call to get LLM responses (fallback)
        twitch_callback: Kept for backward compatibility
        bot_name: Name of the bot
        enable_twitch_responses: Kept for backward compatibility
        enable_bot_core: Whether to use bot_core for responses
        response_handler_instance: Optional pre-configured ResponseHandler instance
        
    Returns:
        The initialized priority system
    """
    global priority_system, response_handler
    
    # Create priority system
    priority_system = PrioritySystem()
    
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
    
    # For backward compatibility, if twitch_callback is provided, set it as well
    if twitch_callback and not response_handler.twitch_send_callback:
        response_handler.set_twitch_send_callback(twitch_callback)
    
    # Register prioritized input handler
    priority_system.set_response_callback(response_handler.handle_prioritized_input)
    
    # Set the priority system in the input handlers
    set_priority_system(priority_system)
    
    print(f"🔄 Priority system initialized with bot_core: {response_handler.use_bot_core}")
    
    return priority_system

def set_conversation_state(state: ConversationState):
    """Set the conversation state"""
    global priority_system
    if priority_system:
        priority_system.set_state(state)

def process_console_command(command: str) -> bool:
    """Process a console command, return True if exit requested"""
    global priority_system, response_handler
    
    if command.lower() == "exit":
        return True  # Signal to exit
    elif command.lower() == "help":
        _show_help()
    elif command.lower().startswith("state "):
        # Change conversation state
        state_name = command.lower().split("state ")[1].strip()
        try:
            new_state = ConversationState[state_name.upper()]
            set_conversation_state(new_state)
        except KeyError:
            print(f"Unknown state: {state_name}")
            print(f"Available states: {[s.name for s in ConversationState]}")
    elif command.lower() == "bot_core on":
        # Enable bot_core responses
        if response_handler:
            response_handler.enable_bot_core(True)
            print("Bot core responses enabled - Bot will use bot_core.ask_question")
        else:
            print("Response handler not initialized")
    elif command.lower() == "bot_core off":
        # Disable bot_core responses
        if response_handler:
            response_handler.enable_bot_core(False)
            print("Bot core responses disabled - Bot will use LLM callback")
        else:
            print("Response handler not initialized")
    else:
        # Treat as direct input to the bot
        handle_console_input(command)
    
    return False  # Don't exit

def _show_help():
    """Show help information"""
    print("\nAvailable commands:")
    print("  exit - Exit the program")
    print("  state [STATE] - Change conversation state")
    print(f"    Available states: {[s.name for s in ConversationState]}")
    print("  bot_core on - Enable responses using bot_core.ask_question")
    print("  bot_core off - Disable responses using bot_core.ask_question")
    print("  help - Show this help message")
    print("\nAny other input will be treated as a direct message to the bot.")

def toggle_bot_core(enable: bool) -> bool:
    """
    Toggle the use of bot_core for responses.
    
    Args:
        enable: Whether to enable bot_core for responses
        
    Returns:
        Whether the operation was successful
    """
    global response_handler
    if response_handler is None:
        print("Response handler not initialized")
        return False
    
    response_handler.enable_bot_core(enable)
    return True

def shutdown_priority_system():
    """Shut down the priority system"""
    global priority_system
    if priority_system:
        priority_system.stop_processing()
        print("Priority system shut down")

# Function to get the current response handler
def get_response_handler() -> Optional[ResponseHandler]:
    """Get the current response handler instance"""
    global response_handler
    return response_handler