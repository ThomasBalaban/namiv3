import asyncio
import threading
import time
from . import twitch_chat
from ..config import TARGET_CHANNEL
from ..bot_core import BOTNAME
# --- MODIFIED: Import the correct, centralized message handler ---
from ..input_systems import handle_twitch_message as process_incoming_message
from ..ui.server import emit_twitch_message

input_funnel = None
message_lock = asyncio.Lock()
is_twitch_running = False
twitch_event_loop = None

# --- MODIFIED: This function is now a simple bridge to the main input system ---
async def handle_twitch_message(msg):
    """
    Handles all incoming Twitch messages.
    1. Emits the message to the UI for display.
    2. Passes the message to the centralized input handler for context/reply processing.
    """
    async with message_lock:
        # Don't process the bot's own messages
        if msg.user.name.lower() == BOTNAME.lower():
            return
        
        # Emit every message to the UI so the panel is a true reflection of chat
        emit_twitch_message(msg.user.name, msg.text)

        # Process the message through the proper input system handler
        # This handler knows how to route mentions vs. regular chat for context
        await process_incoming_message(msg, botname=BOTNAME)


twitch_message_queue = asyncio.Queue()

async def send_to_twitch_internal(message):
    chat = twitch_chat.get_chat()
    if chat:
        try:
            await chat.send_message(TARGET_CHANNEL, message)
            print(f"[TWITCH] Sent: {message[:50]}...")
        except Exception as e:
            print(f"Error sending to Twitch: {e}")
    else:
        print("Failed to send message to Twitch: Chat not initialized")

def send_to_twitch_sync(message):
    global twitch_event_loop
    if is_twitch_running and twitch_event_loop:
        try:
            asyncio.run_coroutine_threadsafe(twitch_message_queue.put(message), twitch_event_loop)
        except Exception as e:
            print(f"Error queueing message for Twitch: {e}")
    else:
        print("Cannot send to Twitch: Twitch bot not running or loop not available.")

async def run_twitch_chat():
    global is_twitch_running, twitch_event_loop
    is_twitch_running = True
    twitch_event_loop = asyncio.get_running_loop()
    await twitch_chat.setup_chat(handle_twitch_message)
    print("Twitch chat bot is running and processing messages!")
    while is_twitch_running:
        message = await twitch_message_queue.get()
        await send_to_twitch_internal(message)
        twitch_message_queue.task_done()

def start_twitch_chat_thread():
    asyncio.run(run_twitch_chat())

def init_twitch_bot(handler=None, funnel=None):
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
    global is_twitch_running
    is_twitch_running = False
    print("Twitch bot shutdown requested")