from .priority_core import InputSource

# Global references
priority_system = None
input_funnel = None

# Feature flags
ENABLE_DESKTOP_AUDIO = False  # Set to False to disable desktop audio prompts
ENABLE_VISION = False         # Set to False to disable vision prompts

def set_priority_system(ps):
    """Set the global priority system reference"""
    global priority_system
    priority_system = ps

def set_input_funnel(funnel):
    """Set the global input funnel reference"""
    global input_funnel
    input_funnel = funnel

def set_feature_flags(desktop_audio=False, vision=False):
    """Enable or disable specific input sources"""
    global ENABLE_DESKTOP_AUDIO, ENABLE_VISION
    ENABLE_DESKTOP_AUDIO = desktop_audio
    ENABLE_VISION = vision
    print(f"Feature flags updated - Desktop Audio: {desktop_audio}, Vision: {vision}")

# ====== TWITCH CHAT HANDLER ======

async def handle_twitch_message(msg, botname="peepingnami"):
    """Process incoming Twitch chat messages"""
    global priority_system, input_funnel
    
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
    
    # Direct mentions can go straight to the funnel if available
    if is_mention and input_funnel:
        # Format the message
        formatted_message = f"{username} in chat: {user_message}"
        
        # Add to funnel with high priority
        input_funnel.add_input(
            content=formatted_message,
            priority=0.2,  # High priority (low number)
            source_info={
                'source': 'TWITCH_MENTION',
                'username': username,
                'is_direct': True,
                'use_tts': False  # Don't use TTS for Twitch responses
            }
        )
        print(f"Twitch mention from {username} sent directly to funnel")
    elif priority_system:
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
    global priority_system, input_funnel
    
    # Skip empty or too short transcriptions
    if not transcription or len(transcription) < 2:
        return

    if confidence < 0.4:
        return  # Skip low confidence transcriptions
    
    # Determine if this is direct speech by checking for bot name
    is_direct = 'nami' in transcription.lower() or 'peepingnami' in transcription.lower()
    
    # Skip system-related transcriptions
    if any(keyword in transcription.lower() for keyword in 
          ["loading", "initializing", "startup", "started", "test", "vision system"]):
        print(f"Skipping system-related transcription: {transcription}")
        return
    
    # Create metadata
    metadata = {
        'source_type': "MICROPHONE",
        'confidence': confidence,
        'is_direct': is_direct,
        'relevance': confidence,  # Use confidence as initial relevance
        'urgency': 0.5 if is_direct else 0.2
    }
    
    # Direct microphone inputs can go straight to the funnel if available
    if is_direct and input_funnel:
        # Format the input
        formatted_input = f"You said: {transcription}"
        
        # Add directly to funnel with highest priority
        input_funnel.add_input(
            content=formatted_input,
            priority=0.1,  # Very high priority (lower number)
            source_info={
                'source': 'DIRECT_MICROPHONE',
                'confidence': confidence,
                'is_direct': True,
                'use_tts': True  # Enable TTS for direct microphone
            }
        )
        print(f"Direct microphone input sent straight to funnel: {transcription[:50]}...")
    elif priority_system:
        # Add to priority system with appropriate source
        if is_direct:
            priority_system.add_input(
                InputSource.DIRECT_MICROPHONE, 
                transcription,
                metadata
            )
        else:
            # For indirect microphone inputs, we still log them but don't send to priority system
            print(f"Indirect microphone input (not sent to bot): {transcription[:50]}...")

def handle_desktop_audio_input(transcription, audio_type, confidence):
    """Process input specifically from desktop audio"""
    global priority_system, ENABLE_DESKTOP_AUDIO
    
    # Skip empty or too short transcriptions
    if not transcription or len(transcription) < 2:
        return
        
    # If desktop audio processing is disabled, just log it
    if not ENABLE_DESKTOP_AUDIO:
        print(f"Desktop audio (disabled): [{audio_type}] {transcription[:50]}...")
        return
    
    if priority_system is None:
        return
        
    if confidence < 0.4:
        return  # Skip low confidence transcriptions
    
    # Skip system-related transcriptions
    if any(keyword in transcription.lower() for keyword in 
          ["loading", "initializing", "startup", "started", "test", "vision system"]):
        print(f"Skipping system-related desktop audio: {transcription}")
        return
    
    # Create metadata
    metadata = {
        'source_type': audio_type,  # "SPEECH" or "MUSIC" 
        'confidence': confidence,
        'is_direct': False,  # Desktop audio is never direct by definition
        'relevance': confidence * 0.8,  # Slightly lower relevance than microphone
        'urgency': 0.2
    }
    
    # Desktop audio always goes to ambient audio via priority system
    # We don't send this directly to the funnel as it's lower priority
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
    global priority_system, input_funnel, ENABLE_VISION
    
    # If vision processing is disabled, just log it
    if not ENABLE_VISION:
        is_summary = metadata.get('type') == 'summary' if metadata else False
        print(f"Vision input (disabled): [{is_summary and 'SUMMARY' or 'ANALYSIS'}] {analysis_text[:50]}...")
        return
    
    # Skip system-related and startup messages
    if any(keyword in analysis_text.lower() for keyword in 
          ["loading", "initializing", "startup", "started", "test", "vision system", "model"]):
        print(f"Skipping system-related vision input: {analysis_text[:50]}...")
        return
    
    # For summaries, we always want to process them (they're important)
    is_summary = metadata.get('type') == 'summary' if metadata else False
    
    # Skip low confidence non-summary analyses
    if confidence < 0.5 and not is_summary:
        return
    
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
    
    # For significant vision changes, send directly to funnel if available
    if (is_summary or confidence > 0.8) and input_funnel:
        # Format the input
        if is_summary:
            formatted_input = f"You're seeing: {analysis_text}"
        else:
            formatted_input = f"You notice: {analysis_text}"
            
        # Add directly to funnel
        input_funnel.add_input(
            content=formatted_input,
            priority=0.3 if is_summary else 0.5,  # Higher priority for summaries
            source_info={
                'source': 'VISUAL_CHANGE',
                'is_summary': is_summary,
                'confidence': confidence,
                'use_tts': False
            }
        )
        print(f"Vision input sent directly to funnel: {analysis_text[:50]}...")
    elif priority_system:
        # Otherwise use the priority system
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
    
    # Skip empty text or error messages
    if not text.strip() or item_type == 'error':
        return
    
    # Skip system-related and startup message
    if any(keyword in text.lower() for keyword in 
          ["loading", "initializing", "startup", "started", "test", "vision system", "model"]):
        print(f"Skipping system-related vision queue item: {text[:50]}...")
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
    global priority_system, input_funnel
    
    # Skip test commands
    if "test" in text.lower() and "bot_core" in text.lower():
        print(f"Skipping test command: {text}")
        return
        
    # Check for feature flag commands
    if text.lower() == "enable vision":
        set_feature_flags(ENABLE_DESKTOP_AUDIO, True)
        print("Vision inputs enabled")
        return
    elif text.lower() == "disable vision":
        set_feature_flags(ENABLE_DESKTOP_AUDIO, False)
        print("Vision inputs disabled")
        return
    elif text.lower() == "enable desktop audio":
        set_feature_flags(True, ENABLE_VISION)
        print("Desktop audio inputs enabled")
        return
    elif text.lower() == "disable desktop audio":
        set_feature_flags(False, ENABLE_VISION)
        print("Desktop audio inputs disabled")
        return
    elif text.lower() == "enable all inputs":
        set_feature_flags(True, True)
        print("All input sources enabled")
        return
    elif text.lower() == "disable all inputs":
        set_feature_flags(False, False)
        print("All input sources disabled (except microphone)")
        return
    elif text.lower() == "status inputs":
        print(f"Input Status - Desktop Audio: {ENABLE_DESKTOP_AUDIO}, Vision: {ENABLE_VISION}")
        return
    
    # If funnel is available, send directly to it with highest priority
    if input_funnel:
        input_funnel.add_input(
            content=f"Console input: {text}",
            priority=0.0,  # Highest priority
            source_info={
                'source': 'CONSOLE',
                'is_direct': True,
                'use_tts': False  # Don't use TTS for console by default
            }
        )
        print(f"Console input sent directly to funnel: {text[:50]}...")
    elif priority_system:
        # Otherwise use priority system
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