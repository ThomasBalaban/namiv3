# save this as training/prepare_gemini_data.py
import json
import os

def convert_to_vertex_format(input_file, output_file):
    """
    Converts Nami's training data to the specific JSONL format required by
    Vertex AI Gemini fine-tuning, using the 'contents' and 'parts' structure.
    """
    print(f"Starting conversion of {input_file} for Vertex AI (v2)...")
    converted_count = 0
    
    try:
        with open(input_file, 'r') as infile, open(output_file, 'w') as outfile:
            training_data = json.load(infile)
            
            for item in training_data:
                try:
                    user_message = item.get('user')
                    assistant_message = item.get('peepingNami')
                    
                    if user_message and assistant_message:
                        # --- MODIFIED: Create the exact structure Vertex AI requires ---
                        vertex_example = {
                            "contents": [
                                {
                                    "role": "user",
                                    "parts": [{"text": user_message}]
                                },
                                {
                                    "role": "model",
                                    "parts": [{"text": assistant_message}]
                                }
                            ]
                        }
                        
                        json.dump(vertex_example, outfile)
                        outfile.write('\n')
                        converted_count += 1
                        
                except KeyError:
                    print(f"Skipping item with missing 'user' or 'peepingNami' keys: {item}")

    except json.JSONDecodeError:
        print(f"Error: The input file {input_file} is not a valid JSON file.")
        return
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return
                
    print(f"Conversion complete. Converted {converted_count} examples.")
    print(f"Output file created at: {output_file}")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(base_dir, 'training_data.json')
    output_path = os.path.join(base_dir, 'gemini_training_data.jsonl')
    
    if not os.path.exists(input_path):
        print(f"ERROR: Input file not found at {input_path}")
    else:
        convert_to_vertex_format(input_path, output_path)