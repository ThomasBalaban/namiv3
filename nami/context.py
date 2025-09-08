import time
from threading import Lock

# Constants
CONTEXT_TIME_WINDOW_SECONDS = 30
MAX_TWITCH_CONTEXT_LENGTH = 20

# Global context stores
latest_vision_context = []
latest_spoken_word_context = []
latest_audio_context = []
latest_twitch_chat_context = []

# Thread lock for safe updates
context_lock = Lock()

def update_twitch_chat_context(username: str, message: str):
    """Thread-safely updates the latest Twitch chat context."""
    global latest_twitch_chat_context
    with context_lock:
        formatted_message = f"{username}: {message}"
        latest_twitch_chat_context.append(formatted_message)
        while len(latest_twitch_chat_context) > MAX_TWITCH_CONTEXT_LENGTH:
            latest_twitch_chat_context.pop(0)

def update_vision_context(text: str):
    """Thread-safely updates vision context, keeping entries within the time window."""
    global latest_vision_context
    with context_lock:
        now = time.time()
        latest_vision_context.append((now, text))
        # Filter out old entries
        latest_vision_context = [(ts, txt) for ts, txt in latest_vision_context if now - ts <= CONTEXT_TIME_WINDOW_SECONDS]

def update_spoken_word_context(text: str):
    """Thread-safely updates spoken word context, keeping entries within the time window."""
    global latest_spoken_word_context
    with context_lock:
        now = time.time()
        latest_spoken_word_context.append((now, text))
        # Filter out old entries
        latest_spoken_word_context = [(ts, txt) for ts, txt in latest_spoken_word_context if now - ts <= CONTEXT_TIME_WINDOW_SECONDS]

def update_audio_context(text: str):
    """Thread-safely updates audio context, keeping entries within the time window."""
    global latest_audio_context
    with context_lock:
        now = time.time()
        latest_audio_context.append((now, text))
        # Filter out old entries
        latest_audio_context = [(ts, txt) for ts, txt in latest_audio_context if now - ts <= CONTEXT_TIME_WINDOW_SECONDS]

def get_formatted_context():
    """Builds a formatted string of all current context for the LLM."""
    with context_lock:
        vision_summary = "You haven't seen anything recently."
        if latest_vision_context:
            vision_texts = [text for _, text in latest_vision_context]
            vision_summary = "\n".join(vision_texts)

        spoken_word_summary = "You haven't heard anyone speak recently."
        if latest_spoken_word_context:
            spoken_word_texts = [text for _, text in latest_spoken_word_context]
            spoken_word_summary = "\n".join(spoken_word_texts)

        audio_summary = "You haven't heard anything recently."
        if latest_audio_context:
            audio_texts = [text for _, text in latest_audio_context]
            audio_summary = "\n".join(audio_texts)
        
        twitch_chat_summary = "Nothing new in chat."
        if latest_twitch_chat_context:
            twitch_chat_summary = "\n".join(latest_twitch_chat_context)

        context_prompt = (
            f"SYSTEM: This is your internal monologue. Use it to inform your answer based on recent events.\n"
            f"--- What you've recently seen (last {CONTEXT_TIME_WINDOW_SECONDS}s) ---\n{vision_summary}\n\n"
            f"--- What you've recently heard spoken (last {CONTEXT_TIME_WINDOW_SECONDS}s) ---\n{spoken_word_summary}\n\n"
            f"--- What you've recently heard (last {CONTEXT_TIME_WINDOW_SECONDS}s) ---\n{audio_summary}\n\n"
            f"--- Recent messages in Twitch chat ---\n{twitch_chat_summary}\n"
            f"--- END OF CONTEXT ---\n"
            f"Now, respond to the user as peepingnami."
        )
        return context_prompt