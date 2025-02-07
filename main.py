from ollama import chat
import sys
import threading
import asyncio
from twitch_chat import setup_chat, get_chat, set_message_callback  # Import the new set_message_callback function
from config import TARGET_CHANNEL

BOTNAME = "peepingnami"  # Bot's name
conversation_history = []  # Initialize an empty list to store conversation history

# Callback function to handle Twitch chat messages
async def handle_twitch_message(msg):
    global conversation_history

    # Extract the message content and sender
    user_message = msg.text
    username = msg.user.name

    # Append the user message to the conversation history
    conversation_history.append({"role": "user", "content": user_message})

    # Get the bot's response
    bot_reply = ask_question(user_message)

    # Send the bot's response back to Twitch chat
    chat = get_chat()
    if chat:
        await chat.send_message(TARGET_CHANNEL, f"{BOTNAME}: {bot_reply}")

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
    """
    Sends the question to the bot and gets a response using the Ollama Python package.
    This function will now return the bot's reply to be printed elsewhere.
    """
    global conversation_history

    try:
        # Append the user message to the conversation history
        conversation_history.append({"role": "user", "content": question})

        print("Conversation History:", conversation_history, flush=False)  # Optional: for debugging

        # Interact with the bot using the ollama chat function
        stream = chat(
            model='peepingnami',
            messages=conversation_history,  # Pass the entire conversation history
            stream=True,
        )

        print("PeepingNami: ", end='', flush=True)  # Print "PeepingNami: " without a newline
        bot_reply = ""

        # Collect the full bot response
        for chunk in stream:
            bot_reply += chunk['message']['content']
            print(chunk['message']['content'], end='', flush=True)  # Print the chunk's content on the same line

        print()

        # Append the bot's final reply to the conversation history
        conversation_history.append({"role": "assistant", "content": bot_reply})

        return bot_reply  # Return the bot's reply

    except Exception as error:
        print("\nError processing the request:", error)
        return "Something went wrong, please try again later."

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