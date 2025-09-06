import requests
import json
import re
from threading import Lock # MODIFIED: Correctly import Lock from threading
from nami.hard_filter import banned_words

# Constants
OLLAMA_API_URL = "http://localhost:11434/api/chat"
BOTNAME = "peepingnami"

# --- NEW: Dedicated Context Storage ---
# These variables will hold the most recent piece of information from vision and audio.
# They are kept separate from the main conversation history to avoid pollution.
latest_vision_context = "You can't see anything right now."
latest_audio_context = "You can't hear anything right now."
context_lock = Lock() # MODIFIED: Use the correct Lock object

# Global state for conversation
conversation_history = []
MAX_CONVERSATION_LENGTH = 10

def update_vision_context(text: str):
    """Thread-safely updates the latest vision context."""
    global latest_vision_context
    with context_lock:
        latest_vision_context = text

def update_audio_context(text: str):
    """Thread-safely updates the latest audio context."""
    global latest_audio_context
    with context_lock:
        latest_audio_context = text

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
    global conversation_history, latest_vision_context, latest_audio_context

    add_message("user", question)

    try:
        # --- MODIFIED: Context Injection ---
        # Create a temporary, context-aware message history for this specific query.
        # This ensures the bot is always aware without polluting her main memory.
        with context_lock:
            context_prompt = (
                f"SYSTEM: This is your internal monologue. Use it to inform your answer. "
                f"You are currently seeing: '{latest_vision_context}'. "
                f"You are currently hearing: '{latest_audio_context}'. "
                f"Now, respond to the user as peepingnami."
            )
        
        # Prepend the system context prompt to the current conversation
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

