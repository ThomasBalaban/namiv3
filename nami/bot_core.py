import os
import yaml
import vertexai
from vertexai.generative_models import GenerativeModel, HarmCategory, HarmBlockThreshold
# --- MODIFIED: Removed service account imports ---
from nami.config import TUNED_MODEL_ID
from nami.context import get_formatted_context

BOTNAME = "peepingnami"

class NamiBot:
    def __init__(self, config_path='model.yaml'):
        """
        Initializes the NamiBot, configuring it to use the Vertex AI Gemini API
        with Application Default Credentials.
        """
        print("Initializing NamiBot with Vertex AI...")
        
        try:
            parts = TUNED_MODEL_ID.split('/')
            project_id = parts[1]
            location = parts[3]
        except IndexError:
            raise ValueError("TUNED_MODEL_ID in config.py is not in the expected format.")

        # --- MODIFIED: Use Application Default Credentials automatically ---
        vertexai.init(project=project_id, location=location)
        print("Vertex AI initialized successfully (using Application Default Credentials).")

        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = os.path.join(base_dir, config_path)
        
        self.system_prompt = self._load_system_prompt()
        self.history = []
        self.max_history_length = 20

        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        }
        
        # --- Use the full TUNED_MODEL_ID directly ---
        self.model = GenerativeModel(
            model_name=TUNED_MODEL_ID,
            system_instruction=[self.system_prompt],
            safety_settings=self.safety_settings
        )
        
        self.chat = self.model.start_chat(history=[])
        
        print(f"NamiBot initialization complete. Using model: {TUNED_MODEL_ID}")

    def _load_system_prompt(self):
        """
        Loads the system prompt from the YAML configuration file.
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                prompt_text = f.read()
                if prompt_text.startswith('SYSTEM """'):
                    prompt_text = prompt_text[len('SYSTEM """'):].strip()
                if prompt_text.endswith('"""'):
                    prompt_text = prompt_text[:-3].strip()
                print(f"Loaded system prompt from {self.config_path}")
                return prompt_text
        except FileNotFoundError:
            print(f"Error: Config file not found at {self.config_path}")
            return "You are Nami, a helpful assistant."
        except Exception as e:
            print(f"Error loading system prompt: {e}")
            return ""

    def generate_response(self, prompt):
        """
        Generates a response from the Vertex AI API using the provided prompt and context.
        """
        if not prompt:
            return "I can't respond to an empty prompt, silly."

        dynamic_context = get_formatted_context()
        full_prompt = f"{dynamic_context}\n{prompt}"
        
        print(f"\n--- Sending Prompt to Gemini --- \n{full_prompt}\n---------------------------------")
        
        try:
            response = self.chat.send_message(full_prompt)
            nami_response = response.text

            print(f"\n--- Received Nami's Response ---\n{nami_response}\n----------------------------------")
            return nami_response
        except Exception as e:
            print(f"An error occurred while generating response: {e}")
            return "Ugh, my circuits are sizzling. Give me a second and try that again."

# --- Create a global instance for the rest of the application ---
# --- MODIFIED: Removed GCP_CREDS_PATH check ---
if not TUNED_MODEL_ID:
    print("\n" + "="*50)
    print("FATAL ERROR: Please set TUNED_MODEL_ID in your config.py")
    print("="*50 + "\n")
    nami_bot_instance = None
else:
    nami_bot_instance = NamiBot()

def ask_question(question):
    """Wrapper function to call the bot's generate_response method."""
    if nami_bot_instance:
        return nami_bot_instance.generate_response(question)
    else:
        return "NamiBot is not initialized. Please check your config."