#!/usr/bin/env python3
"""
Test the trained Nami LoRA
"""

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# Configuration
BASE_MODEL = "google/gemma-2-27b-it"
LORA_PATH = "./nami-lora-adapters"

def load_nami_model():
    """Load the base model with trained LoRA adapters"""
    print("Loading base model...")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.float16,
        device_map="auto",
        low_cpu_mem_usage=True,
    )
    
    print("Loading LoRA adapters...")
    model = PeftModel.from_pretrained(base_model, LORA_PATH)
    
    print("Model ready!")
    return model, tokenizer

def generate_response(model, tokenizer, prompt, max_length=200):
    """Generate a response from Nami"""
    # Format prompt in Gemma chat format
    formatted_prompt = f"<start_of_turn>user\n{prompt}\n<end_of_turn>\n<start_of_turn>model\n"
    
    # Tokenize
    inputs = tokenizer(formatted_prompt, return_tensors="pt")
    
    # Generate
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_length=max_length,
            do_sample=True,
            temperature=0.8,
            top_p=0.9,
            pad_token_id=tokenizer.eos_token_id,
        )
    
    # Decode response
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    
    # Extract just Nami's response
    if "<start_of_turn>model\n" in response:
        nami_response = response.split("<start_of_turn>model\n")[-1]
        if "<end_of_turn>" in nami_response:
            nami_response = nami_response.split("<end_of_turn>")[0]
        return nami_response.strip()
    
    return response

def interactive_chat():
    """Interactive chat with Nami"""
    print("Loading Nami...")
    model, tokenizer = load_nami_model()
    
    print("\nNami is ready! Type 'quit' to exit.")
    print("=" * 50)
    
    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() in ['quit', 'exit', 'q']:
            break
            
        print("Nami: ", end="", flush=True)
        response = generate_response(model, tokenizer, user_input)
        print(response)

def test_responses():
    """Test with some sample prompts"""
    print("Loading Nami for testing...")
    model, tokenizer = load_nami_model()
    
    test_prompts = [
        "Hey Nami, roast me",
        "I died again in the same spot in the game",
        "Nami there are 3 wires, red blue and yellow",
        "I just beat the boss!",
        "Hello, this is pizza hut"
    ]
    
    print("\nTesting Nami's responses:")
    print("=" * 50)
    
    for prompt in test_prompts:
        print(f"\nUser: {prompt}")
        response = generate_response(model, tokenizer, prompt)
        print(f"Nami: {response}")
        print("-" * 30)

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_responses()
    else:
        interactive_chat()