import time
import requests
import json
import asyncio
import re
from hard_filter import banned_words

# Constants
OLLAMA_API_URL = "http://localhost:11434/api/chat"
BOTNAME = "peepingnami"  # Bot's name

# Global state
conversation_history = []  # Initialize an empty list to store conversation history
MAX_CONVERSATION_LENGTH = 8
message_lock = asyncio.Lock()  # Create an asyncio lock to prevent concurrent message handling.

def censor_text(text):
    """Replace banned words with "*filtered*" """
    # Create a regex pattern that matches any of the banned words (case-insensitive)
    pattern = re.compile("|".join(re.escape(word) for word in banned_words), flags=re.IGNORECASE)
    # Replace any banned word with "*filtered*"
    return pattern.sub("*filtered*", text)

def add_message(role, content):
    """Add a message to the conversation history, maintaining max length"""
    global conversation_history
    # Append the new message
    conversation_history.append({"role": role, "content": content})
    
    # If the history exceeds the limit, remove the oldest messages
    while len(conversation_history) > MAX_CONVERSATION_LENGTH:
        conversation_history.pop(0)

def ask_question(question):
    """Send a question to the Ollama API and return the bot's response."""
    global conversation_history

    print(conversation_history)

    # Add the user's question to the conversation history
    add_message("user", question)

    try:
        # Prepare the payload for the API request
        payload = {
            "model": "peepingnami",  # Specify the model to use
            "messages": conversation_history,     # Pass the conversation history
            "stream": True,         # Enable streaming for real-time responses
        }

        # Send the HTTP POST request to the Ollama API
        response = requests.post(
            OLLAMA_API_URL,
            json=payload,
            stream=True  # Enable streaming for the response
        )

        # Check if the request was successful
        if response.status_code != 200:
            raise Exception(f"API request failed with status code {response.status_code}")

        # Print the bot's response in real-time
        print("PeepingNami: ", end="", flush=True)
        bot_reply = ""

        # Process the streaming response
        for chunk in response.iter_lines():
            if chunk:
                # Parse the JSON chunk
                chunk_data = json.loads(chunk.decode("utf-8"))
                # Access the content from the "message" key
                part = chunk_data.get("message", {}).get("content", "")
                # Censor any banned words in the chunk
                part = censor_text(part)
                bot_reply += part
                print(part, end="", flush=True)

        print()  # Print a newline after the response is complete

        # Add the bot's reply to the conversation history
        add_message("assistant", bot_reply)

        return bot_reply  # Return the bot's reply

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
            # This will be handled by the main module
            print("Checking vision queue...")
            continue

        # Directly interact with the bot via its Python API
        ask_question(question)