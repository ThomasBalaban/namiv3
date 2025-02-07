from twitchAPI.twitch import Twitch
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.type import AuthScope, ChatEvent
from twitchAPI.chat import Chat, EventData, ChatMessage, ChatSub, ChatCommand
import asyncio
from config import APP_ID, APP_SECRET

USER_SCOPE = [AuthScope.CHAT_READ, AuthScope.CHAT_EDIT]
TARGET_CHANNEL = 'peepingotter'

# Global variable to store the chat object
chat = None

# Callback to forward messages to the local chatbot
message_callback = None

# Set a callback function to handle messages
def set_message_callback(callback):
    global message_callback
    message_callback = callback

# this will be called when the event READY is triggered, which will be on bot start
async def on_ready(ready_event: EventData):
    print('Bot is ready for work, joining channels')
    await ready_event.chat.join_room(TARGET_CHANNEL)

# this will be called whenever a message in a channel was sent by either the bot OR another user
async def on_message(msg: ChatMessage):
    print(f'in {msg.room.name}, {msg.user.name} said: {msg.text}')
    if message_callback:
        await message_callback(msg)  # Forward the message to the local chatbot

# this will be called whenever the !reply command is issued
async def test_command(cmd: ChatCommand):
    if len(cmd.parameter) == 0:
        await cmd.reply('you did not tell me what to reply with')
    else:
        await cmd.reply(f'{cmd.user.name}: {cmd.parameter}')

# this is where we set up the bot
async def setup_chat():
    global chat
    # set up twitch api instance and add user authentication with some scopes
    twitch = await Twitch(APP_ID, APP_SECRET)
    auth = UserAuthenticator(twitch, USER_SCOPE)
    token, refresh_token = await auth.authenticate()
    await twitch.set_user_authentication(token, USER_SCOPE, refresh_token)

    # create chat instance
    chat = await Chat(twitch)

    # register the handlers for the events you want
    chat.register_event(ChatEvent.READY, on_ready)
    chat.register_event(ChatEvent.MESSAGE, on_message)
    chat.register_command('reply', test_command)

    # start the chat bot
    chat.start()

    return chat

# Function to stop the chat bot
async def stop_chat():
    global chat
    if chat:
        chat.stop()
        await chat.twitch.close()

# Function to get the chat object
def get_chat():
    global chat
    return chat