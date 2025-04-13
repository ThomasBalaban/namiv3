import asyncio
import threading
import inspect
import time
from nami import twitch_chat
from nami.config import TARGET_CHANNEL
from nami.bot_core import add_message, ask_question, BOTNAME


# Import the ResponseHandler (if available)
try:
    from nami.input_systems.priority_integration import get_response_handler
    from nami.input_systems.priority_core import InputItem, InputSource
except ImportError:
    # Fallback if imports aren't available
    get_response_handler = lambda: None
    InputItem = None
    InputSource = None

# Message handling lock
message_lock = asyncio.Lock()

# Store the event loop and thread for async operations
twitch_event_loop = None
twitch_thread_id = None
is_twitch_running = False

# Callback function to handle Twitch chat messages
async def handle_twitch_message(msg):
    async with message_lock:
        # Extract the message content and sender
        user_message = msg.text
        username = msg.user.name
        
        # Prevent the bot from responding to its own messages
        if username.lower() == BOTNAME.lower():
            return
        
        # Log the message for debugging
        print(f"Received message from {username}: {user_message}")
        
        # Get the response handler if available
        response_handler = get_response_handler() if callable(get_response_handler) else None
        
        # Check if we should process with priority system and response handler
        if response_handler and InputItem and InputSource:
            # Determine if this is a direct mention of the bot
            is_mention = 'nami' in user_message.lower() or 'peepingnami' in user_message.lower()
            input_source = InputSource.TWITCH_MENTION if is_mention else InputSource.TWITCH_CHAT
            
            # Only process mentions, unless we're processing all chat
            if not is_mention and input_source == InputSource.TWITCH_CHAT:
                return
            
            print(f"Processing message via ResponseHandler: {username}: {user_message}")
            
            # Create an input item for the response handler
            input_item = InputItem(
                text=user_message,
                source=input_source,
                timestamp=asyncio.get_event_loop().time(),
                metadata={'username': username}
            )
            
            # Process via the response handler
            # If response handler is synchronous, run it in an executor
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, response_handler.handle_prioritized_input, input_item)
        else:
            # Fallback to direct processing if no response handler
            # Only process if it contains 'nami' or 'peepingnami'
            if not ('nami' in user_message.lower() or 'peepingnami' in user_message.lower()):
                print(f"Ignoring message (no bot mention): {username}: {user_message}")
                return
                
            print(f"Processing message directly: {username}: {user_message}")
            
            # Append the user message to the conversation history using the helper
            add_message("user", f"{username}: {user_message}")
            
            # If ask_question is blocking, run it in an executor
            loop = asyncio.get_event_loop()
            bot_reply = await loop.run_in_executor(None, ask_question, f"{username}: {user_message}")
            
            # Send the bot's response back to Twitch chat
            chat = twitch_chat.get_chat()
            if chat and bot_reply:
                # Try different sending methods
                try:
                    # First try send method
                    if hasattr(chat, 'send'):
                        await chat.send(TARGET_CHANNEL, bot_reply)
                    # Then try send_message method
                    elif hasattr(chat, 'send_message'):
                        await chat.send_message(TARGET_CHANNEL, bot_reply)
                    else:
                        print(f"No suitable send method found in chat object. Available methods: {dir(chat)}")
                    print(f"Sent response to Twitch: {bot_reply[:50]}...")
                except Exception as e:
                    print(f"Error sending to Twitch: {e}")

# Global queue for messages to be sent to Twitch
twitch_message_queue = []

# Function to run in the Twitch thread to process message queue
async def process_message_queue():
    global twitch_message_queue
    
    while is_twitch_running:
        # Process any queued messages
        if twitch_message_queue:
            message = twitch_message_queue.pop(0)
            await send_to_twitch_internal(message)
        
        # Wait a bit before checking again
        await asyncio.sleep(0.1)

# Internal function to send a message to Twitch chat (called from the Twitch thread)
async def send_to_twitch_internal(message):
    """Send a message to the Twitch chat (internal implementation)"""
    print(f"Sending to Twitch: {message[:50]}...")
    chat = twitch_chat.get_chat()
    if chat:
        try:
            # Try different sending methods
            if hasattr(chat, 'send'):
                await chat.send(TARGET_CHANNEL, message)
            elif hasattr(chat, 'send_message'):
                await chat.send_message(TARGET_CHANNEL, message)
            else:
                print(f"No suitable send method found in chat object. Available methods: {dir(chat)}")
                return
            print(f"Message sent to Twitch successfully: {message[:50]}...")
        except Exception as e:
            print(f"Error sending to Twitch: {e}")
    else:
        print(f"Failed to send message to Twitch: Chat not initialized")

# Function to add a message to the queue (can be called from any thread)
def send_to_twitch_sync(message):
    """Add a message to the Twitch message queue"""
    global twitch_message_queue, is_twitch_running
    
    if is_twitch_running:
        print(f"Queueing message for Twitch: {message[:50]}...")
        twitch_message_queue.append(message)
    else:
        print("Cannot send to Twitch: Twitch bot not running")

async def run_twitch_chat():
    """
    Initialize and run the Twitch chat bot.
    """
    global twitch_event_loop, twitch_thread_id, is_twitch_running
    
    # Store the event loop and thread ID
    twitch_event_loop = asyncio.get_event_loop()
    twitch_thread_id = threading.get_ident()
    is_twitch_running = True
    
    print(f"Twitch thread ID: {twitch_thread_id}")
    print(f"Twitch event loop ID: {id(twitch_event_loop)}")
    print("Setting up Twitch chat...")
    
    # Find the setup function in the twitch_chat module
    setup_func = None
    for attr_name in dir(twitch_chat):
        attr = getattr(twitch_chat, attr_name)
        if inspect.iscoroutinefunction(attr) and ('setup' in attr_name.lower() or 'init' in attr_name.lower() or 'start' in attr_name.lower()):
            setup_func = attr
            print(f"Found setup function: {attr_name}")
            break
    
    if setup_func:
        # Call the setup function
        await setup_func()
    else:
        print("WARNING: Could not find a setup function in the twitch_chat module")
        print(f"Available functions: {[name for name in dir(twitch_chat) if callable(getattr(twitch_chat, name))]}")
    
    print("Twitch chat bot is running!")
    
    # Start the message queue processor
    asyncio.create_task(process_message_queue())
    
    # Keep the event loop running
    while is_twitch_running:
        await asyncio.sleep(1)

def start_twitch_chat():
    """
    Start the Twitch chat bot in a separate event loop.
    """
    # Set up message callback
    try:
        # Try different ways to set the message callback
        if hasattr(twitch_chat, 'message_callback') and not callable(getattr(twitch_chat, 'message_callback')):
            # If message_callback is a variable, set it directly
            twitch_chat.message_callback = handle_twitch_message
            print("Set message_callback directly")
        elif hasattr(twitch_chat, 'set_message_callback') and callable(getattr(twitch_chat, 'set_message_callback')):
            # If set_message_callback is a function, call it
            twitch_chat.set_message_callback(handle_twitch_message)
            print("Called set_message_callback function")
        else:
            print("WARNING: Could not find a way to set the message callback in twitch_chat module")
            print(f"Available attributes: {dir(twitch_chat)}")
    except Exception as e:
        print(f"Error setting message callback: {e}")
    
    # Start the async loop
    asyncio.run(run_twitch_chat())

def init_twitch_bot(handler=None):
    """Initialize the Twitch chat bot in a background thread"""
    print("Initializing Twitch bot...")
    print(f"Available in twitch_chat module: {dir(twitch_chat)}")
    
    # If a response handler was provided, set the Twitch send callback
    if handler:
        handler.set_twitch_send_callback(send_to_twitch_sync)
        print(f"Registered Twitch callback with ResponseHandler")
    
    # Start the Twitch chat bot in a separate thread
    twitch_thread = threading.Thread(target=start_twitch_chat)
    twitch_thread.daemon = True  # Set as daemon so it exits when the main thread exits
    twitch_thread.start()
    
    # Give the thread a moment to initialize
    time.sleep(1)
    
    return twitch_thread

def shutdown_twitch_bot():
    """Shutdown the Twitch bot"""
    global is_twitch_running
    is_twitch_running = False
    print("Twitch bot shutdown requested")