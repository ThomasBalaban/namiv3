# conversation

import os
import json

BOT_CONFIG = {
    "name": "BOTNAME",
    "personality": "This bot is witty and helpful.",
    "creatorDetails": "Created by Timos.",
    "rules": "Please be respectful and adhere to Twitch guidelines."
}

# Construct the system message
system_message = {
    "role": "system",
    "content": f"{BOT_CONFIG['personality']} {BOT_CONFIG['creatorDetails']} {BOT_CONFIG['rules']}",
}

history_array = [system_message]  # Start with the system message


def load_twitch_chat_conversation(username_of_streamer):
    file_path = f"./conversations/chat_logs/twitchchatconvervation_{username_of_streamer}.json"

    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                conversation_data = json.load(file)

            if isinstance(conversation_data, list):
                if len(conversation_data) > 40:
                    conversation_data = conversation_data[-20:]  # Keep the last 20 entries
                    with open(file_path, "w", encoding="utf-8") as file:
                        json.dump(conversation_data, file, indent=2)

                return conversation_data  # Return the conversation data
            else:
                return []  # Return an empty list if the structure is unexpected
        except Exception as e:
            print(f"Error reading or parsing the Twitch chat file: {e}")
            raise Exception(f"Failed to load Twitch chat conversation: {str(e)}")
    else:
        print("No Twitch chat history found, initializing new conversation file.")
        save_conversation("twitchChat", False, [])
        return []


def load_conversation(username):
    file_path = f"./conversations/conversation_{username}.json"

    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                conversation_data = json.load(file)

            if isinstance(conversation_data.get("conversation", []), list):
                return conversation_data["conversation"]  # Return the conversation array
            else:
                return []  # Return an empty list if the structure is unexpected
        except Exception as e:
            print(f"Error reading or parsing the file: {e}")
            raise Exception(f"Failed to load conversation: {str(e)}")
    else:
        save_conversation(username, False, history_array)
        print(f"No conversation history found for user: {username}")
        return []


def append_message_to_conversation(username, question, bot_reply):
    filename = f"./conversations/user_profiles/conversation_{username}.json"
    file_path = filename

    if not os.path.exists(file_path):
        print(f"Error: The conversation file for {username} does not exist.")
        save_conversation(username, False, history_array)

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            conversation_data = json.load(file)

        # Append the new messages
        conversation_data["conversation"].extend([
            {"role": "user", "content": question},
            {"role": "assistant", "content": bot_reply}
        ])

        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(conversation_data, file, indent=2)

        print(f"New message appended to {username}'s conversation.")
    except Exception as e:
        print(f"Error appending the message: {e}")


def save_conversation(username, underage=False, history_array=None):
    if history_array is None:
        history_array = []

    print("Reached save conversation function")
    filename = f"conversation_{username}.json"

    conversation_data = {
        "username": username,
        "underage": underage,
        "conversation": []
    }

    # Add only user and assistant messages (skip system message)
    for item in history_array:
        if item.get("role") != "system":
            conversation_data["conversation"].append(item)

    # Ensure the directory exists
    dir_path = "./conversations/user_profiles/"
    os.makedirs(dir_path, exist_ok=True)

    file_path = os.path.join(dir_path, filename)
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(conversation_data, file, indent=2)

    print(f"Conversation saved to {file_path}")
