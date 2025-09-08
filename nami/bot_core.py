import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import re
import time
from threading import Lock
from nami.hard_filter import banned_words

# LoRA Configuration
BASE_MODEL_NAME = "huihui-ai/gemma-3-27b-it-abliterated"
LORA_ADAPTER_PATH = "../training//nami-lora-adapters"  # Path to your trained LoRA
BOTNAME = "peepingnami"

# Context settings
CONTEXT_TIME_WINDOW_SECONDS = 30
latest_vision_context = []
latest_spoken_word_context = []
latest_audio_context = []
latest_twitch_chat_context = []
MAX_TWITCH_CONTEXT_LENGTH = 20

# Global state for conversation
conversation_history = []
MAX_CONVERSATION_LENGTH = 30

context_lock = Lock()

# LoRA Model - loaded once at startup
model = None
tokenizer = None

def load_lora_model():
    """Load the base model with LoRA adapters"""
    global model, tokenizer
    
    print("Loading base model...")
    # Load base model
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_NAME,
        torch_dtype=torch.float16,
        device_map="auto",
        low_cpu_mem_usage=True,
        trust_remote_code=True,
    )
    
    print("Loading LoRA adapters...")
    # Load LoRA adapters
    model = PeftModel.from_pretrained(base_model, LORA_ADAPTER_PATH)
    
    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_NAME, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    
    print("LoRA model loaded successfully!")

def update_twitch_chat_context(username: str, message: str):
    """Thread-safely updates the latest Twitch chat context."""
    global latest_twitch_chat_context
    with context_lock:
        formatted_message = f"{username}: {message}"
        latest_twitch_chat_context.append(formatted_message)
        while len(latest_twitch_chat_context) > MAX_TWITCH_CONTEXT_LENGTH:
            latest_twitch_chat_context.pop(0)

def update_vision_context(text: str):
    """Thread-safely updates vision context, keeping entries within the time window."""
    global latest_vision_context
    with context_lock:
        now = time.time()
        latest_vision_context.append((now, text))
        latest_vision_context = [(ts, txt) for ts, txt in latest_vision_context if now - ts <= CONTEXT_TIME_WINDOW_SECONDS]

def update_spoken_word_context(text: str):
    """Thread-safely updates spoken word context, keeping entries within the time window."""
    global latest_spoken_word_context
    with context_lock:
        now = time.time()
        latest_spoken_word_context.append((now, text))
        latest_spoken_word_context = [(ts, txt) for ts, txt in latest_spoken_word_context if now - ts <= CONTEXT_TIME_WINDOW_SECONDS]

def update_audio_context(text: str):
    """Thread-safely updates audio context, keeping entries within the time window."""
    global latest_audio_context
    with context_lock:
        now = time.time()
        latest_audio_context.append((now, text))
        latest_audio_context = [(ts, txt) for ts, txt in latest_audio_context if now - ts <= CONTEXT_TIME_WINDOW_SECONDS]

def censor_text(text):
    """Replace banned words with "*filtered*" """
    pattern = re.compile("|".join(re.escape(word) for word in banned_words), flags=re.IGNORECASE)
    return pattern.sub("*filtered*", text)

def add_message(role, content):
    """Add a message to the conversation history, maintaining max length"""
    global conversation_history
    conversation_history.append({"role": role, "content": content})
    while len(conversation_history) > MAX_CONVERSATION_LENGTH:
        conversation_history.pop(0)

def format_conversation_for_gemma(messages_with_context):
    """Convert conversation to Gemma chat format"""
    formatted_conversation = ""
    
    for message in messages_with_context:
        role = message["role"]
        content = message["content"]
        
        if role == "system":
            # System messages can be added as user messages in Gemma
            formatted_conversation += f"<start_of_turn>user\n{content}\n<end_of_turn>\n"
        elif role == "user":
            formatted_conversation += f"<start_of_turn>user\n{content}\n<end_of_turn>\n"
        elif role == "assistant":
            formatted_conversation += f"<start_of_turn>model\n{content}\n<end_of_turn>\n"
    
    # Add the start of the model's response
    formatted_conversation += "<start_of_turn>model\n"
    
    return formatted_conversation

def generate_response(prompt, max_new_tokens=500, temperature=0.7, top_p=0.9):
    """Generate response using the LoRA model"""
    global model, tokenizer
    
    if model is None or tokenizer is None:
        raise Exception("Model not loaded. Call load_lora_model() first.")
    
    # Tokenize input
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=2048)
    
    # Move to same device as model
    inputs = {k: v.to(model.device) for k, v in inputs.items()}
    
    # Generate response
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    
    # Decode only the new tokens
    response = tokenizer.decode(outputs[0][inputs['input_ids'].shape[1]:], skip_special_tokens=True)
    
    # Clean up the response
    response = response.strip()
    if response.endswith("<end_of_turn>"):
        response = response[:-12].strip()
    
    return response

def ask_question(question):
    """Send a question to the LoRA model and return the bot's response."""
    global conversation_history, latest_vision_context, latest_spoken_word_context, latest_audio_context, latest_twitch_chat_context

    add_message("user", question)

    try:
        with context_lock:
            vision_summary = "You haven't seen anything recently."
            if latest_vision_context:
                vision_texts = [text for timestamp, text in latest_vision_context]
                vision_summary = "\n".join(vision_texts)

            spoken_word_summary = "You haven't heard anyone speak recently."
            if latest_spoken_word_context:
                spoken_word_texts = [text for timestamp, text in latest_spoken_word_context]
                spoken_word_summary = "\n".join(spoken_word_texts)

            audio_summary = "You haven't heard anything recently."
            if latest_audio_context:
                audio_texts = [text for timestamp, text in latest_audio_context]
                audio_summary = "\n".join(audio_texts)
            
            twitch_chat_summary = "Nothing new in chat."
            if latest_twitch_chat_context:
                twitch_chat_summary = "\n".join(latest_twitch_chat_context)

            context_prompt = (
                f"SYSTEM: This is your internal monologue. Use it to inform your answer based on recent events.\n"
                f"--- What you've recently seen (last {CONTEXT_TIME_WINDOW_SECONDS}s) ---\n{vision_summary}\n\n"
                f"--- What you've recently heard spoken (last {CONTEXT_TIME_WINDOW_SECONDS}s) ---\n{spoken_word_summary}\n\n"
                f"--- What you've recently heard (last {CONTEXT_TIME_WINDOW_SECONDS}s) ---\n{audio_summary}\n\n"
                f"--- Recent messages in Twitch chat ---\n{twitch_chat_summary}\n"
                f"--- END OF CONTEXT ---\n"
                f"Now, respond to the user as peepingnami."
            )
        
        messages_with_context = [{"role": "system", "content": context_prompt}] + conversation_history

        # Format for Gemma
        formatted_prompt = format_conversation_for_gemma(messages_with_context)
        
        # Generate response
        print("PeepingNami: ", end="", flush=True)
        bot_reply = generate_response(formatted_prompt)
        bot_reply = censor_text(bot_reply)
        
        print(bot_reply)

        add_message("assistant", bot_reply)
        return bot_reply

    except Exception as error:
        print(f"An error occurred: {error}")
        return None

# Initialize the model when the module is imported
if __name__ == "__main__":
    # For testing
    load_lora_model()
    
    while True:
        user_input = input("You: ")
        if user_input.lower() in ['quit', 'exit']:
            break
        response = ask_question(user_input)