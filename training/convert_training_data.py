#!/usr/bin/env python3
import json
import os
import random

def convert_nami_data():
    # Load your training data
    with open('training_data.json', 'r') as f:
        training_data = json.load(f)
    
    formatted_data = []
    
    for item in training_data:
        if 'dialogue' in item:
            # Handle multi-turn dialogues
            for exchange in item['dialogue']:
                text = f"User: {exchange['user']}\nNami: {exchange['peepingNami']}"
                formatted_data.append({"text": text})
        else:
            # Handle single exchanges
            user_content = item.get('user', '')
            nami_response = item.get('peepingNami', '')
            
            if user_content and nami_response:
                text = f"User: {user_content}\nNami: {nami_response}"
                formatted_data.append({"text": text})

    # Shuffle and split
    random.seed(42)
    random.shuffle(formatted_data)
    split_index = int(len(formatted_data) * 0.9)
    train_data = formatted_data[:split_index]
    val_data = formatted_data[split_index:]
    
    os.makedirs('data', exist_ok=True)
    
    # Save training
    with open('data/train.jsonl', 'w') as f:
        for item in train_data:
            f.write(json.dumps(item) + '\n')
    
    # Save validation
    with open('data/valid.jsonl', 'w') as f:
        for item in val_data:
            f.write(json.dumps(item) + '\n')
    
    print(f"Converted and split {len(formatted_data)} examples into:")
    print(f"  - {len(train_data)} training -> data/train.jsonl")
    print(f"  - {len(val_data)} validation -> data/valid.jsonl")
    
    if train_data:
        print("\nSample training example:")
        print(json.dumps(train_data[0], indent=2))

if __name__ == "__main__":
    convert_nami_data()
