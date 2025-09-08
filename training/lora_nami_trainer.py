#!/usr/bin/env python3
"""
LoRA Training for Nami on Gemma-3-27B
Much faster and more memory efficient than full fine-tuning
"""

import os
import json
import torch
from transformers import (
    AutoModelForCausalLM, 
    AutoTokenizer, 
    TrainingArguments, 
    Trainer,
    DataCollatorForLanguageModeling
)
from peft import LoraConfig, get_peft_model, TaskType
from datasets import Dataset
import psutil

# Configuration
MODEL_NAME = "google/gemma-2-27b-it"  # We'll use the base model for LoRA
OUTPUT_DIR = "./nami-lora"
LORA_OUTPUT_DIR = "./nami-lora-adapters"

def get_memory_usage():
    """Get current memory usage"""
    process = psutil.Process(os.getpid())
    memory_gb = process.memory_info().rss / (1024 ** 3)
    if torch.cuda.is_available():
        gpu_memory = torch.cuda.memory_allocated() / (1024 ** 3)
        return f"RAM: {memory_gb:.2f}GB, GPU: {gpu_memory:.2f}GB"
    return f"RAM: {memory_gb:.2f}GB"

def load_training_data(data_path):
    """Load and format training data"""
    print(f"Loading training data from {data_path}...")
    
    data = []
    with open(data_path, 'r') as f:
        for line in f:
            item = json.loads(line)
            if 'messages' in item:
                # Convert to Gemma chat format
                conversation = ""
                for msg in item['messages']:
                    if msg['role'] == 'user':
                        conversation += f"<start_of_turn>user\n{msg['content']}\n<end_of_turn>\n"
                    elif msg['role'] == 'assistant':
                        conversation += f"<start_of_turn>model\n{msg['content']}\n<end_of_turn>\n"
                
                if conversation:
                    data.append({"text": conversation})
    
    print(f"Loaded {len(data)} training examples")
    return data

def create_dataset(data, tokenizer, max_length=1024):
    """Create tokenized dataset"""
    print("Tokenizing dataset...")
    
    def tokenize_function(examples):
        tokenized = tokenizer(
            examples["text"],
            truncation=True,
            padding=False,
            max_length=max_length,
            return_tensors=None,
        )
        tokenized["labels"] = tokenized["input_ids"].copy()
        return tokenized
    
    dataset = Dataset.from_list(data)
    tokenized_dataset = dataset.map(
        tokenize_function,
        batched=True,
        remove_columns=["text"],
        desc="Tokenizing"
    )
    
    print(f"Dataset tokenized. {len(tokenized_dataset)} examples")
    return tokenized_dataset

def setup_lora_model(model_name):
    """Setup model with LoRA configuration"""
    print(f"Loading model: {model_name}")
    print(f"Initial memory: {get_memory_usage()}")
    
    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    
    # Load base model (Mac compatible)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.float16,
        device_map="auto",
        low_cpu_mem_usage=True,
        trust_remote_code=True,  # Sometimes needed for newer models
    )
    
    print(f"Base model loaded. Memory: {get_memory_usage()}")
    
    # LoRA configuration
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=64,                    # LoRA rank - higher = more parameters but better quality
        lora_alpha=128,          # LoRA scaling parameter
        lora_dropout=0.1,        # LoRA dropout
        target_modules=[         # Gemma-specific target modules
            "q_proj",
            "k_proj", 
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj"
        ],
        bias="none",
        inference_mode=False,
    )
    
    # Apply LoRA to the model
    model = get_peft_model(model, lora_config)
    
    # Print trainable parameters
    model.print_trainable_parameters()
    
    print(f"LoRA model ready. Memory: {get_memory_usage()}")
    return model, tokenizer

def train_lora():
    """Main LoRA training function"""
    print("=" * 60)
    print("LoRA Training for Nami on Gemma-3-27B")
    print("=" * 60)
    print(f"GPU Available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name()}")
        print(f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f}GB")
    
    print(f"System RAM: {psutil.virtual_memory().total / 1024**3:.1f}GB")
    print(f"Available RAM: {psutil.virtual_memory().available / 1024**3:.1f}GB")
    
    # Create output directories
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(LORA_OUTPUT_DIR, exist_ok=True)
    
    # Load training data
    training_data = load_training_data("nami_training_data.jsonl")
    
    # Setup LoRA model
    model, tokenizer = setup_lora_model(MODEL_NAME)
    
    # Create dataset
    train_dataset = create_dataset(training_data, tokenizer, max_length=768)
    
    # Split into train/validation
    split_dataset = train_dataset.train_test_split(test_size=0.1, seed=42)
    train_data = split_dataset['train']
    eval_data = split_dataset['test']
    
    print(f"Training examples: {len(train_data)}")
    print(f"Validation examples: {len(eval_data)}")
    
    # Data collator
    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False,
    )
    
    # Training arguments optimized for LoRA (Mac compatible)
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        overwrite_output_dir=True,
        
        # Training schedule
        num_train_epochs=5,              
        per_device_train_batch_size=1,   
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=8,   
        
        # Optimization
        learning_rate=2e-4,              
        weight_decay=0.01,
        warmup_steps=50,
        
        # Memory optimization (Mac compatible)
        dataloader_pin_memory=False,
        gradient_checkpointing=False,    # Disabled - causing gradient issues
        fp16=False,                      # Disabled for Mac MPS compatibility
        
        # Evaluation and saving
        eval_strategy="steps",
        eval_steps=25,
        save_strategy="steps", 
        save_steps=50,
        save_total_limit=3,
        
        # Logging
        logging_dir="./logs",
        logging_steps=5,
        report_to=None,
        
        # LoRA specific
        remove_unused_columns=False,
    )
    
    # Initialize trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_data,
        eval_dataset=eval_data,
        tokenizer=tokenizer,
        data_collator=data_collator,
    )
    
    # Start training
    print("\nStarting LoRA training...")
    print(f"Memory before training: {get_memory_usage()}")
    
    try:
        trainer.train()
        
        # Save LoRA adapters
        print("Saving LoRA adapters...")
        model.save_pretrained(LORA_OUTPUT_DIR)
        tokenizer.save_pretrained(LORA_OUTPUT_DIR)
        
        print(f"✅ LoRA training completed!")
        print(f"LoRA adapters saved to: {LORA_OUTPUT_DIR}")
        print(f"Final memory: {get_memory_usage()}")
        
        # Instructions for using the trained LoRA
        print("\n" + "="*60)
        print("How to use your trained LoRA:")
        print("="*60)
        print(f"1. Base model: {MODEL_NAME}")
        print(f"2. LoRA adapters: {LORA_OUTPUT_DIR}")
        print("3. Load with:")
        print("   from peft import PeftModel")
        print(f"   model = AutoModelForCausalLM.from_pretrained('{MODEL_NAME}')")
        print(f"   model = PeftModel.from_pretrained(model, '{LORA_OUTPUT_DIR}')")
        
    except Exception as e:
        print(f"❌ Training error: {e}")
        print(f"Memory at error: {get_memory_usage()}")
        
        # Try to save checkpoint
        try:
            checkpoint_path = f"{LORA_OUTPUT_DIR}/emergency_checkpoint"
            model.save_pretrained(checkpoint_path)
            print(f"Emergency checkpoint saved to {checkpoint_path}")
        except:
            print("Failed to save emergency checkpoint")
        
        raise

if __name__ == "__main__":
    train_lora()