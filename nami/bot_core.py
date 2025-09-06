# nami/bot_core.py

import requests
import json
import re
from nami.hard_filter import banned_words

# Constants
OLLAMA_API_URL = "http://localhost:11434/api/chat"
BOTNAME = "peepingnami"

# Global state
conversation_history = []
MAX_CONVERSATION_LENGTH = 8

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
    global conversation_history

    # --- ENHANCED LOGGING ---
    # This will print the exact history being sent to the AI for this question.
    print("\n--- CONVERSATION HISTORY SENT TO AI ---")
    print(json.dumps(conversation_history, indent=2))
    print("---------------------------------------\n")
    # --- END ENHANCED LOGGING ---

    add_message("user", question)

    try:
        payload = {
            "model": "peepingnami",
            "messages": conversation_history,
            "stream": True,
        }

        response = requests.post(
            OLLAMA_API_URL,
            json=payload,
            stream=True
        )

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

def start_bot_console():
    """Starts the bot with console interaction."""
    print(f"BOT_CORE.PY:  {BOTNAME} is ready. Start chatting!")

    while True:
        question = input("You: ")

        if question.lower() == "exit":
            print("Goodbye!")
            break
        elif question.lower() == "vision check":
            print("Checking vision queue...")
            continue

        ask_question(question)