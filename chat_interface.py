import asyncio
import threading
from twitch_chat import setup_chat, get_chat, set_message_callback
from config import TARGET_CHANNEL
from bot_core import add_message, ask_question, BOTNAME

# Message handling lock
message_lock = asyncio.Lock()

# Callback function to handle Twitch chat messages
async def handle_twitch_message(msg):
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
        if chat and bot_reply:
            await chat.send_message(TARGET_CHANNEL, f"{bot_reply}")

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
    # Set the callback function for Twitch chat messages
    set_message_callback(handle_twitch_message)
    
    # Start the async loop
    asyncio.run(run_twitch_chat())
    
def init_twitch_bot():
    """Initialize the Twitch chat bot in a background thread"""
    # Start the Twitch chat bot in a separate thread
    twitch_thread = threading.Thread(target=start_twitch_chat)
    twitch_thread.daemon = True  # Set as daemon so it exits when the main thread exits
    twitch_thread.start()
    return twitch_thread