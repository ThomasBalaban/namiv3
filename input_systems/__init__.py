"""
Priority Input System Package
This package contains the prioritization system for handling
multiple input sources and determining which inputs trigger responses.
"""
# Expose key components at package level for easier imports
from .priority_core import PrioritySystem, InputSource, ConversationState, InputItem
from .priority_integration import (
    init_priority_system,
    shutdown_priority_system,
    process_console_command,
    set_conversation_state,
    response_handler # Expose the response handler for direct access
)
from .input_handlers import (
    handle_twitch_message,
    handle_microphone_input, # Updated: replaced handle_hearing_input
    handle_desktop_audio_input, # Added: new handler for desktop audio
    handle_vision_input,
    handle_console_input,
    process_hearing_line,
    process_vision_line
)
# Expose TTS functionality
from .azure_tts import speak, set_voice, enable_tts, is_tts_enabled

# In input_systems/__init__.py or wherever process_console_command is defined
def process_console_command(command):
    """Process a console command, return True if exit requested"""
    global priority_system
    # Split command into parts if it has spaces
    parts = command.strip().split()
    cmd = parts[0].lower() if parts else ""
    
    # Handle basic system commands
    if cmd in ["exit", "quit", "q"]:
        return True
    elif cmd == "help":
        print("\nAvailable commands:")
        print(" exit, quit, q - Exit the program")
        print(" help - Show this help message")
        print(" state [idle|engaged|observing|busy] - Set conversation state")
        print(" twitch [on|off] - Enable/disable Twitch responses")
        print(" bot_core [on|off] - Enable/disable bot_core for responses")
        print(" tts [on|off] - Enable/disable text-to-speech")
        print(" voice [voice_name] - Set TTS voice (e.g., en-US-JennyNeural)")
        print(" clear - Clear priority queue")
        print(" vision check - Check vision queue")
        return False
    
    # Handle conversation state changes
    elif cmd == "state" and len(parts) > 1:
        from .priority_integration import priority_system
        from .priority_core import ConversationState
        state_map = {
            "idle": ConversationState.IDLE,
            "engaged": ConversationState.ENGAGED,
            "observing": ConversationState.OBSERVING,
            "busy": ConversationState.BUSY
        }
        if parts[1].lower() in state_map and priority_system:
            priority_system.set_state(state_map[parts[1].lower()])
        else:
            print("Invalid state. Use: idle, engaged, observing, busy")
        return False
    
    # Handle Twitch response toggling
    elif cmd == "twitch" and len(parts) > 1:
        from .priority_integration import toggle_twitch_responses
        if parts[1].lower() == "on":
            toggle_twitch_responses(True)
        elif parts[1].lower() == "off":
            toggle_twitch_responses(False)
        else:
            print("Invalid option. Use: on, off")
        return False
    
    # Add new command to toggle bot_core
    elif cmd == "bot_core" and len(parts) > 1:
        from .priority_integration import toggle_bot_core
        if parts[1].lower() == "on":
            toggle_bot_core(True)
        elif parts[1].lower() == "off":
            toggle_bot_core(False)
        else:
            print("Invalid option. Use: on, off")
        return False
    
    # Add new command to toggle TTS
    elif cmd == "tts" and len(parts) > 1:
        from .priority_integration import response_handler
        if parts[1].lower() == "on":
            response_handler.enable_tts(True)
        elif parts[1].lower() == "off":
            response_handler.enable_tts(False)
        else:
            print("Invalid option. Use: on, off")
        return False
    
    # Add new command to set TTS voice
    elif cmd == "voice" and len(parts) > 1:
        from .priority_integration import response_handler
        voice_name = " ".join(parts[1:])
        response_handler.set_tts_voice(voice_name)
        return False
    
    # Handle priority queue clearing
    elif cmd == "clear":
        from .priority_integration import priority_system
        if priority_system:
            priority_system.empty_queue()
            print("Priority queue cleared")
        return False
    
    # Handle vision check command
    elif command.lower() == "vision check":
        from vision_system import check_vision_queue
        check_vision_queue()
        return False
    
    # For any other input, treat as direct input to bot
    else:
        from .input_handlers import handle_console_input
        handle_console_input(command)
        return False