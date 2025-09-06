"""
This file makes the 'ui' directory a Python package.
It also exposes the main functions from the server module for easier access.
"""
from .server import (
    start_ui_server,
    emit_log,
    emit_vision_context,
    emit_audio_context,
    emit_twitch_message,
    emit_bot_reply
)
