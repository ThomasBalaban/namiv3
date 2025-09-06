# nami/twitch_integration/chat_interface.py

import asyncio
import threading
import time
from . import twitch_chat
from ..config import TARGET_CHANNEL
from ..bot_core import add_message, ask_question, BOTNAME

# --- NEW: Global variable to hold the input funnel ---
input_funnel = None

# Message handling lock
message_lock = asyncio.Lock()

# Store the event loop and thread for async operations
is_twitch_running = False

async def handle_twitch_message(msg):
    """Processes incoming messages from Twitch and routes them to the bot core."""
    global input_funnel
    async with message_lock:
        user_message = msg.text
        username = msg.user.name

        if username.lower() == BOTNAME.lower():
            return

        mention_keywords = ['nami', BOTNAME.lower()]
        is_mention = any(keyword in user_message.lower() for keyword in mention_keywords)

        # --- UPDATED LOGIC ---
        # If it's a mention and the input funnel is available, use it to enable TTS
        if is_mention and input_funnel:
            print(f"Processing Twitch mention via InputFunnel: {username}: {user_message}")
            formatted_input = f"{username} in chat: {user_message}"
            
            # Add to funnel with high priority and the 'use_tts' flag set to True
            input_funnel.add_input(
                content=formatted_input,
                priority=0.2,  # High priority (low number)
                source_info={
                    'source': 'TWITCH_MENTION',
                    'username': username,
                    'is_direct': True,
                    'use_tts': True  # This flag triggers the voice
                }
            )
        # Fallback for non-mentions or if funnel is not used
        else:
            if not is_mention:
                print(f"Ignoring message (no bot mention): {username}: {user_message}")
                return

            print(f"Processing message directly (no funnel): {username}: {user_message}")
            add_message("user", f"{username}: {user_message}")

            loop = asyncio.get_event_loop()
            bot_reply = await loop.run_in_executor(None, ask_question, f"{username}: {user_message}")

            if bot_reply:
                await send_to_twitch_internal(bot_reply)
        # --- END UPDATED LOGIC ---

# (The rest of the file remains the same)

twitch_message_queue = asyncio.Queue()

async def send_to_twitch_internal(message):
    """Sends a message to the Twitch chat."""
    print(f"Sending to Twitch: {message[:50]}...")
    chat = twitch_chat.get_chat()
    if chat:
        try:
            await chat.send_message(TARGET_CHANNEL, message)
            print(f"Message sent to Twitch successfully: {message[:50]}...")
        except Exception as e:
            print(f"Error sending to Twitch: {e}")
    else:
        print("Failed to send message to Twitch: Chat not initialized")

def send_to_twitch_sync(message):
    """Adds a message to the Twitch message queue from a synchronous context."""
    if is_twitch_running:
        try:
            asyncio.run_coroutine_threadsafe(twitch_message_queue.put(message), asyncio.get_running_loop())
        except RuntimeError:
            print("Cannot queue message: Twitch event loop not running.")
    else:
        print("Cannot send to Twitch: Twitch bot not running")

async def run_twitch_chat():
    """Initializes and runs the Twitch chat bot."""
    global is_twitch_running
    is_twitch_running = True

    await twitch_chat.setup_chat(handle_twitch_message)

    print("Twitch chat bot is running and processing messages!")

    while is_twitch_running:
        message = await twitch_message_queue.get()
        await send_to_twitch_internal(message)
        twitch_message_queue.task_done()

def start_twitch_chat_thread():
    """Starts the asyncio event loop for the Twitch bot in a new thread."""
    asyncio.run(run_twitch_chat())

def init_twitch_bot(handler=None, funnel=None):
    """Initializes the Twitch chat bot in a background thread."""
    global input_funnel
    print("Initializing Twitch bot...")

    # --- NEW: Set the funnel instance ---
    if funnel:
        input_funnel = funnel
        print("InputFunnel connected to Twitch interface.")

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