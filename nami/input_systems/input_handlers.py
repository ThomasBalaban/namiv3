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

    # All Twitch messages, mentions or not, now go through the priority system.
    # The priority system will correctly identify mentions as high-priority and chat as low-priority context.
    if priority_system:
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
    global priority_system

    if not transcription or len(transcription) < 2:
        return

    emit_spoken_word_context(transcription)

    is_direct = 'nami' in transcription.lower() or 'peepingnami' in transcription.lower()

    metadata = {
        'source_type': "MICROPHONE",
        'confidence': confidence,
        'is_direct': is_direct,
        'relevance': confidence,
        'urgency': 0.5 if is_direct else 0.2
    }

    if priority_system:
        if is_direct:
            priority_system.add_input(
                InputSource.DIRECT_MICROPHONE,
                transcription,
                metadata
            )
        else:
            priority_system.add_input(
                InputSource.MICROPHONE,
                transcription,
                metadata
            )


def handle_desktop_audio_input(transcription, audio_type, confidence):
    """Process input specifically from desktop audio"""
    global priority_system, ENABLE_DESKTOP_AUDIO

    if not transcription or len(transcription) < 2:
        return

    emit_audio_context(f"[{audio_type.upper()}] {transcription}")

    if not ENABLE_DESKTOP_AUDIO or not priority_system:
        return

    is_direct = 'nami' in transcription.lower() or 'peepingnami' in transcription.lower()

    metadata = {
        'source_type': audio_type,
        'confidence': confidence,
        'is_direct': is_direct,
        'relevance': confidence * 0.8,
        'urgency': 0.5 if is_direct else 0.2
    }
    
    # If a direct mention is heard in desktop audio, treat it as a prompt.
    # Otherwise, it's just ambient context.
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
    """
    Process input from the vision system.
    FIX: This now ONLY sends data to the priority system for context, it never calls the funnel directly.
    """
    global priority_system, ENABLE_VISION

    if not ENABLE_VISION or not priority_system:
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

    # All vision input now goes through the priority system, which will correctly
    # score it as low-priority context and not trigger a response.
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
    global priority_system

    if not text.strip() or not priority_system:
        return

    # Console input is always a direct prompt
    priority_system.add_input(
        InputSource.DIRECT_MICROPHONE, # Treated as a direct prompt
        text,
        {
            'source_type': 'CONSOLE',
            'confidence': 1.0,
            'is_direct': True,
            'relevance': 0.9,
            'urgency': 0.6
        }
    )