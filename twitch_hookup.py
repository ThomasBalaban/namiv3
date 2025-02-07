import asyncio
import json
import os
from twitchio.ext import commands

ACTIVE_CHANNEL = 'peepingotter'
chatters = []
conversation_data = []


# Bot Configuration
class TwitchBot(commands.Bot):
    def __init__(self):
        super().__init__(
            token="oauth:51ioccg8wrmo5m9dpb9kc039h5i6wc",  # Replace with your OAuth token
            prefix="!",
            initial_channels=[ACTIVE_CHANNEL],
        )

    async def event_ready(self):
        print(f"Logged in as {self.nick}")
        print(f"Connected to channel: {ACTIVE_CHANNEL}")

    async def event_message(self, message):
        # Ignore the bot's own messages
        if message.echo:
            return

        username = message.author.name
        content = message.content

        # Add the user to the chatters list if not already present
        if username not in chatters:
            chatters.append(username)
            print(f"New user added: {username}")

        # Log the message
        chat_entry = {
            "role": "user",
            "content": f"{username}: {content}",
        }
        append_message(chat_entry)

        # Send the message to the bot and get a response
        try:
            bot_reply = await ask_question(content, username)
            conversation_data.append(chat_entry)

            if bot_reply:
                bot_reply_entry = {
                    "role": "assistant",
                    "content": bot_reply,
                }
                conversation_data.append(bot_reply_entry)
                append_message(bot_reply_entry)

                # Reply to the user in Twitch chat
                await message.channel.send(f"@{username} {bot_reply}")
        except Exception as e:
            print(f"Error processing message from {username}: {e}")

    async def close(self):
        print("Disconnecting from Twitch...")
        save_conversations()
        await super().close()


# Function to save conversations
def save_conversations():
    print("Saving conversations...")
    os.makedirs('./conversations/user_profiles/', exist_ok=True)

    # Iterate through chatters and save their conversations
    for username in chatters:
        filename = f"./conversations/user_profiles/conversation_{username}.json"

        if os.path.exists(filename):
            print(f"Found file for {username}: {filename}")
            # You can add further processing for existing files here
        else:
            print(f"No file found for {username}, creating one: {filename}")
            with open(filename, "w") as file:
                json.dump([], file)

    print("Conversations saved.")


# Function to append a message to the JSON file
def append_message(chat_entry):
    os.makedirs('./conversations/chat_logs/', exist_ok=True)
    file_path = './conversations/chat_logs/twitchchatconvervation_peepingotter.json'

    try:
        if not os.path.exists(file_path):
            # Create a new file with an empty list if it doesn't exist
            with open(file_path, "w") as file:
                json.dump([chat_entry], file, indent=2)
        else:
            # Load existing messages and append the new one
            with open(file_path, "r") as file:
                data = json.load(file)

            data.append(chat_entry)

            # If there are more than 80 entries, remove the earliest 40
            if len(data) > 80:
                data = data[40:]

            with open(file_path, "w") as file:
                json.dump(data, file, indent=2)
    except Exception as e:
        print(f"Error appending message: {e}")


# Function to handle bot logic (replace with your implementation)
async def ask_question(message, username):
    # Simulate a response from the bot
    if "hello" in message.lower():
        return "Hello! How can I assist you today?"
    if "nami" in message.lower():
        return "Hi, this is Nami! How can I help you?"
    return None


# Run the bot
bot = TwitchBot()
bot.run()
