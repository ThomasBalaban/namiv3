# Save as: nami/bot_core.py
import os
import yaml
import vertexai
import traceback
from vertexai.generative_models import GenerativeModel, HarmCategory, HarmBlockThreshold, Part, Content, FunctionDeclaration, Tool
from google.oauth2 import service_account
from nami.config import TUNED_MODEL_ID
# --- MODIFIED: Import both context getters ---
from nami.context import get_breadcrumbs_from_director, get_summary_from_director

BOTNAME = "peepingnami"

# --- (All code from here to generate_response is unchanged) ---
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
sound_effects_tool = Tool(function_declarations=[play_sound_effect_func])

class NamiBot:
    def __init__(self, config_path=None):
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

    def _handle_function_calls(self, response):
        if not response.candidates or not response.candidates[0].content.parts:
            return None
        function_calls = []
        text_parts = []
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'function_call') and part.function_call:
                func_call = part.function_call
                if func_call.name == "play_sound_effect":
                    effect_name = func_call.args.get("effect_name", "")
                    context = func_call.args.get("context", "")
                    print(f"🔊 Function call: play_sound_effect({effect_name})")
                    self._execute_sound_effect(effect_name, context)
                    function_calls.append({'name': func_call.name, 'args': dict(func_call.args)})
            elif hasattr(part, 'text') and part.text:
                text_parts.append(part.text)
        return {'text': ''.join(text_parts), 'function_calls': function_calls}

    def _execute_sound_effect(self, effect_name, context=""):
        try:
            from nami.tts_utils.sfx_player import play_sound_effect_threaded
            print(f"🎵 Playing sound effect: {effect_name}")
            if context: print(f"   Context: {context}")
            success = play_sound_effect_threaded(effect_name)
            if not success: print(f"❌ Failed to play sound effect '{effect_name}'")
        except Exception as e:
            print(f"❌ Error playing sound effect '{effect_name}': {e}")

    # --- THIS FUNCTION IS THE CORE CHANGE ---
    def generate_response(self, prompt):
        """
        Generates a response using both the summary and breadcrumbs from the Director.
        """
        if not prompt:
            return "I can't respond to an empty prompt, silly.", "No context provided."

        # --- NEW: Get BOTH summary and breadcrumbs ---
        summary = get_summary_from_director()
        breadcrumbs = get_breadcrumbs_from_director(count=3)
        
        breadcrumb_context = ""
        if breadcrumbs:
            breadcrumb_context = "[Interesting Events (most recent first)]\n"
            for bc in breadcrumbs:
                score_str = f"{bc.get('score', 0.0):.2f}"
                breadcrumb_context += f"- {bc['source']}: {bc['text']} (Score: {score_str})\n"
        
        # --- MODIFIED: Create the new, full context prompt ---
        full_prompt_with_context = (
            f"[Current Situation Summary]\n{summary}\n\n"
            f"{breadcrumb_context}\n"
            f"USER PROMPT: {prompt}"
        )

        history_for_ui = "No history yet."
        if self.history:
            history_lines = [
                f"{'User' if entry.role == 'user' else 'Nami'}: {entry.parts[0].text.strip()}"
                for entry in self.history
            ]
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

# --- (Global instance and wrapper are unchanged) ---
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