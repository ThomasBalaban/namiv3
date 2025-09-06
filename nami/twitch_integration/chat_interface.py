import asyncio
import threading
import time
from . import twitch_chat
from ..config import TARGET_CHANNEL
from ..bot_core import add_message, ask_question, BOTNAME
# --- ADDED: Import UI emitter ---
from ..ui.server import emit_twitch_message

input_funnel = None
message_lock = asyncio.Lock()
is_twitch_running = False
twitch_event_loop = None

async def handle_twitch_message(msg):
    global input_funnel
    async with message_lock:
        user_message = msg.text
        username = msg.user.name

        if username.lower() == BOTNAME.lower():
            return
        
        # --- ADDED: Send message to UI ---
        emit_twitch_message(username, user_message)

        mention_keywords = ['nami', BOTNAME.lower()]
        is_mention = any(keyword in user_message.lower() for keyword in mention_keywords)

        if is_mention and input_funnel:
            print(f"Processing Twitch mention via InputFunnel: {username}: {user_message}")
            formatted_input = f"{username} in chat: {user_message}"
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
        else:
            if not is_mention:
                return

            print(f"Processing message directly (no funnel): {username}: {user_message}")
            add_message("user", f"{username}: {user_message}")
            loop = asyncio.get_event_loop()
            bot_reply = await loop.run_in_executor(None, ask_question, f"{username}: {user_message}")
            if bot_reply:
                await send_to_twitch_internal(bot_reply)

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
