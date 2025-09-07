#!/usr/bin/env python3

import mlx.core as mx
import mlx.optimizers as optim
from mlx_lm import load
from mlx_lm.tuner import train, TrainingArgs
from mlx_lm.tuner.datasets import load_dataset
import os

def train_nami():
    """Train Nami using the correct MLX API"""
    
    print("Starting Nami training...")
    
    # Load model and tokenizer
    print("Loading Mistral-Nemo model...")
    model, tokenizer = load("mistralai/Mistral-Nemo-Instruct-2407")
    print("Model loaded successfully!")
    
    # Create training arguments first (needed for dataset loading)
    args = TrainingArgs(
        batch_size=1,              # Conservative for memory
        iters=200,                 # Reduced iterations for first test
        val_batches=10,            # Validation batches  
        steps_per_report=10,       # Report progress every 10 steps
        steps_per_eval=50,         # Evaluate every 50 steps
        steps_per_save=100,        # Save checkpoint every 100 steps
        max_seq_length=2048,       # Reasonable sequence length
        adapter_file=None,         # This should disable LoRA and enable full fine-tuning
        grad_checkpoint=True       # Save memory with gradient checkpointing
    )
    
    # Add the required attributes for dataset loading
    args.data = "nami_training_data.jsonl"
    args.train = True  # Enable training mode
    
    # Check if we need to set this to None differently
    if hasattr(args, 'adapter_file'):
        args.adapter_file = None
    
    # Load dataset
    print("Loading training dataset...")
    train_dataset, valid_dataset = load_dataset(args, tokenizer)
    print(f"Dataset loaded: {len(train_dataset)} training examples")
    
    print("Training configuration:")
    print(f"  Batch size: {args.batch_size}")
    print(f"  Iterations: {args.iters}")
    print(f"  Max sequence length: {args.max_seq_length}")
    print(f"  Full fine-tuning: True")
    
    # Create optimizer
    optimizer = optim.Adam(learning_rate=1e-5)
    
    # Start training
    print("\nStarting training...")
    try:
        train(
            model=model,
            optimizer=optimizer, 
            train_dataset=train_dataset,
            val_dataset=valid_dataset,
            args=args
        )
        
        print("Training completed!")
        
        # Save the model using MLX utils
        print("Saving model...")
        from mlx_lm.utils import save
        output_dir = "./nami-trained"
        os.makedirs(output_dir, exist_ok=True)
        save(model, tokenizer, output_dir)
        print(f"Model saved to {output_dir}")
        
    except Exception as e:
        print(f"Training error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    train_nami()