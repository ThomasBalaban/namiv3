# nami/twitch_integration/chat_interface.py

import asyncio
import threading
import time
from . import twitch_chat
from ..config import TARGET_CHANNEL
from ..bot_core import add_message, ask_question, BOTNAME

# Import the ResponseHandler (if available)
try:
    from ..input_systems.priority_integration import get_response_handler
    from ..input_systems.priority_core import InputItem, InputSource
except ImportError:
    # Fallback if imports aren't available
    get_response_handler = lambda: None
    InputItem = None
    InputSource = None

# Message handling lock
message_lock = asyncio.Lock()

# Store the event loop and thread for async operations
is_twitch_running = False

# Callback function to handle Twitch chat messages
async def handle_twitch_message(msg):
    """Processes incoming messages from Twitch and routes them to the bot core."""
    async with message_lock:
        user_message = msg.text
        username = msg.user.name

        # Prevent the bot from responding to its own messages
        if username.lower() == BOTNAME.lower():
            return

        # --- FIX 1: Broader mention detection ---
        mention_keywords = ['nami', BOTNAME.lower()]
        is_mention = any(keyword in user_message.lower() for keyword in mention_keywords)

        response_handler = get_response_handler() if callable(get_response_handler) else None

        # Check if we should process with priority system and response handler
        if response_handler and InputItem and InputSource:
            input_source = InputSource.TWITCH_MENTION if is_mention else InputSource.TWITCH_CHAT

            # Create an input item for the response handler
            input_item = InputItem(
                text=user_message,
                source=input_source,
                timestamp=asyncio.get_event_loop().time(),
                metadata={'username': username}
            )

            # Process via the response handler
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, response_handler.handle_prioritized_input, input_item)
        else:
            # Fallback to direct processing if no response handler
            if not is_mention:
                print(f"Ignoring message (no bot mention): {username}: {user_message}")
                return

            print(f"Processing message directly: {username}: {user_message}")
            add_message("user", f"{username}: {user_message}")

            loop = asyncio.get_event_loop()
            bot_reply = await loop.run_in_executor(None, ask_question, f"{username}: {user_message}")

            if bot_reply:
                await send_to_twitch_internal(bot_reply)

# Global queue for messages to be sent to Twitch
twitch_message_queue = asyncio.Queue()

# Internal function to send a message to Twitch chat
async def send_to_twitch_internal(message):
    """Sends a message to the Twitch chat."""
    print(f"Sending to Twitch: {message[:50]}...")
    chat = twitch_chat.get_chat()
    if chat:
        try:
            # --- FIX 2: Use the correct method name 'send_message' ---
            await chat.send_message(TARGET_CHANNEL, message)
            print(f"Message sent to Twitch successfully: {message[:50]}...")
        except Exception as e:
            print(f"Error sending to Twitch: {e}")
    else:
        print("Failed to send message to Twitch: Chat not initialized")

# Function to add a message to the queue (can be called from any thread)
def send_to_twitch_sync(message):
    """Adds a message to the Twitch message queue from a synchronous context."""
    if is_twitch_running:
        try:
            # Since the queue is an asyncio queue, we must call this from the loop
            asyncio.run_coroutine_threadsafe(twitch_message_queue.put(message), asyncio.get_running_loop())
        except RuntimeError:
            print("Cannot queue message: Twitch event loop not running.")
    else:
        print("Cannot send to Twitch: Twitch bot not running")

async def run_twitch_chat():
    """Initializes and runs the Twitch chat bot."""
    global is_twitch_running
    is_twitch_running = True

    # Directly call the setup function with our message handler
    await twitch_chat.setup_chat(handle_twitch_message)

    print("Twitch chat bot is running and processing messages!")

    # Process the outgoing message queue
    while is_twitch_running:
        message = await twitch_message_queue.get()
        await send_to_twitch_internal(message)
        twitch_message_queue.task_done()

def start_twitch_chat_thread():
    """Starts the asyncio event loop for the Twitch bot in a new thread."""
    asyncio.run(run_twitch_chat())

def init_twitch_bot(handler=None):
    """Initializes the Twitch chat bot in a background thread."""
    print("Initializing Twitch bot...")

    if handler:
        handler.set_twitch_send_callback(send_to_twitch_sync)
        print("Registered Twitch callback with ResponseHandler")

    twitch_thread = threading.Thread(target=start_twitch_chat_thread, daemon=True)
    twitch_thread.start()

    time.sleep(1) # Give the thread a moment to initialize
    return twitch_thread

def shutdown_twitch_bot():
    """Shutdown the Twitch bot."""
    global is_twitch_running
    is_twitch_running = False
    print("Twitch bot shutdown requested")