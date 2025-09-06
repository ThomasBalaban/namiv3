import requests
import json
import re
import time
from threading import Lock
from nami.hard_filter import banned_words

# Constants
OLLAMA_API_URL = "http://localhost:11434/api/chat"
BOTNAME = "peepingnami"

# --- MODIFIED: Context now uses a time window for Vision and Audio ---
CONTEXT_TIME_WINDOW_SECONDS = 30
latest_vision_context = []  # List of (timestamp, text)
latest_audio_context = []   # List of (timestamp, text)
latest_twitch_chat_context = []
MAX_TWITCH_CONTEXT_LENGTH = 5

# Global state for conversation
conversation_history = []
MAX_CONVERSATION_LENGTH = 30

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
        # Prune entries older than the time window
        latest_vision_context = [(ts, txt) for ts, txt in latest_vision_context if now - ts <= CONTEXT_TIME_WINDOW_SECONDS]

def update_audio_context(text: str):
    """Thread-safely updates audio context, keeping entries within the time window."""
    global latest_audio_context
    with context_lock:
        now = time.time()
        latest_audio_context.append((now, text))
        # Prune entries older than the time window
        latest_audio_context = [(ts, txt) for ts, txt in latest_audio_context if now - ts <= CONTEXT_TIME_WINDOW_SECONDS]

def censor_text(text):
    """Replace banned words with "*filtered*" """
    pattern = re.compile("|".join(re.escape(word) for word in banned_words), flags=re.IGNORECASE)
    return pattern.sub("*filtered*", text)

def add_message(role, content):
    """Add a message to the conversation history, maintaining max length"""
    global conversation_history
    conversation_history.append({"role": role, "content": content})
    while len(conversation_history) > MAX_CONVERSATION_LENGTH:
        conversation_history.pop(0)

def ask_question(question):
    """Send a question to the Ollama API and return the bot's response."""
    global conversation_history, latest_vision_context, latest_audio_context, latest_twitch_chat_context

    add_message("user", question)

    try:
        with context_lock:
            # Format vision context from the list
            vision_summary = "You haven't seen anything recently."
            if latest_vision_context:
                vision_texts = [text for timestamp, text in latest_vision_context]
                vision_summary = "\n".join(vision_texts)

            # Format audio context from the list
            audio_summary = "You haven't heard anything recently."
            if latest_audio_context:
                audio_texts = [text for timestamp, text in latest_audio_context]
                audio_summary = "\n".join(audio_texts)
            
            # Format twitch chat
            twitch_chat_summary = "Nothing new in chat."
            if latest_twitch_chat_context:
                twitch_chat_summary = "\n".join(latest_twitch_chat_context)

            context_prompt = (
                f"SYSTEM: This is your internal monologue. Use it to inform your answer based on recent events.\n"
                f"--- What you've recently seen (last {CONTEXT_TIME_WINDOW_SECONDS}s) ---\n{vision_summary}\n\n"
                f"--- What you've recently heard (last {CONTEXT_TIME_WINDOW_SECONDS}s) ---\n{audio_summary}\n\n"
                f"--- Recent messages in Twitch chat ---\n{twitch_chat_summary}\n"
                f"--- END OF CONTEXT ---\n"
                f"Now, respond to the user as peepingnami."
            )
        
        messages_with_context = [{"role": "system", "content": context_prompt}] + conversation_history

        payload = {
            "model": "peepingnami",
            "messages": messages_with_context,
            "stream": True,
        }

        response = requests.post(OLLAMA_API_URL, json=payload, stream=True)
        if response.status_code != 200:
            raise Exception(f"API request failed with status code {response.status_code}")

        print("PeepingNami: ", end="", flush=True)
        bot_reply = ""
        for chunk in response.iter_lines():
            if chunk:
                chunk_data = json.loads(chunk.decode("utf-8"))
                part = chunk_data.get("message", {}).get("content", "")
                part = censor_text(part)
                bot_reply += part
                print(part, end="", flush=True)
        print()

        add_message("assistant", bot_reply)
        return bot_reply

    except Exception as error:
        print(f"An error occurred: {error}")
        return None