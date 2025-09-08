# Phase 2: Fine-Tuning for Nami's True Personality

Now we teach a new model Nami's specific voice, humor, and adult nature using your excellent training data.

## Step 1: Prepare Your Training Data

The Gemini API needs the training data in a simple `JSONL` format with `text` fields. We need to convert your `training/nami_training_data.jsonl` file.

### 1. Create a new Python script

Create a new Python script named `prepare_gemini_data.py` in your `training` folder.

### 2. Paste the code below

Copy and paste this code into the `prepare_gemini_data.py` file:

```python
# save this as training/prepare_gemini_data.py
import json
import os

def convert_to_gemini_format(input_file, output_file):
    """
    Converts Nami's training data to the format required for Gemini fine-tuning.
    The format is a JSONL file where each line is a dictionary with a "text" key.
    The value is a string like: "input: <user_prompt> output: <nami_response>"
    """
    print(f"Starting conversion of {input_file}...")
    converted_count = 0
    
    with open(input_file, 'r') as infile, open(output_file, 'w') as outfile:
        for line in infile:
            try:
                data = json.loads(line)
                messages = data.get('messages', [])
                
                if len(messages) >= 2:
                    user_message = ""
                    assistant_message = ""
                    
                    for msg in messages:
                        if msg['role'] == 'user':
                            user_message = msg['content']
                        elif msg['role'] == 'assistant':
                            assistant_message = msg['content']
                    
                    if user_message and assistant_message:
                        user_prompt_formatted = json.dumps(user_message)
                        nami_response_formatted = json.dumps(assistant_message)
                        
                        formatted_string = f"input: {user_prompt_formatted} output: {nami_response_formatted}"
                        
                        json.dump({"text": formatted_string}, outfile)
                        outfile.write('\n')
                        converted_count += 1
                        
            except json.JSONDecodeError:
                print(f"Skipping malformed line: {line.strip()}")
            except KeyError:
                print(f"Skipping line with missing keys: {line.strip()}")
                
    print(f"Conversion complete. Converted {converted_count} examples.")
    print(f"Output file created at: {output_file}")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(base_dir, 'nami_training_data.jsonl')
    output_path = os.path.join(base_dir, 'gemini_training_data.jsonl')
    
    if not os.path.exists(input_path):
        print(f"ERROR: Input file not found at {input_path}")
    else:
        convert_to_gemini_format(input_path, output_path)
```

### 3. Run the script

```bash
python training/prepare_gemini_data.py
```

You will now have a `gemini_training_data.jsonl` file ready for upload.

## Step 2: Launch the Fine-Tuning Job

1. Go back to **Google AI Studio**
2. On the left menu, click "**Tuned models**"
3. Click "**Create tuned model**"
4. Give your model a name (e.g., `nami-v1-tuned`)
5. For the "Base model", select `Gemini 1.5 Flash`
6. For the "Training data", upload your newly created `gemini_training_data.jsonl` file
7. Click "**Tune**"

The tuning process will take some time (from 30 minutes to a few hours depending on file size) and will have a small cost associated with it. You can leave the page and it will notify you when it's complete.