from ollama import chat
import sys
import threading
import requests
import re
import json
import asyncio
from hard_filter import banned_words
from twitch_chat import setup_chat, get_chat, set_message_callback  # Import the new set_message_callback function
from config import TARGET_CHANNEL

OLLAMA_API_URL = "http://localhost:11434/api/chat"
BOTNAME = "peepingnami"  # Bot's name
conversation_history = []  # Initialize an empty list to store conversation history
MAX_CONVERSATION_LENGTH = 50
message_lock = asyncio.Lock() # Create an asyncio lock to prevent concurrent message handling.


def censor_text(text):
    # List of banned words (all will be replaced with "*filtered*")
    # Create a regex pattern that matches any of the banned words (case-insensitive)
    pattern = re.compile("|".join(re.escape(word) for word in banned_words), flags=re.IGNORECASE)
    # Replace any banned word with "*filtered*"
    return pattern.sub("*filtered*", text)


def add_message(role, content):
    global conversation_history
    # Append the new message
    conversation_history.append({"role": role, "content": content})
    
    # If the history exceeds the limit, remove the oldest messages
    while len(conversation_history) > MAX_CONVERSATION_LENGTH:
        conversation_history.pop(0)


# Callback function to handle Twitch chat messages
async def handle_twitch_message(msg):
    global conversation_history

    async with message_lock:
        # Extract the message content and sender
        user_message = msg.text
        username = msg.user.name

        # Only process the message if it contains 'nami' or 'peepingnami'
        if not ('nami' in user_message.lower() or 'peepingnami' in user_message.lower()):
            return

        # Prevent the bot from responding to its own messages
        if username.lower() == BOTNAME.lower():
            return

        # Append the user message to the conversation history using the helper
        add_message("user", f"{username}: {user_message}")

        # If ask_question is blocking, run it in an executor.
        loop = asyncio.get_event_loop()
        bot_reply = await loop.run_in_executor(None, ask_question, f"{username}: {user_message}")

        # Send the bot's response back to Twitch chat
        chat = get_chat()
        if chat:
            await chat.send_message(TARGET_CHANNEL, f"{bot_reply}")


def start_bot():
    """
    Starts the bot once and enters a continuous interaction loop.
    """
    print(f"{BOTNAME} is ready. Start chatting!")

    while True:
        question = input("You: ")

        if question.lower() == "exit":
            print("Goodbye!")
            break

        # Directly interact with the bot via its Python API
        ask_question(question)


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
            "messages": conversation_history,     # Pass the user's question
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


async def run_twitch_chat():
    """
    Initialize and run the Twitch chat bot.
    """
    await setup_chat()
    print("Twitch chat bot is running!")

def start_twitch_chat():
    """
    Start the Twitch chat bot in a separate event loop.
    """
    asyncio.run(run_twitch_chat())

def main():
    """
    Start both the bot and the Twitch chat listener concurrently.
    """
    # Set the callback function for Twitch chat messages
    set_message_callback(handle_twitch_message)

    # Start the Twitch chat bot in a separate thread
    twitch_thread = threading.Thread(target=start_twitch_chat)
    twitch_thread.start()

    # Start the main bot loop
    start_bot()

    # Optionally, wait for both threads to finish (if needed)
    twitch_thread.join()

if __name__ == "__main__":
    main()