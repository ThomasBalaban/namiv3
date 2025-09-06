from .priority_core import InputSource
from ..config import ENABLE_DESKTOP_AUDIO, ENABLE_VISION
from ..ui import emit_spoken_word_context, emit_audio_context

# Global references
priority_system = None
input_funnel = None

def set_priority_system(ps):
    """Set the global priority system reference"""
    global priority_system
    priority_system = ps

def set_input_funnel(funnel):
    """Set the global input funnel reference"""
    global input_funnel
    input_funnel = funnel

# ====== TWITCH CHAT HANDLER ======

async def handle_twitch_message(msg, botname="peepingnami"):
    """Process incoming Twitch chat messages"""
    global priority_system, input_funnel
    
    if msg.user.name.lower() == botname.lower():
        return
        
    user_message = msg.text
    username = msg.user.name

    is_mention = 'nami' in user_message.lower() or 'peepingnami' in user_message.lower()
    
    metadata = {
        'username': username,
        'mentioned_bot': is_mention,
        'message_length': len(user_message),
        'relevance': 0.5,
    }
    
    if is_mention and input_funnel:
        formatted_message = f"{username} in chat: {user_message}"
        
        input_funnel.add_input(
            content=formatted_message,
            priority=0.2,
            source_info={
                'source': 'TWITCH_MENTION',
                'username': username,
                'is_direct': True,
                # --- FIX: Changed this from False to True ---
                'use_tts': True
            }
        )
    elif priority_system:
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
    
    if not transcription or len(transcription) < 2:
        return

    # --- Route to the correct UI panel ---
    emit_spoken_word_context(transcription)
    
    is_direct = 'nami' in transcription.lower() or 'peepingnami' in transcription.lower()
    
    metadata = {
        'source_type': "MICROPHONE",
        'confidence': confidence,
        'is_direct': is_direct,
        'relevance': confidence,
        'urgency': 0.5 if is_direct else 0.2
    }
    
    if is_direct and input_funnel:
        formatted_input = f"You said: {transcription}"
        
        input_funnel.add_input(
            content=formatted_input,
            priority=0.1,
            source_info={
                'source': 'DIRECT_MICROPHONE',
                'confidence': confidence,
                'is_direct': True,
                'use_tts': True
            }
        )
    elif priority_system:
        if is_direct:
            priority_system.add_input(
                InputSource.DIRECT_MICROPHONE, 
                transcription,
                metadata
            )

def handle_desktop_audio_input(transcription, audio_type, confidence):
    """Process input specifically from desktop audio"""
    global priority_system, ENABLE_DESKTOP_AUDIO
    
    if not transcription or len(transcription) < 2:
        return
    
    # --- Route to the correct UI panel ---
    emit_audio_context(f"[{audio_type.upper()}] {transcription}")
        
    if not ENABLE_DESKTOP_AUDIO:
        return
    
    if priority_system is None:
        return
    
    metadata = {
        'source_type': audio_type,
        'confidence': confidence,
        'is_direct': False,
        'relevance': confidence * 0.8,
        'urgency': 0.2
    }
    
    priority_system.add_input(
        InputSource.AMBIENT_AUDIO, 
        transcription,
        metadata
    )

def process_hearing_line(line):
    """Process a line of output from the hearing system"""
    if not line.strip():
        return

    confidence = 0.7
    source_type = "UNKNOWN"
    transcription = ""
    
    if "[Microphone Input]" in line:
        transcription = line.replace("[Microphone Input]", "").strip()
        
        if transcription:
            handle_microphone_input(transcription)
            
    elif any(x in line for x in ["SPEECH", "MUSIC"]):
        
        if "SPEECH" in line:
            source_type = "SPEECH"
            parts = line.split("SPEECH")
            if len(parts) > 1 and len(parts[1].split("]")) > 0:
                try:
                    confidence = float(parts[1].split("]")[0].strip())
                except:
                    confidence = 0.7
        elif "MUSIC" in line:
            source_type = "MUSIC"
            parts = line.split("MUSIC")
            if len(parts) > 1 and len(parts[1].split("]")) > 0:
                try:
                    confidence = float(parts[1].split("]")[0].strip())
                except:
                    confidence = 0.7
        
        parts = line.split("]")
        if len(parts) > 1:
            transcription = parts[-1].strip()
        
        if transcription:
            handle_desktop_audio_input(transcription, source_type, confidence)

# ====== VISION SYSTEM HANDLER ======
def handle_vision_input(analysis_text, confidence, metadata=None):
    """Process input from the vision system"""
    global priority_system, input_funnel, ENABLE_VISION
    
    if not ENABLE_VISION:
        return
    
    if not analysis_text or len(analysis_text) < 2:
        return
    
    is_summary = metadata.get('type') == 'summary' if metadata else False
    
    if confidence < 0.5 and not is_summary:
        return
    
    if metadata is None:
        metadata = {}
    
    metadata.update({
        'confidence': confidence,
        'is_summary': is_summary,
        'relevance': confidence * (1.5 if is_summary else 1.0),
        'urgency': 0.3 if is_summary else 0.2
    })
    
    if (is_summary or confidence > 0.8) and input_funnel:
        if is_summary:
            formatted_input = f"You're seeing: {analysis_text}"
        else:
            formatted_input = f"You notice: {analysis_text}"
            
        input_funnel.add_input(
            content=formatted_input,
            priority=0.3 if is_summary else 0.5,
            source_info={
                'source': 'VISUAL_CHANGE',
                'is_summary': is_summary,
                'confidence': confidence,
                'use_tts': False
            }
        )
    elif priority_system:
        priority_system.add_input(
            InputSource.VISUAL_CHANGE, 
            analysis_text,
            metadata
        )

def process_vision_line(line):
    """Process a line of output from the vision system"""
    if not line.strip():
        return
        
    is_summary = False
    confidence = 0.7
    analysis_text = ""
    
    if "[VISION] 👁️" in line:
        analysis_text = line.replace("[VISION] 👁️", "").strip()
    elif "[SUMMARY]" in line or "[Summary]" in line:
        is_summary = True
        analysis_text = line.replace("[SUMMARY]", "").replace("[Summary]", "").strip()
        confidence = 0.9
    elif any(x in line for x in ["Error", "Exception", "WARNING", "[VISION ERROR]"]):
        return
    elif line.strip().startswith(("0.", "1.", "2.")):
        parts = line.split(":", 1)
        if len(parts) > 1:
            time_part = parts[0].strip()
            content_part = parts[1].strip()
            analysis_text = content_part.strip()
            
            try:
                proc_time = float(time_part)
                confidence = min(0.95, max(0.5, 1.0 - (proc_time / 10.0)))
            except ValueError:
                pass
    else:
        analysis_text = line.strip()
    
    if not analysis_text:
        return
    
    metadata = {
        'type': 'summary' if is_summary else 'analysis',
        'source_type': 'VISION'
    }
    
    handle_vision_input(analysis_text, confidence, metadata)

# ====== CONSOLE INPUT HANDLER ======
def handle_console_input(text):
    """Process direct console input"""
    global priority_system, input_funnel
    
    if not text.strip():
        return
    
    if input_funnel:
        input_funnel.add_input(
            content=f"Console input: {text}",
            priority=0.0,
            source_info={
                'source': 'CONSOLE',
                'is_direct': True,
                'use_tts': False
            }
        )
    elif priority_system:
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