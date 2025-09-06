# nami/twitch_integration/chat_interface.py

import asyncio
import threading
import time
from . import twitch_chat
from ..config import TARGET_CHANNEL
from ..bot_core import add_message, ask_question, BOTNAME

# Global variable to hold the input funnel
input_funnel = None

# Message handling lock
message_lock = asyncio.Lock()

# --- MODIFIED: Store the event loop and thread for async operations ---
is_twitch_running = False
twitch_event_loop = None # ADDED: To store a reference to the correct event loop

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

        # If it's a mention and the input funnel is available, use it to enable TTS
        if is_mention and input_funnel:
            print(f"Processing Twitch mention via InputFunnel: {username}: {user_message}")
            formatted_input = f"{username} in chat: {user_message}"
            
            # Add to funnel with high priority and the 'use_tts' flag set to True
            input_funnel.add_input(
                content=formatted_input,
                priority=0.2,
                source_info={
                    'source': 'TWITCH_MENTION',
                    'username': username,
                    'is_direct': True,
                    'use_tts': True
                }
            )
        # Fallback for non-mentions or if funnel is not used
        else:
            if not is_mention:
                return

            print(f"Processing message directly (no funnel): {username}: {user_message}")
            add_message("user", f"{username}: {user_message}")

            loop = asyncio.get_event_loop()
            bot_reply = await loop.run_in_executor(None, ask_question, f"{username}: {user_message}")

            if bot_reply:
                await send_to_twitch_internal(bot_reply)

# Global queue for messages to be sent to Twitch
twitch_message_queue = asyncio.Queue()

async def send_to_twitch_internal(message):
    """Sends a message to the Twitch chat."""
    chat = twitch_chat.get_chat()
    if chat:
        try:
            await chat.send_message(TARGET_CHANNEL, message)
            print(f"[TWITCH] Sent: {message[:50]}...")
        except Exception as e:
            print(f"Error sending to Twitch: {e}")
    else:
        print("Failed to send message to Twitch: Chat not initialized")

# --- MODIFIED: Function to add a message to the queue (can be called from any thread) ---
def send_to_twitch_sync(message):
    """Adds a message to the Twitch message queue from a synchronous context."""
    global twitch_event_loop
    if is_twitch_running and twitch_event_loop:
        try:
            # Use the stored event loop to safely queue the message
            asyncio.run_coroutine_threadsafe(twitch_message_queue.put(message), twitch_event_loop)
        except Exception as e:
            print(f"Error queueing message for Twitch: {e}")
    else:
        print("Cannot send to Twitch: Twitch bot not running or loop not available.")

# --- MODIFIED: This function now captures and stores the event loop ---
async def run_twitch_chat():
    """Initializes and runs the Twitch chat bot."""
    global is_twitch_running, twitch_event_loop
    is_twitch_running = True
    twitch_event_loop = asyncio.get_running_loop() # ADDED: Capture the loop

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

    if funnel:
        input_funnel = funnel
        print("InputFunnel connected to Twitch interface.")

    if handler:
        handler.set_twitch_send_callback(send_to_twitch_sync)
        print("Registered Twitch callback with ResponseHandler")

    twitch_thread = threading.Thread(target=start_twitch_chat_thread, daemon=True)
    twitch_thread.start()

    time.sleep(1)
    return twitch_thread

def shutdown_twitch_bot():
    """Shutdown the Twitch bot."""
    global is_twitch_running
    is_twitch_running = False
    print("Twitch bot shutdown requested")