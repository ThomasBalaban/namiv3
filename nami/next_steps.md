# Nami's Migration Plan: From Local Gemma to Cloud-Powered Gemini

This guide provides a clear, step-by-step process to transition Nami's core logic from your local model to the Gemini API. We'll do this in three phases:

1.  **Phase 1: Immediate Swap (15-20 minutes)** - Get Nami running with the base Gemini model using your existing system prompt. This gives you an instant performance boost.
2.  **Phase 2: Data Prep & Fine-Tuning** - Convert your existing training data and launch a fine-tuning job to teach a new model Nami's unique, risqué personality.
3.  **Phase 3: The Real Nami** - Update the code to use your new, custom-tuned Nami model.

---

## Phase 1: Immediate Swap to the Base Gemini Model

This phase gets you up and running quickly. We'll modify `bot_core.py` to call the Gemini API instead of your local model.

### Step 1: Get Your API Key

1.  Go to [Google AI Studio](https://aistudio.google.com/).
2.  Sign in with your Google account.
3.  Click "**Get API key**" -> "**Create API key in new project**".
4.  Copy your new API key. **Keep this secret and safe!**

### Step 2: Set Up Your Environment

1.  **Install the Library:**
    ```bash
    pip install google-generativeai
    ```
    Add `google-generativeai` to your `requirements.txt` file.

2.  **Set the API Key:** For security, it's best to set your API key as an environment variable rather than putting it in your code.

    * **macOS/Linux:**
        ```bash
        export GEMINI_API_KEY='YOUR_API_KEY_HERE'
        ```
    * **Windows (Command Prompt):**
        ```bash
        set GEMINI_API_KEY=YOUR_API_KEY_HERE
        ```

### Step 3: Update `nami/bot_core.py`

Replace the entire contents of your existing `nami/bot_core.py` file with the code below. This new version does the following:
* Removes all the complex local model loading code (`AutoModelForCausalLM`, `AutoTokenizer`).
* Loads your existing `system_prompt` from `model_in_progress.yaml`.
* Uses the `google-generativeai` library to call the `gemini-1.5-flash` model, which is perfect for speed and cost-effectiveness.
* Includes safety settings to give Nami more freedom, which is crucial for her character.

```python
# This is the new content for nami/bot_core.py
import os
import yaml
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

class NamiBot:
    def __init__(self, config_path='nami/model_in_progress.yaml'):
        """
        Initializes the NamiBot, configuring it to use the Gemini API.
        """
        print("Initializing NamiBot with Gemini API...")
        self.config_path = config_path
        self.system_prompt = self._load_system_prompt()

        try:
            # Configure the Gemini API key from environment variables
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY environment variable not set.")
            genai.configure(api_key=api_key)
            print("Gemini API configured successfully.")
        except Exception as e:
            print(f"Error configuring Gemini API: {e}")
            # In a real app, you might want to exit or use a fallback mechanism
            raise

        # Define safety settings to allow for Nami's edgy personality.
        # This blocks only the most severe content, giving more leeway for adult humor.
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        }
        
        # --- IMPORTANT ---
        # In Phase 1, use 'gemini-1.5-flash-latest'.
        # In Phase 3, you will replace this with your tuned model's ID.
        # -----------------
        model_to_use = 'gemini-1.5-flash-latest' 
        
        self.model = genai.GenerativeModel(
            model_name=model_to_use,
            system_instruction=self.system_prompt,
            safety_settings=self.safety_settings
        )
        
        # Start a chat session to maintain conversation history naturally
        self.chat = self.model.start_chat(history=[])
        print(f"NamiBot initialization complete. Using model: {model_to_use}")


    def _load_system_prompt(self):
        """
        Loads the system prompt from the YAML configuration file.
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                print(f"Loaded system prompt from {self.config_path}")
                return config.get('system_prompt', '')
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

        print(f"\n--- Sending Prompt to Gemini --- \n{prompt}\n---------------------------------")
        
        try:
            # Send the user's prompt to the ongoing chat session
            response = self.chat.send_message(prompt)
            nami_response = response.text
            print(f"\n--- Received Nami's Response ---\n{nami_response}\n----------------------------------")
            return nami_response
        except Exception as e:
            print(f"An error occurred while generating response: {e}")
            return "Ugh, my circuits are sizzling. Give me a second and try that again."

# Example of how to use the bot (for direct testing of this file)
if __name__ == '__main__':
    if not os.getenv("GEMINI_API_KEY"):
        print("\n" + "="*50)
        print("FATAL ERROR: Please set the GEMINI_API_KEY environment variable before running.")
        print("On macOS/Linux: export GEMINI_API_KEY='your_key_here'")
        print("On Windows:     set GEMINI_API_KEY=your_key_here")
        print("="*50 + "\n")
    else:
        print("Starting NamiBot test...")
        nami = NamiBot()
        test_prompt = "Hey Nami, what do you think of my new haircut?"
        response = nami.generate_response(test_prompt)
        print(f"\nTest Prompt: {test_prompt}")
        print(f"Nami's Test Response: {response}")