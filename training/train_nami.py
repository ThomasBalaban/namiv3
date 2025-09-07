#!/usr/bin/env python3
"""
train_nami.py
Full fine-tuning for Nami on MLX with robust saving across mlx_lm versions.
- Trains in small chunks to reduce Metal OOM risk.
- Disables adapter (LoRA) checkpoints entirely.
- Handles multiple mlx_lm.utils.save() signatures, including the one that expects:
    save(dst_path, src_path, model, tokenizer, config, hf_repo=None, donate_model=False)
"""

import os
import inspect
import mlx.core as mx
import mlx.optimizers as optim
from mlx_lm import load
from mlx_lm.tuner import train, TrainingArgs
from mlx_lm.tuner.datasets import load_dataset

# Keep the source model id in one place (needed by some save() signatures)
SRC_MODEL_ID = "mistralai/Mistral-Nemo-Instruct-2407"

# ---- Trainer-friendly wrapper ----
class TokenExample:
    """Small wrapper so mlx_lm.tuner.trainer works with both [0] and [:L] access."""
    def __init__(self, tokens):
        if not tokens:
            tokens = [0]
        self.tokens = mx.array(tokens, dtype=mx.int32)

    def __getitem__(self, key):
        if key == 0:                  # trainer calls dataset[idx][0]
            return self.tokens
        if isinstance(key, slice):    # trainer slices: batch[j][:L]
            return self.tokens[key]
        raise IndexError("TokenExample supports [0] and [:] only.")

    def __len__(self):
        return len(self.tokens)

# ---- Robust load & save helpers ----
def robust_load(model_id: str):
    """Load model, tokenizer, and (if possible) config."""
    try:
        # Newer mlx_lm exposes return_config
        model, tokenizer, config = load(model_id, return_config=True)
        return model, tokenizer, config
    except TypeError:
        # Older mlx_lm: no return_config
        model, tokenizer = load(model_id)
        config = getattr(model, "config", None)
        if config is None:
            # Minimal config stub is enough for utils.save to write config.json
            config = {
                "model_id": model_id,
                "format": "mlx",
                "note": "minimal config stub for mlx_lm.utils.save"
            }
        return model, tokenizer, config

def robust_save(model, tokenizer, config, outdir: str, src_model_id: str = SRC_MODEL_ID):
    """Call mlx_lm.utils.save with whatever signature this mlx_lm exposes."""
    from mlx_lm.utils import save as mlx_save
    os.makedirs(outdir, exist_ok=True)

    if config is None:
        config = {
            "model_id": src_model_id,
            "format": "mlx",
            "note": "auto-generated minimal config"
        }

    sig = inspect.signature(mlx_save)
    params = list(sig.parameters.keys())

    # Old signature: (model, tokenizer, path)
    if params == ["model", "tokenizer", "path"]:
        return mlx_save(model, tokenizer, outdir)

    # Common newer signature: (model, tokenizer, config, path)
    if params == ["model", "tokenizer", "config", "path"]:
        return mlx_save(model, tokenizer, config, outdir)

    # Your reported signature:
    # (dst_path, src_path, model, tokenizer, config, hf_repo, donate_model)
    if params[:5] == ["dst_path", "src_path", "model", "tokenizer", "config"]:
        return mlx_save(outdir, src_model_id, model, tokenizer, config)

    # Fallback: be permissive if order differs but names exist
    if {"dst_path", "src_path", "model", "tokenizer"}.issubset(params):
        kwargs = {"dst_path": outdir, "src_path": src_model_id, "model": model, "tokenizer": tokenizer}
        if "config" in params:
            kwargs["config"] = config
        return mlx_save(**kwargs)

    raise RuntimeError(f"Unsupported mlx_lm.utils.save signature: {params}")

# ---- Main training ----
def train_nami():
    print("Starting Nami training...")
    print("Loading Mistral-Nemo model...")
    model, tokenizer, config = robust_load(SRC_MODEL_ID)
    print("Model loaded successfully!")

    # Total schedule (chunked to reduce peak memory spikes)
    TOTAL_ITERS = 200
    CHUNK_ITERS = 50

    # Memory-friendly TrainingArgs
    args = TrainingArgs(
        batch_size=1,               # keep peak memory low
        iters=CHUNK_ITERS,          # will be adjusted per chunk
        val_batches=2,              # short validation to reduce spikes
        steps_per_report=10,
        steps_per_eval=50,          # eval each chunk end
        steps_per_save=10**9,       # never touch adapter save path (avoid %0)
        max_seq_length=1536,        # reduce seq len; try 1024 if you still OOM
        adapter_file=None,          # full FT; no LoRA/adapter checkpoints
        grad_checkpoint=True,       # save memory
    )
    # If supported, packing can improve throughput slightly
    try:
        args.packing = True
    except Exception:
        pass

    # Dataset settings
    args.data = "data"
    args.train = True
    args.test = False

    print("Loading training dataset...")
    datasets = load_dataset(args, tokenizer)
    train_dataset = [TokenExample(tokenizer.encode(item["text"])) for item in datasets[0]]
    valid_dataset = [TokenExample(tokenizer.encode(item["text"])) for item in datasets[1]]
    print(f"Dataset ready: {len(train_dataset)} train, {len(valid_dataset)} val")

    print("Training configuration:")
    print(f"  Total iters: {TOTAL_ITERS} (chunks of {CHUNK_ITERS})")
    print(f"  Batch size: {args.batch_size}")
    print(f"  Max seq len: {args.max_seq_length}")
    print(f"  Full fine-tuning: True")

    optimizer = optim.Adam(learning_rate=1e-5)

    done = 0
    try:
        while done < TOTAL_ITERS:
            run_iters = min(CHUNK_ITERS, TOTAL_ITERS - done)
            args.iters = run_iters
            print(f"\n=== Chunk starting @ iter {done} → {done + run_iters} ===")
            train(
                model=model,
                optimizer=optimizer,
                train_dataset=train_dataset,
                val_dataset=valid_dataset,
                args=args,
            )
            done += run_iters

        # Final save (handles your mlx_lm version automatically)
        outdir = "nami-trained"
        robust_save(model, tokenizer, config, outdir, src_model_id=SRC_MODEL_ID)
        print(f"[SAVE] Final model wrote to {outdir}")
        print("Training completed!")

    except Exception as e:
        print(f"[ERROR] Training crashed at iter {done}: {e}")
        # Best-effort emergency save
        try:
            emergency = os.path.join("nami-trained-snaps", f"emergency_step_{done:07d}")
            robust_save(model, tokenizer, config, emergency, src_model_id=SRC_MODEL_ID)
            print(f"[SAVE] Emergency model wrote to {emergency}")
        except Exception as ee:
            print(f"[ERROR] Emergency save failed: {ee}")
        raise

if __name__ == "__main__":
    train_nami()
