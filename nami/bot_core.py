# Save as: nami/bot_core.py
import os
import yaml
import vertexai
import traceback
from vertexai.generative_models import GenerativeModel, HarmCategory, HarmBlockThreshold, Part, Content, FunctionDeclaration, Tool
from google.oauth2 import service_account
from nami.config import TUNED_MODEL_ID
from nami.context import get_breadcrumbs_from_director

BOTNAME = "peepingnami"

# Define sound effect function
play_sound_effect_func = FunctionDeclaration(
    name="play_sound_effect",
    description="Play a sound effect during speech. Use this when the user asks you to play a sound or when you want to emphasize something with a sound effect.",
    parameters={
        "type": "object",
        "properties": {
            "effect_name": {
                "type": "string",
                "enum": ["airhorn", "bonk", "fart"],
                "description": "The name of the sound effect to play"
            },
            "context": {
                "type": "string",
                "description": "Why you're playing this sound effect (optional)"
            }
        },
        "required": ["effect_name"]
    }
)

# Create the tool
sound_effects_tool = Tool(function_declarations=[play_sound_effect_func])

class NamiBot:
    def __init__(self, config_path=None):
        """
        Initializes the NamiBot using a service account key for authentication.
        """
        print("Initializing NamiBot with Vertex AI...")
        
        if config_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.config_path = os.path.join(base_dir, 'model_in_progress.yaml')
        else:
            self.config_path = config_path

        self.system_prompt = self._load_system_prompt()

        try:
            parts = TUNED_MODEL_ID.split('/')
            project_id = parts[1]
            location = parts[3]
            print(f"Parsed project: {project_id}, location: {location}")
        except IndexError:
            raise ValueError("TUNED_MODEL_ID in config.py is not in the expected format.")

        creds_path = os.path.join(os.path.dirname(__file__), 'gcp_creds.json')
        try:
            credentials = service_account.Credentials.from_service_account_file(creds_path)
            print("Successfully loaded credentials from service account file.")
        except Exception as e:
            print(f"FATAL ERROR: Could not load credentials from {creds_path}. {e}")
            raise

        vertexai.init(project=project_id, location=location, credentials=credentials)
        print("Vertex AI initialized successfully.")

        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }

        print(f"Creating model with ID: {TUNED_MODEL_ID}")
        self.model = GenerativeModel(
            model_name=TUNED_MODEL_ID,
            system_instruction=self.system_prompt,
            safety_settings=self.safety_settings
        )

        self.history = []
        self.max_history_length = 20

        print(f"NamiBot initialization complete. Using model: {TUNED_MODEL_ID}")

    def _load_system_prompt(self):
        """
        Loads the system prompt from the YAML configuration file.
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                prompt = config.get('SYSTEM', '')
                if not prompt:
                     prompt = config
                print(f"Loaded system prompt from {self.config_path}")
                return prompt
        except FileNotFoundError:
            print(f"Error: Config file not found at {self.config_path}")
            return "You are Nami, a helpful assistant."
        except Exception as e:
            print(f"Error loading system prompt: {e}")
            return ""

    def generate_response(self, prompt):
        """
        Generates a response. 
        Now vastly simplified because prompt construction is handled by Director.
        """
        if not prompt:
            return "I can't respond to an empty prompt, silly.", "No context provided."

        # --- FETCH CONSTRUCTED PROMPT FROM DIRECTOR ---
        director_data = get_breadcrumbs_from_director(count=3)
        
        # Check if we got the new format (Prompt Constructor)
        if isinstance(director_data, dict) and "formatted_context" in director_data:
            context_block = director_data["formatted_context"]
        else:
            # Fallback if Director isn't updated yet
            context_block = "[Director Connection Issues - Relying on base personality]"

        full_prompt = f"{context_block}\n\nUSER INPUT: {prompt}"

        # History formatting for UI debug
        history_lines = []
        for entry in self.history:
            role = "User" if entry.role == "user" else "Nami"
            text = entry.parts[0].text.strip()
            history_lines.append(f"{role}: {text}")
        history_for_ui = "\n".join(history_lines)

        full_context_for_ui = (
            f"--- CONVERSATION HISTORY ---\n{history_for_ui}\n\n"
            f"--- CURRENT CONTEXT & PROMPT ---\n{full_prompt}"
        )

        print(f"\n--- Sending Prompt to Gemini --- \n{full_prompt}\n---------------------------------")

        try:
            contents_for_api = self.history + [
                Content(role="user", parts=[Part.from_text(full_prompt)])
            ]

            response = self.model.generate_content(contents_for_api)
            nami_response = response.text

            self.history.append(Content(role="user", parts=[Part.from_text(prompt)]))
            self.history.append(Content(role="model", parts=[Part.from_text(nami_response)]))

            if len(self.history) > self.max_history_length:
                self.history = self.history[-self.max_history_length:]

            print(f"\n--- Received Nami's Response ---\n{nami_response}\n----------------------------------")
            return nami_response, full_context_for_ui
        except Exception as e:
            print("\n" + "="*20 + " API ERROR " + "="*20)
            print(f"An error occurred while generating response. Full error details:")
            traceback.print_exc()
            print("="*51 + "\n")
            return "Ugh, my circuits are sizzling. Give me a second and try that again.", full_context_for_ui

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