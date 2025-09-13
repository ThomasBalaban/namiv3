import os
import yaml
import vertexai
import traceback
from vertexai.generative_models import GenerativeModel, HarmCategory, HarmBlockThreshold, Part, Content, Tool, FunctionDeclaration, FunctionCall
from google.oauth2 import service_account
from nami.config import TUNED_MODEL_ID
from nami.context import get_formatted_context
from nami.tts_utils.sfx_player import play_sound_effect_threaded, get_available_sound_effects

BOTNAME = "peepingnami"

class NamiBot:
    def __init__(self, config_path='model_in_progress.yaml'):
        """
        Initializes the NamiBot using a service account key for authentication.
        """
        print("Initializing NamiBot with Vertex AI...")
        self.config_path = config_path

        # FIX: Load the system prompt BEFORE using it
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

        # FIX: Set safety settings to BLOCK_NONE to be less restrictive
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
        
        # --- NEW: Define the tool schema manually with FunctionDeclaration ---
        play_sfx_func = FunctionDeclaration(
            name="play_sound_effect",
            description="Plays a sound effect for the stream. Use this function when Nami wants to add an audio cue to her response, for example, to punctuate a joke or react to something.",
            parameters={
                "type": "object",
                "properties": {
                    "sfx_name": {
                        "type": "string",
                        "enum": get_available_sound_effects(),
                        "description": "The name of the sound effect to play."
                    }
                },
                "required": ["sfx_name"],
            },
        )
        # Create the tool instance from the function declaration
        play_sfx_tool = Tool(function_declarations=[play_sfx_func])

        print(f"Creating model with ID: {TUNED_MODEL_ID} and tool use enabled.")
        self.model = GenerativeModel(
            model_name=TUNED_MODEL_ID,
            system_instruction=self.system_prompt,
            safety_settings=self.safety_settings,
            tools=[play_sfx_tool] # Pass the tool to the model
        )

        # This will store our conversation history manually
        self.history = []
        self.max_history_length = 20  # 10 pairs of user/model messages

        print(f"NamiBot initialization complete. Using model: {TUNED_MODEL_ID}")

    # ADDED: This method was missing
    def _load_system_prompt(self):
        """
        Loads the system prompt from the YAML configuration file.
        """
        try:
            config_file_path = os.path.join(os.path.dirname(__file__), self.config_path)
            with open(config_file_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                prompt = config.get('SYSTEM', '')
                if not prompt:
                     # Fallback for the other yaml file format
                     prompt = config
                print(f"Loaded system prompt from {self.config_path}")
                return prompt
        except FileNotFoundError:
            print(f"Error: Config file not found at {config_file_path}")
            return "You are Nami, a helpful assistant."
        except Exception as e:
            print(f"Error loading system prompt: {e}")
            return ""

    def generate_response(self, prompt):
        """
        Generates a response using a stateless generate_content call,
        including dynamic context and conversation history.
        """
        if not prompt:
            return "I can't respond to an empty prompt, silly."

        dynamic_context = get_formatted_context()
        full_prompt_with_context = f"{dynamic_context}\n\nUSER PROMPT: {prompt}"

        # --- FIX: Prepare history for UI display ---
        history_for_ui = "No history yet."
        if self.history:
            history_lines = []
            for entry in self.history:
                role = "User" if entry.role == "user" else "Nami"
                text = entry.parts[0].text.strip()
                history_lines.append(f"{role}: {text}")
            history_for_ui = "\n".join(history_lines)

        full_context_for_ui = (
            f"--- CONVERSATION HISTORY ---\n{history_for_ui}\n\n"
            f"--- CURRENT CONTEXT & PROMPT ---\n{full_prompt_with_context}"
        )

        print(f"\n--- Sending Prompt to Gemini --- \n{full_prompt_with_context}\n---------------------------------")

        try:
            contents_for_api = self.history + [
                Content(role="user", parts=[Part.from_text(full_prompt_with_context)])
            ]

            response = self.model.generate_content(contents_for_api)

            # --- MODIFIED: Handle both text and function call responses ---
            nami_response_text = ""
            tool_call_part = None

            for part in response.parts:
                if part.text:
                    nami_response_text += part.text
                elif isinstance(part, FunctionCall):
                    tool_call_part = part

            # If a tool call was made, extract the function name and arguments
            if tool_call_part:
                tool_name = tool_call_part.name
                tool_args = tool_call_part.args

                # Return a special object that contains the text and the tool call.
                print(f"Tool call detected: {tool_name}({tool_args})")
                return nami_response_text, full_context_for_ui, {"tool": tool_name, "args": tool_args}

            # If there's no text response either, return a generic message
            if not nami_response_text:
                nami_response_text = "Hmm, I'm not sure what to say to that."

            # No tool call, just return the text response
            self.history.append(Content(role="user", parts=[Part.from_text(prompt)]))
            self.history.append(Content(role="model", parts=[Part.from_text(nami_response_text)]))

            if len(self.history) > self.max_history_length:
                self.history = self.history[-self.max_history_length:]

            print(f"\n--- Received Nami's Response ---\n{nami_response_text}\n----------------------------------")
            return nami_response_text, full_context_for_ui, None

        except Exception as e:
            print("\n" + "="*20 + " API ERROR " + "="*20)
            print(f"An error occurred while generating response. Full error details:")
            traceback.print_exc()
            print("="*51 + "\n")
            # --- FIX: Return the UI context even on error ---
            return "Ugh, my circuits are sizzling. Give me a second and try that again.", full_context_for_ui, None


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