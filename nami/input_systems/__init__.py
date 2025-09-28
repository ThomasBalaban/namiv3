# nami/input_systems/__init__.py

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
    handle_microphone_input,
    handle_desktop_audio_input,
    handle_vision_input,
    handle_console_input,
    # REMOVED: process_hearing_line
    process_vision_line
)

# ... (rest of the file remains the same)