import json

def convert_nami_data():
    # Load your training data
    with open('training_data.json', 'r') as f:
        training_data = json.load(f)
    
    converted_data = []
    
    for item in training_data:
        if 'dialogue' in item:
            # Handle multi-turn dialogues
            for exchange in item['dialogue']:
                converted_data.append({
                    "messages": [
                        {"role": "user", "content": exchange['user']},
                        {"role": "assistant", "content": exchange['peepingNami']}
                    ]
                })
        else:
            # Handle single exchanges
            user_content = item.get('user', '')
            nami_response = item.get('peepingNami', '')
            
            if user_content and nami_response:
                converted_data.append({
                    "messages": [
                        {"role": "user", "content": user_content},
                        {"role": "assistant", "content": nami_response}
                    ]
                })
    
    # Save in MLX format (JSONL)
    with open('nami_training_data.jsonl', 'w') as f:
        for item in converted_data:
            f.write(json.dumps(item) + '\n')
    
    print(f"Converted {len(converted_data)} training examples")
    print("Saved to: nami_training_data.jsonl")
    
    # Show a sample
    if converted_data:
        print("\nSample training example:")
        print(json.dumps(converted_data[0], indent=2))

if __name__ == "__main__":
    convert_nami_data()