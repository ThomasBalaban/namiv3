import requests
import subprocess
import json
from conversation import load_twitch_chat_conversation, append_message_to_conversation 
from bot import BotConfig

# Create an instance of BotConfig
bot_config = BotConfig()

ACTIVE_CHANNEL = 'peepingotter'
BOTNAME = bot_config.config['name']  # Accessing the 'name' from the config dictionary
personality = bot_config.config['personality']  # Accessing the 'personality' from the config dictionary
creator_details = bot_config.config['creator_details']  # Accessing the 'creator_details' from the config dictionary
rules = bot_config.config['rules']  # Accessing the 'rules' from the config dictionary

# Load initial conversation history
history_array = load_twitch_chat_conversation(ACTIVE_CHANNEL)
system_message = {
    "role": "system",
    "content": f"{personality} {creator_details} {rules}",
}

# Combine the system message with the full chat history
conversation_history = [system_message] + history_array

import subprocess
import json

def ask_question(question, username="anonymous"):
    global conversation_history

    # Append user question to the conversation
    conversation_history.append({
        "role": "user",
        "content": f"{username}: {question}",
    })

    try:
        print("Conversation history:", conversation_history)

        # Trim conversation history if it grows too large
        if len(conversation_history) > 30:
            messages_to_keep = [
                message for message in conversation_history[1:]  # Exclude system message
                if "nami" in message["content"].lower() or message["role"] == "assistant"
            ]

            # Keep at most 7 relevant messages and 15 others
            messages_to_keep = messages_to_keep[:7]
            messages_to_remove = conversation_history[1:15 - len(messages_to_keep)]

            conversation_history = [system_message] + messages_to_keep + messages_to_remove
            print('Updated conversation history after trimming:', conversation_history)

        if "nami" not in question.lower():
            # Skip processing if trigger words are not present
            return None

        # Build the input payload for Ollama
        request_payload = {
            "model": bot_config.config["model"],  # Use model from config
            "messages": conversation_history,
            "stream": False,
            "max_tokens": bot_config.config["max_tokens"],  # Use max_tokens from config
            "temperature": bot_config.config["temperature"],  # Use temperature from config
            "top_k": bot_config.config["top_k"],  # Use top_k from config
            "top_p": bot_config.config["top_p"],  # Use top_p from config
            "repeat_penalty": bot_config.config["repeat_penalty"],  # Use repeat_penalty from config
            "repeat_last_n": bot_config.config["repeat_last_n"],  # Use repeat_last_n from config
            "num_predict": bot_config.config["num_predict"],  # Use num_predict from config
        }

        # Call the local Ollama server via subprocess
        # Make sure the local Ollama build is running and listening to the correct port
        result = subprocess.run(
            ['ollama', 'chat', '--model', bot_config.config["model"], '--json'],
            input=json.dumps(request_payload),  # Pass the request as JSON
            text=True,  # Handle input and output as text
            capture_output=True
        )
        print('---------------------')

        print(result)


        # Check for errors in the response
        if result.returncode != 0:
            print("Error calling Ollama:", result.stderr)
            return "Something went wrong with the Ollama model!"

        # Parse the response from Ollama
        response_data = json.loads(result.stdout)

        if "message" in response_data:
            bot_reply = response_data["message"]["content"]

            # Save the response to the history
            conversation_history.append({
                "role": "assistant",
                "content": bot_reply,
            })

            # Save the interaction for persistent storage
            append_message_to_conversation(username, question, bot_reply)

            return bot_reply
        else:
            print("Unexpected response structure:", response_data)
            return "I couldn't process that, sorry!"

    except Exception as error:
        print("Error processing the request:", error)
        return "Something went wrong, please try again later."


def start_conversation():
    print("Start chatting with the bot! Type 'exit' to quit.")
    while True:
        question = input("You: ")

        if question.lower() == "exit":
            print("Goodbye!")
            break

        if question.lower().startswith("set mood to "):
            new_mood = question[12:].strip()
            set_mood(new_mood)
            print(f"Mood updated to: {new_mood}")
            continue

        reply = ask_question(question)
        if reply:
            print(f"{BOTNAME}: {reply}")


if __name__ == "__main__":
    start_conversation()
