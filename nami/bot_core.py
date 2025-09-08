import os
import yaml
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from nami.config import GEMINI_API_KEY
# --- MODIFIED: Import the new context getter ---
from nami.context import get_formatted_context

BOTNAME = "peepingnami"

class NamiBot:
    def __init__(self, config_path='model.yaml'):
        """
        Initializes the NamiBot, configuring it to use the Gemini API.
        """
        print("Initializing NamiBot with Gemini API...")
        self.config_path = config_path
        self.system_prompt = self._load_system_prompt()
        self.history = []
        self.max_history_length = 20 # Keep last 10 user/assistant message pairs

        try:
            # Configure the Gemini API key from config.py
            if not GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY not found or is empty in config.py.")
            genai.configure(api_key=GEMINI_API_KEY)
            print("Gemini API configured successfully.")
        except Exception as e:
            print(f"Error configuring Gemini API: {e}")
            raise

        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        }
        
        model_to_use = 'gemini-1.5-flash-latest' 
        
        self.model = genai.GenerativeModel(
            model_name=model_to_use,
            # The static system prompt is now the base personality
            system_instruction=self.system_prompt,
            safety_settings=self.safety_settings
        )
        
        print(f"NamiBot initialization complete. Using model: {model_to_use}")

    def _load_system_prompt(self):
        """
        Loads the system prompt from the YAML configuration file.
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                # The YAML file is not standard, so we read the whole file as a string
                prompt_text = f.read()
                # Remove the 'SYSTEM """' and trailing '"""' if they exist
                if prompt_text.startswith('SYSTEM """'):
                    prompt_text = prompt_text[len('SYSTEM """'):].strip()
                if prompt_text.endswith('"""'):
                    prompt_text = prompt_text[:-3].strip()
                print(f"Loaded system prompt from {self.config_path}")
                return prompt_text
        except FileNotFoundError:
            print(f"Error: Config file not found at {self.config_path}")
            return "You are Nami, a helpful assistant." # A generic fallback
        except Exception as e:
            print(f"Error loading system prompt: {e}")
            return ""

    def generate_response(self, prompt):
        """
        Generates a response from the Gemini API using the provided prompt and maintaining context.
        """
        if not prompt:
            return "I can't respond to an empty prompt, silly."

        # Get the latest dynamic context
        dynamic_context = get_formatted_context()
        
        # Construct the full prompt for this turn
        full_prompt = f"{dynamic_context}\n{prompt}"
        
        print(f"\n--- Sending Prompt to Gemini --- \n{full_prompt}\n---------------------------------")
        
        try:
            # We create a new chat session on each turn to inject the dynamic context.
            # The model's `system_instruction` provides the base personality,
            # and the history provides conversation memory.
            chat = self.model.start_chat(history=self.history)
            response = chat.send_message(full_prompt)
            nami_response = response.text
            
            # Update history
            self.history.append({'role': 'user', 'parts': [prompt]})
            self.history.append({'role': 'model', 'parts': [nami_response]})

            # Trim history to prevent it from growing too large
            if len(self.history) > self.max_history_length:
                self.history = self.history[-self.max_history_length:]

            print(f"\n--- Received Nami's Response ---\n{nami_response}\n----------------------------------")
            return nami_response
        except Exception as e:
            print(f"An error occurred while generating response: {e}")
            return "Ugh, my circuits are sizzling. Give me a second and try that again."

# --- Create a global instance for the rest of the application ---
if not GEMINI_API_KEY:
    print("\n" + "="*50)
    print("FATAL ERROR: Please set the GEMINI_API_KEY in your config.py file before running.")
    print("="*50 + "\n")
    nami_bot_instance = None
else:
    nami_bot_instance = NamiBot()

def ask_question(question):
    """Wrapper function to call the bot's generate_response method."""
    if nami_bot_instance:
        return nami_bot_instance.generate_response(question)
    else:
        return "NamiBot is not initialized. Please check your API key."