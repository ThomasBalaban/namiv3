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

def handle_microphone_input(transcription, confidence=0.7):
    """Process input specifically from microphone"""
    if priority_system is None:
        return
        
    if confidence < 0.4:
        return  # Skip low confidence transcriptions
    
    # Determine if this is direct speech by checking for bot name
    is_direct = 'nami' in transcription.lower() or 'peepingnami' in transcription.lower()
    
    # Create metadata
    metadata = {
        'source_type': "MICROPHONE",
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

def handle_desktop_audio_input(transcription, audio_type, confidence):
    """Process input specifically from desktop audio"""
    if priority_system is None:
        return
        
    if confidence < 0.4:
        return  # Skip low confidence transcriptions
    
    # Create metadata
    metadata = {
        'source_type': audio_type,  # "SPEECH" or "MUSIC" 
        'confidence': confidence,
        'is_direct': False,  # Desktop audio is never direct by definition
        'relevance': confidence * 0.8,  # Slightly lower relevance than microphone
        'urgency': 0.2
    }
    
    # Desktop audio always goes to ambient audio
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
        # Process microphone input
        transcription = line.replace("[Microphone Input]", "").strip()
        
        # If we have a transcription, handle it
        if transcription:
            handle_microphone_input(transcription)
            
    elif any(x in line for x in ["SPEECH", "MUSIC"]):
        # This is desktop audio
        
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
        
        # If we have a transcription, handle it as desktop audio
        if transcription:
            handle_desktop_audio_input(transcription, source_type, confidence)

# ====== VISION SYSTEM HANDLER ======
def handle_vision_input(analysis_text, confidence, metadata=None):
    """Process input from the vision system"""
    if priority_system is None:
        return
        
    is_summary = metadata.get('type') == 'summary' if metadata else False
    
    if confidence < 0.5 and not is_summary:
        return  # Skip low confidence analyses unless it's a summary
    
    # Create standard metadata if not provided
    if metadata is None:
        metadata = {}
    
    # Add required fields for priority system
    metadata.update({
        'confidence': confidence,
        'is_summary': is_summary,
        'relevance': confidence * (1.5 if is_summary else 1.0),  # Boost summaries
        'urgency': 0.3 if is_summary else 0.2
    })
    
    # Add to priority system
    priority_system.add_input(
        InputSource.VISUAL_CHANGE, 
        analysis_text,
        metadata
    )

def process_vision_queue_item(item):
    """Process an item from the vision queue"""
    if not item:
        return
        
    # Extract standard fields from queue item
    source = item.get('source', 'VISUAL_CHANGE')
    text = item.get('text', '')
    score = item.get('score', 0.7)
    metadata = item.get('metadata', {})
    item_type = item.get('type', 'analysis')
    
    # Skip empty text
    if not text.strip():
        return
        
    # Skip error messages unless in debug mode
    if item_type == 'error' and not metadata.get('debug', False):
        return
        
    # Pass to the handle_vision_input function with full metadata
    metadata['type'] = item_type  # Ensure type is in metadata
    handle_vision_input(text, score, metadata)

# Legacy line processor for console output compatibility
def process_vision_line(line):
    """Process a line of output from the vision system (legacy method)"""
    # Skip empty lines
    if not line.strip():
        return
        
    # Determine line type and extract content
    is_summary = False
    confidence = 0.7  # Default confidence
    analysis_text = ""
    
    if "[VISION] 👁️" in line:
        # New format from updated vision system
        analysis_text = line.replace("[VISION] 👁️", "").strip()
    elif "[SUMMARY]" in line or "[Summary]" in line:
        is_summary = True
        analysis_text = line.replace("[SUMMARY]", "").replace("[Summary]", "").strip()
        confidence = 0.9  # Higher confidence for summaries
    elif any(x in line for x in ["Error", "Exception", "WARNING", "[VISION ERROR]"]):
        # Skip error messages
        return
    elif line.strip().startswith(("0.", "1.", "2.")):
        # Analysis line with time prefix
        parts = line.split(":", 1)
        if len(parts) > 1:
            time_part = parts[0].strip()
            content_part = parts[1].strip()
            analysis_text = content_part.strip()
            
            # Try to extract processing time for confidence
            try:
                proc_time = float(time_part)
                confidence = min(0.95, max(0.5, 1.0 - (proc_time / 10.0)))
            except ValueError:
                pass
    else:
        # Any other analysis output
        analysis_text = line.strip()
    
    # Skip if no analysis
    if not analysis_text:
        return
    
    # Create metadata with type information
    metadata = {
        'type': 'summary' if is_summary else 'analysis',
        'source_type': 'VISION'
    }
    
    handle_vision_input(analysis_text, confidence, metadata)

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