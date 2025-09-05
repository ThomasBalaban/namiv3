# nami/twitch_integration/twitch_chat.py

from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.type import AuthScope, ChatEvent
from twitchAPI.chat import Chat, EventData, ChatMessage, ChatCommand
from ..config import APP_ID, APP_SECRET, TARGET_CHANNEL  # UPDATED IMPORT

USER_SCOPE = [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT]

# Global variable to store the chat object
chat_instance = None

# this will be called when the event READY is triggered, which will be on bot start
async def on_ready(ready_event: EventData):
    """Callback for when the bot is ready."""
    print('Twitch bot is ready, joining channel...')
    await ready_event.chat.join_room(TARGET_CHANNEL)
    print(f"Successfully joined channel: {TARGET_CHANNEL}")

# this will be called whenever the !reply command is issued for testing
async def test_command(cmd: ChatCommand):
    """A simple test command."""
    if len(cmd.parameter) == 0:
        await cmd.reply('you did not tell me what to reply with')
    else:
        await cmd.reply(f'{cmd.user.name}: {cmd.parameter}')

async def setup_chat(message_handler):
    """
    Sets up the Twitch API, authenticates, and starts the chat client.

    Args:
        message_handler: The async function to call when a message is received.
    """
    global chat_instance
    print("Setting up Twitch API...")
    twitch = await Twitch(APP_ID, APP_SECRET)

    auth = UserAuthenticator(twitch, USER_SCOPE, force_verify=True)
    token, refresh_token = await auth.authenticate()
    await twitch.set_user_authentication(token, USER_SCOPE, refresh_token)
    print("Twitch authentication successful.")

    # create chat instance
    chat_instance = await Chat(twitch)

    # create a handler for incoming messages
    async def on_message(msg: ChatMessage):
        """Callback for when a new message is sent in chat."""
        # Forward the message to the main application's handler
        if message_handler:
            await message_handler(msg)

    # register the handlers for the events
    chat_instance.register_event(ChatEvent.READY, on_ready)
    chat_instance.register_event(ChatEvent.MESSAGE, on_message)
    chat_instance.register_command('reply', test_command)

    # start the chat bot
    chat_instance.start()
    print("Twitch chat client started.")

    return chat_instance

def get_chat():
    """Returns the global chat instance."""
    global chat_instance
    return chat_instance