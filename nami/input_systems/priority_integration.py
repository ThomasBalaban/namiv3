from typing import Callable, Optional
from nami.input_systems.priority_core import PrioritySystem, ConversationState, InputSource, InputItem
from nami.input_systems.input_handlers import set_priority_system, handle_console_input
from nami.input_systems.response_handler import ResponseHandler

# Global instances
priority_system = None
response_handler = None
input_funnel = None

def get_response_handler():
    """Returns the global response_handler instance."""
    global response_handler
    return response_handler

def init_priority_system(
    llm_callback: Optional[Callable[[str], str]] = None,
    bot_name: str = "bot",
    enable_bot_core: bool = True,
    response_handler_instance: Optional[ResponseHandler] = None,
    funnel_instance = None
) -> PrioritySystem:
    """
    Initialize the priority system.
    """
    global priority_system, response_handler, input_funnel

    if funnel_instance:
        input_funnel = funnel_instance
        print("Input funnel connected to priority system")

    priority_system = PrioritySystem()

    if input_funnel:
        def priority_to_funnel(item: InputItem):
            """
            Bridge function to send priority items to the funnel.
            AMBIENT REPLIES ARE NOW DISABLED. This only handles direct inputs.
            """
            # This check ensures we don't accidentally process ambient events as direct replies.
            if item.source not in [InputSource.DIRECT_MICROPHONE, InputSource.TWITCH_MENTION]:
                return

            formatted_input = _format_input_for_funnel(item)
            priority_value = 1.0 - item.score
            source_info = {
                'source': item.source.name,
                'timestamp': item.timestamp,
                # UPDATED LOGIC: Enable TTS for Twitch mentions as well
                'use_tts': item.source in [InputSource.DIRECT_MICROPHONE, InputSource.TWITCH_MENTION],
                **item.metadata
            }
            input_funnel.add_input(
                content=formatted_input,
                priority=priority_value,
                source_info=source_info
            )
            print(f"Direct input sent to funnel: {item.source.name} (score: {item.score:.2f})")

        priority_system.set_response_callback(priority_to_funnel)
        print("Priority system initialized with funnel integration for direct replies.")
    else:
        # Fallback if funnel isn't used
        if response_handler_instance:
            response_handler = response_handler_instance
        else:
            response_handler = ResponseHandler(bot_name=bot_name)
            if llm_callback:
                response_handler.set_llm_callback(llm_callback)
            response_handler.enable_bot_core(enable_bot_core)
        priority_system.set_response_callback(response_handler.handle_prioritized_input)
        print("Priority system initialized with traditional response handler")

    set_priority_system(priority_system)
    return priority_system

def _format_input_for_funnel(item: InputItem) -> str:
    """Format the input appropriately based on source"""
    if item.source == InputSource.DIRECT_MICROPHONE:
        return f"PeepingOtter said: {item.text}"
    elif item.source == InputSource.TWITCH_MENTION:
        username = item.metadata.get('username', 'Someone')
        # Use a simple "Username: message" format
        return f"{username}: {item.text}"
    # Ambient formatting is removed as they no longer generate replies this way
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
    
    if not command.strip():
        return False
    
    if command.lower() == "exit":
        return True

    elif command.lower() == "status":
        _show_status()
    else:
        if input_funnel:
            input_funnel.add_input(
                content=command,
                priority=0.0,
                source_info={'source': 'CONSOLE', 'use_tts': False}
            )
        else:
            handle_console_input(command)
    
    return False

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
    
    if input_funnel and hasattr(input_funnel, 'stop'):
        try:
            input_funnel.stop()
        except Exception as e:
            print(f"Error stopping input funnel: {e}")
    
    if priority_system:
        priority_system.stop_processing()
        print("Priority system shut down")