"""
Input Handlers for PeepingNami Bot

Processes inputs from various sources into a standardized format
for the priority system.
"""

import asyncio
import threading
from typing import Dict, Any

from .priority_core import InputSource

# Global priority system reference (set by integration module)
priority_system = None

def set_priority_system(ps):
    """Set the global priority system reference"""
    global priority_system
    priority_system = ps

# ====== TWITCH CHAT HANDLER ======

async def handle_twitch_message(msg, botname="peepingnami"):
    """Process incoming Twitch chat messages"""
    if priority_system is None:
        return
        
    # Skip bot's own messages
    if msg.user.name.lower() == botname.lower():
        return
    
    # Skip system messages about bot joining
    if "Bot is ready for work" in msg.text or "joining channels" in msg.text:
        print(f"Skipping system Twitch message: {msg.text}")
        return
        
    # Extract the message content and sender
    user_message = msg.text
    username = msg.user.name

    # Determine if this is a direct mention
    is_mention = 'nami' in user_message.lower() or 'peepingnami' in user_message.lower()
    
    # Create metadata
    metadata = {
        'username': username,
        'mentioned_bot': is_mention,
        'message_length': len(user_message),
        'relevance': 0.5,  # Default relevance
    }
    
    # Add to priority system with appropriate source
    if is_mention:
        priority_system.add_input(
            InputSource.TWITCH_MENTION, 
            user_message,
            metadata
        )
    else:
        priority_system.add_input(
            InputSource.TWITCH_CHAT, 
            user_message,
            metadata
        )

# ====== HEARING SYSTEM HANDLER ======

def handle_hearing_input(transcription, source_type, confidence):
    """Process input from the hearing system"""
    if priority_system is None:
        return
        
    if confidence < 0.4:
        return  # Skip low confidence transcriptions
    
    # Determine if this is direct speech or ambient
    is_direct = False
    if source_type == "MICROPHONE":
        # Simple check - if it contains bot name, assume it's direct
        is_direct = 'nami' in transcription.lower() or 'peepingnami' in transcription.lower()
    
    # Create metadata
    metadata = {
        'source_type': source_type,
        'confidence': confidence,
        'is_direct': is_direct,
        'relevance': confidence,  # Use confidence as initial relevance
        'urgency': 0.5 if is_direct else 0.2
    }
    
    # Add to priority system with appropriate source
    if is_direct:
        priority_system.add_input(
            InputSource.DIRECT_MICROPHONE, 
            transcription,
            metadata
        )
    else:
        priority_system.add_input(
            InputSource.AMBIENT_AUDIO, 
            transcription,
            metadata
        )

def process_hearing_line(line):
    """Process a line of output from the hearing system"""
    # Skip empty lines
    if not line.strip():
        return

    # Parse the line to extract information
    confidence = 0.0
    source_type = "UNKNOWN"
    transcription = ""
    
    if "[Microphone Input]" in line:
        source_type = "MICROPHONE"
        transcription = line.replace("[Microphone Input]", "").strip()
        confidence = 0.7  # Assume decent confidence for microphone
    elif any(x in line for x in ["SPEECH", "MUSIC"]):
        # Extract confidence if available
        if "SPEECH" in line:
            source_type = "SPEECH"
            parts = line.split("SPEECH")
            if len(parts) > 1 and len(parts[1].split("]")) > 0:
                try:
                    confidence = float(parts[1].split("]")[0].strip())
                except:
                    confidence = 0.5  # Default if parsing fails
        elif "MUSIC" in line:
            source_type = "MUSIC"
            parts = line.split("MUSIC")
            if len(parts) > 1 and len(parts[1].split("]")) > 0:
                try:
                    confidence = float(parts[1].split("]")[0].strip())
                except:
                    confidence = 0.5  # Default if parsing fails
        
        # Extract the transcription text
        parts = line.split("]")
        if len(parts) > 1:
            transcription = parts[-1].strip()
    
    # Skip if no transcription
    if not transcription:
        return
    
    handle_hearing_input(transcription, source_type, confidence)

# ====== VISION SYSTEM HANDLER ======

def handle_vision_input(analysis_text, confidence, is_summary=False):
    """Process input from the vision system"""
    if priority_system is None:
        return
        
    if confidence < 0.5 and not is_summary:
        return  # Skip low confidence analyses unless it's a summary
    
    # Create metadata
    metadata = {
        'confidence': confidence,
        'is_summary': is_summary,
        'relevance': confidence * (1.5 if is_summary else 1.0),  # Boost summaries
        'urgency': 0.3 if is_summary else 0.2
    }
    
    # Add to priority system
    priority_system.add_input(
        InputSource.VISUAL_CHANGE, 
        analysis_text,
        metadata
    )

def process_vision_line(line):
    """Process a line of output from the vision system"""
    # Skip empty lines
    if not line.strip():
        return
        
    # Skip system initialization messages
    system_messages = [
        "Starting vision system", 
        "Model loaded", 
        "Vision system initialized",
        "Starting", 
        "Initializing",
        "Loading"
    ]
    
    if any(msg in line for msg in system_messages):
        print(f"Skipping system message: {line.strip()}")
        return
        
    # Determine line type and extract content
    is_summary = False
    confidence = 0.5  # Default confidence
    analysis_text = ""
    
    if "[SUMMARY]" in line or "[Summary]" in line:
        is_summary = True
        analysis_text = line.replace("[SUMMARY]", "").replace("[Summary]", "").strip()
        confidence = 0.8  # Higher confidence for summaries
    elif any(x in line for x in ["Error", "Exception", "WARNING"]):
        # Skip error messages
        return
    elif line.strip().startswith(("0.", "1.", "2.")):
        # Analysis line with time prefix
        parts = line.split(":", 1)
        if len(parts) > 1:
            time_part = parts[0].strip()
            content_part = parts[1].strip()
            analysis_text = content_part.strip()
    else:
        # Any other analysis output
        analysis_text = line.strip()
    
    # Skip if no analysis
    if not analysis_text:
        return
    
    handle_vision_input(analysis_text, confidence, is_summary)

# ====== CONSOLE INPUT HANDLER ======

def handle_console_input(text):
    """Process direct console input"""
    if priority_system is None:
        return
        
    priority_system.add_input(
        InputSource.DIRECT_MICROPHONE,
        text,
        {
            'source_type': 'CONSOLE',
            'confidence': 1.0,
            'is_direct': True,
            'relevance': 0.9,
            'urgency': 0.6
        }
    )