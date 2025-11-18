# Save as: nami/input_systems/input_handlers.py
from .priority_core import InputSource
from ..config import ENABLE_DESKTOP_AUDIO, ENABLE_VISION
from nami.director_connector import send_event

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
    global priority_system

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
    
    # Always send to Director so it shows in UI
    send_event(
        source_str="TWITCH_MENTION" if is_mention else "TWITCH_CHAT",
        text=user_message,
        metadata=metadata,
        username=username
    )

    if priority_system and is_mention:
        # --- TIER 3 (Action) ---
        priority_system.add_input(
            InputSource.TWITCH_MENTION,
            user_message,
            metadata
        )

# ====== HEARING SYSTEM HANDLER ======
def handle_microphone_input(transcription, confidence=0.7):
    """Process input specifically from microphone"""
    global priority_system

    if not transcription or len(transcription) < 2:
        return

    is_direct = 'nami' in transcription.lower() or 'peepingnami' in transcription.lower()
    metadata = {
        'source_type': "MICROPHONE",
        'confidence': confidence,
        'is_direct': is_direct,
        'relevance': confidence,
        'urgency': 0.5 if is_direct else 0.2
    }

    # --- MODIFIED: Always send to Director for UI visibility ---
    send_event(
        source_str="DIRECT_MICROPHONE" if is_direct else "MICROPHONE",
        text=transcription,
        metadata=metadata
    )

    if priority_system and is_direct:
        # --- TIER 3 (Action) ---
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

    if not ENABLE_DESKTOP_AUDIO:
        return

    is_direct = 'nami' in transcription.lower() or 'peepingnami' in transcription.lower()
    metadata = {
        'source_type': audio_type,
        'confidence': confidence,
        'is_direct': is_direct,
        'relevance': confidence * 0.8,
        'urgency': 0.5 if is_direct else 0.2
    }
    
    # Send to Director for UI / Context
    send_event(
        source_str="AMBIENT_AUDIO",
        text=transcription,
        metadata=metadata
    )
    
    if is_direct and priority_system:
        # --- TIER 3 (Action) ---
        priority_system.add_input(
            InputSource.DIRECT_MICROPHONE,
            transcription,
            metadata
        )

def process_hearing_line(line):
    if not line.strip(): return
    confidence = 0.7
    source_type = "UNKNOWN"
    transcription = ""
    if "[Microphone Input]" in line:
        transcription = line.replace("[Microphone Input]", "").strip()
        if transcription: handle_microphone_input(transcription)
    elif any(x in line for x in ["SPEECH", "MUSIC"]):
        if "SPEECH" in line:
            source_type = "SPEECH"
            parts = line.split("SPEECH")
            if len(parts) > 1 and len(parts[1].split("]")) > 0:
                try: confidence = float(parts[1].split("]")[0].strip())
                except: confidence = 0.7
        elif "MUSIC" in line:
            source_type = "MUSIC"
            parts = line.split("MUSIC")
            if len(parts) > 1 and len(parts[1].split("]")) > 0:
                try: confidence = float(parts[1].split("]")[0].strip())
                except: confidence = 0.7
        parts = line.split("]")
        if len(parts) > 1: transcription = parts[-1].strip()
        if transcription: handle_desktop_audio_input(transcription, source_type, confidence)

# ====== VISION SYSTEM HANDLER ======
def handle_vision_input(analysis_text, confidence, metadata=None):
    global priority_system, ENABLE_VISION
    if not ENABLE_VISION: return
    if not analysis_text or len(analysis_text) < 2: return
    is_summary = metadata.get('type') == 'summary' if metadata else False
    if confidence < 0.5 and not is_summary: return
    if metadata is None: metadata = {}
    metadata.update({
        'confidence': confidence,
        'is_summary': is_summary,
        'relevance': confidence * (1.5 if is_summary else 1.0),
        'urgency': 0.3 if is_summary else 0.2
    })
    
    # Send to Director for UI / Context
    send_event(
        source_str="VISUAL_CHANGE",
        text=analysis_text,
        metadata=metadata
    )

def process_vision_line(line):
    if not line.strip(): return
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
            except ValueError: pass
    else:
        analysis_text = line.strip()
    if not analysis_text: return
    metadata = {'type': 'summary' if is_summary else 'analysis', 'source_type': 'VISION'}
    handle_vision_input(analysis_text, confidence, metadata)

# ====== CONSOLE INPUT HANDLER ======
def handle_console_input(text):
    global priority_system
    if not text.strip() or not priority_system: return
    priority_system.add_input(
        InputSource.DIRECT_MICROPHONE,
        text,
        {'source_type': 'CONSOLE', 'confidence': 1.0, 'is_direct': True, 'relevance': 0.9, 'urgency': 0.6}
    )