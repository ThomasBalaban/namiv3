import os
import yaml
import vertexai
import traceback
from vertexai.generative_models import GenerativeModel, HarmCategory, HarmBlockThreshold, Part, Content
from google.oauth2 import service_account
from nami.config import TUNED_MODEL_ID
from nami.context import get_formatted_context

BOTNAME = "peepingnami"

class NamiBot:
    def __init__(self, config_path='model.yaml'):
        """
        Initializes the NamiBot using a service account key for authentication.
        """
        print("Initializing NamiBot with Vertex AI...")
        
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
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        }
        
        print(f"Creating model with ID: {TUNED_MODEL_ID}")
        self.model = GenerativeModel(
            model_name=TUNED_MODEL_ID,
            safety_settings=self.safety_settings
        )
        
        # This will store our conversation history manually
        self.history = []
        self.max_history_length = 20 # 10 pairs of user/model messages
        
        print(f"NamiBot initialization complete. Using model: {TUNED_MODEL_ID}")

    def generate_response(self, prompt):
        """
        Generates a response using a stateless generate_content call,
        including dynamic context and conversation history.
        """
        if not prompt:
            return "I can't respond to an empty prompt, silly."

        # --- RE-ADD: Get the latest dynamic context ---
        dynamic_context = get_formatted_context()
        # Prepend the context to the user's prompt for this turn only.
        full_prompt_with_context = f"{dynamic_context}\n\nUSER PROMPT: {prompt}"
        
        print(f"\n--- Sending Prompt to Gemini --- \n{full_prompt_with_context}\n---------------------------------")
        
        try:
            # --- RE-ADD: Build the request with history ---
            # The history and the new contextual prompt are combined into a single list.
            contents_for_api = self.history + [
                Content(role="user", parts=[Part.from_text(full_prompt_with_context)])
            ]
            
            # Use the stateless `generate_content` method
            response = self.model.generate_content(contents_for_api)
            nami_response = response.text

            # --- RE-ADD: Manually update our history list ---
            # Add the user's ORIGINAL prompt (without context)
            self.history.append(Content(role="user", parts=[Part.from_text(prompt)]))
            # Add the model's response
            self.history.append(Content(role="model", parts=[Part.from_text(nami_response)]))

            # Trim the history if it gets too long
            if len(self.history) > self.max_history_length:
                self.history = self.history[-self.max_history_length:]

            print(f"\n--- Received Nami's Response ---\n{nami_response}\n----------------------------------")
            return nami_response
        except Exception as e:
            print("\n" + "="*20 + " API ERROR " + "="*20)
            print(f"An error occurred while generating response. Full error details:")
            traceback.print_exc()
            print("="*51 + "\n")
            return "Ugh, my circuits are sizzling. Give me a second and try that again."

# Create a global instance
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