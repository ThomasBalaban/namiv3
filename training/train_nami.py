#!/usr/bin/env python3
"""
train_nami_ultra_conservative.py
Ultra-conservative settings for Metal GPU buffer limits
"""

import os
import inspect
import mlx.core as mx
import mlx.optimizers as optim
import psutil
from mlx_lm import load
from mlx_lm.tuner import train, TrainingArgs
from mlx_lm.tuner.datasets import load_dataset

SRC_MODEL_ID = "google/gemma-2-27b-it"

def get_memory_usage():
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 ** 3)

class TokenExample:
    def __init__(self, tokens):
        if not tokens:
            tokens = [0]
        self.tokens = mx.array(tokens, dtype=mx.int32)

    def __getitem__(self, key):
        if key == 0:
            return self.tokens
        if isinstance(key, slice):
            return self.tokens[key]
        raise IndexError("TokenExample supports [0] and [:] only.")

    def __len__(self):
        return len(self.tokens)

def robust_save(model, tokenizer, config, outdir: str, src_model_id: str = SRC_MODEL_ID):
    from mlx_lm.utils import save as mlx_save
    os.makedirs(outdir, exist_ok=True)

    if config is None:
        config = {"model_id": src_model_id, "format": "mlx"}

    sig = inspect.signature(mlx_save)
    params = list(sig.parameters.keys())

    if params == ["model", "tokenizer", "path"]:
        return mlx_save(model, tokenizer, outdir)
    elif params == ["model", "tokenizer", "config", "path"]:
        return mlx_save(model, tokenizer, config, outdir)
    elif params[:5] == ["dst_path", "src_path", "model", "tokenizer", "config"]:
        return mlx_save(outdir, src_model_id, model, tokenizer, config)
    else:
        kwargs = {"dst_path": outdir, "src_path": src_model_id, "model": model, "tokenizer": tokenizer}
        if "config" in params:
            kwargs["config"] = config
        return mlx_save(**kwargs)

def train_ultra_conservative():
    print("=== Ultra-Conservative Gemma-3-27B Training ===")
    print(f"System RAM: {psutil.virtual_memory().total / (1024**3):.1f} GB")
    print(f"Available RAM: {psutil.virtual_memory().available / (1024**3):.1f} GB")
    print(f"Metal GPU buffer limit: ~77GB")
    print(f"Initial memory usage: {get_memory_usage():.2f} GB")
    
    print("\nLoading model...")
    try:
        model, tokenizer, config = load(SRC_MODEL_ID, return_config=True)
    except TypeError:
        model, tokenizer = load(SRC_MODEL_ID)
        config = None
    
    print(f"✅ Model loaded. Memory: {get_memory_usage():.2f} GB")

    # ULTRA conservative settings - should definitely work
    TOTAL_ITERS = 100   # Reduced total
    CHUNK_ITERS = 10    # Very small chunks

    args = TrainingArgs(
        batch_size=1,               # Keep at 1
        iters=CHUNK_ITERS,          
        val_batches=1,              # Only 1 validation sample
        steps_per_report=2,         # Report every 2 steps
        steps_per_eval=5,           # Eval every 5 steps
        steps_per_save=10**9,       # No saves
        max_seq_length=384,         # MUCH smaller - key change!
        adapter_file=None,          
        grad_checkpoint=True,       
    )

    # Disable any optional features that might use memory
    try:
        args.packing = False
    except:
        pass

    args.data = "data"
    args.train = True
    args.test = False

    print("\nLoading and preparing dataset...")
    datasets = load_dataset(args, tokenizer)
    
    # More aggressive filtering and truncation
    print("Aggressively filtering dataset...")
    raw_train = datasets[0]
    raw_val = datasets[1]
    
    train_data = []
    for item in raw_train:
        tokens = tokenizer.encode(item["text"])
        # Truncate to much shorter sequences
        if len(tokens) > args.max_seq_length:
            tokens = tokens[:args.max_seq_length]
        train_data.append(TokenExample(tokens))
    
    val_data = []
    for item in raw_val:
        tokens = tokenizer.encode(item["text"])
        if len(tokens) > args.max_seq_length:
            tokens = tokens[:args.max_seq_length]
        val_data.append(TokenExample(tokens))
    
    # Only use a subset for the first test
    train_data = train_data[:30]  # Use fewer samples
    val_data = val_data[:3]       # Fewer validation samples
    
    print(f"Dataset prepared. Memory: {get_memory_usage():.2f} GB")
    print(f"Training samples: {len(train_data)}, Validation: {len(val_data)}")
    
    train_lengths = [len(item.tokens) for item in train_data]
    print(f"Sequence lengths - Min: {min(train_lengths)}, Max: {max(train_lengths)}, Avg: {sum(train_lengths)/len(train_lengths):.1f}")

    print("\nUltra-conservative training configuration:")
    print(f"  Model: Gemma-3-27B")
    print(f"  Total iters: {TOTAL_ITERS} (chunks of {CHUNK_ITERS})")
    print(f"  Batch size: {args.batch_size}")
    print(f"  Max seq len: {args.max_seq_length}")
    print(f"  Training samples: {len(train_data)} (reduced for testing)")

    # Use a very small learning rate to be extra safe
    optimizer = optim.Adam(learning_rate=5e-6)

    done = 0
    try:
        while done < TOTAL_ITERS:
            run_iters = min(CHUNK_ITERS, TOTAL_ITERS - done)
            args.iters = run_iters
            
            print(f"\n=== Chunk starting @ iter {done} → {done + run_iters} ===")
            print(f"Memory before chunk: {get_memory_usage():.2f} GB")
            
            # Force garbage collection
            import gc
            gc.collect()
            
            # Try to free up as much memory as possible
            mx.metal.clear_cache()  # Clear Metal cache if available
            
            try:
                print("Starting training step...")
                train(
                    model=model,
                    optimizer=optimizer,
                    train_dataset=train_data,
                    val_dataset=val_data,
                    args=args,
                )
                
                done += run_iters
                print(f"✅ Chunk completed! Progress: {done}/{TOTAL_ITERS}")
                print(f"Memory after chunk: {get_memory_usage():.2f} GB")
                
                # Save checkpoint every 20 iterations
                if done % 20 == 0:
                    checkpoint_dir = f"nami-gemma-checkpoint-{done}"
                    robust_save(model, tokenizer, config, checkpoint_dir)
                    print(f"Checkpoint saved: {checkpoint_dir}")
                
            except Exception as e:
                error_msg = str(e)
                print(f"❌ Training error: {error_msg}")
                print(f"Memory at error: {get_memory_usage():.2f} GB")
                
                if ("Memory" in error_msg or 
                    "kIOGPUCommandBufferCallbackErrorOutOfMemory" in error_msg):
                    
                    print("\n🚨 Still hitting Metal GPU buffer limit!")
                    print("\nThis suggests the 27B model is too large for full fine-tuning")
                    print("on this Metal GPU configuration.")
                    print("\nRecommendations:")
                    print("1. Try Gemma-2-9B instead (much smaller)")
                    print("2. Use LoRA training with the 27B model")
                    print("3. Try a different training framework")
                    
                    # Emergency save attempt
                    try:
                        emergency_dir = f"nami-gemma-emergency-{done}"
                        robust_save(model, tokenizer, config, emergency_dir)
                        print(f"Emergency save: {emergency_dir}")
                    except:
                        print("Emergency save failed")
                    
                    return False
                else:
                    print(f"Non-memory error: {error_msg}")
                    raise

        # Final save
        final_dir = "nami-gemma-trained"
        robust_save(model, tokenizer, config, final_dir)
        print(f"\n🎉 Ultra-conservative training completed! Model: {final_dir}")
        return True
        
    except KeyboardInterrupt:
        print("\n⏹️ Training interrupted")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = train_ultra_conservative()
    if success:
        print("\n✅ Training succeeded with ultra-conservative settings!")
        print("You can now try increasing max_seq_length or batch_size.")
    else:
        print("\n❌ Even ultra-conservative settings failed.")
        print("Consider switching to Gemma-2-9B or using LoRA training.")