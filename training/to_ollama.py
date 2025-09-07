#!/usr/bin/env python3
"""
to_ollama.py
Convert a trained MLX model -> Hugging Face -> GGUF -> Ollama model.

Requirements:
- mlx_lm installed and on PATH (for the convert CLI) OR importable (for Python fallback)
- llama.cpp conversion available:
    EITHER `python -m llama_cpp.convert` (from `pip install llama-cpp-python>=0.2.90`)
    OR `convert-hf-to-gguf.py` in PATH (from the llama.cpp repo)

Ollama usage after success:
    ollama run nami
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

SRC_MODEL_MLX = Path("./nami-trained")
# --- CHANGE 1: Point directly to your existing model directory ---
DST_MODEL_HF  = Path("./nami-trained")
DST_GGUF_DIR  = Path("./nami-gguf")
DST_GGUF_FILE = DST_GGUF_DIR / "nami.Q5_K_M.gguf"   # choose your quant (Q5_K_M is a good balance)

def run(cmd, **popen_kwargs):
    print("▶", " ".join(cmd))
    return subprocess.run(cmd, text=True, capture_output=True, **popen_kwargs)

def ensure_clean_dir(p: Path):
    if p.exists():
        print(f"ℹ Removing existing: {p}")
        shutil.rmtree(p)
    p.mkdir(parents=True, exist_ok=True)

# 1) MLX -> HF (This function is no longer called)
def convert_mlx_to_hf():
    """Convert MLX model to HuggingFace format first (handles multiple mlx_lm versions)."""
    from pathlib import Path
    import shutil, sys, subprocess

    mlx_model_path = Path("./nami-trained")
    hf_output_path = Path("./nami-hf")

    print("Converting MLX model to HuggingFace format...")
    print(f"Source: {mlx_model_path}")
    print(f"Output: {hf_output_path}")

    if not mlx_model_path.exists():
        print(f"❌ MLX model not found at {mlx_model_path}")
        return False

    if hf_output_path.exists():
        print(f"ℹ Removing existing: {hf_output_path}")
        shutil.rmtree(hf_output_path)

    # Try 1: console entrypoint (some installs provide `mlx_lm`)
    cmd1 = ["mlx_lm", "convert", "--mlx-path", str(mlx_model_path), "--hf-path", str(hf_output_path)]
    print("▶", " ".join(cmd1))
    try:
        res = subprocess.run(cmd1, capture_output=True, text=True)
        if res.returncode == 0:
            print("✅ MLX → HF conversion successful (mlx_lm CLI).")
            return True
        else:
            print("CLI failed:", res.stderr.strip() or res.stdout.strip())
    except FileNotFoundError:
        pass

    # Try 2: dotted module (older versions)
    cmd2 = [sys.executable, "-m", "mlx_lm.convert", "--mlx-path", str(mlx_model_path), "--hf-path", str(hf_output_path)]
    print("▶", " ".join(cmd2))
    res = subprocess.run(cmd2, capture_output=True, text=True)
    if res.returncode == 0:
        print("✅ MLX → HF conversion successful (python -m mlx_lm.convert).")
        return True
    else:
        print("Dotted module failed:", res.stderr.strip() or res.stdout.strip())

    # Try 3: Python API (older signature uses mlx_path/hf_path)
    try:
        from mlx_lm.convert import convert as mlx_convert
        mlx_convert(mlx_path=str(mlx_model_path), hf_path=str(hf_output_path))
        print("✅ MLX → HF conversion successful (Python API).")
        return True
    except Exception as e:
        print("❌ MLX → HF conversion failed:", e)
        return False

# 2) HF -> GGUF via llama.cpp
def convert_hf_to_gguf() -> bool:
    print("\n=== Step 2: HF -> GGUF ===")
    if not DST_MODEL_HF.exists():
        print(f"❌ HF folder not found at {DST_MODEL_HF.resolve()}")
        return False

    ensure_clean_dir(DST_GGUF_DIR)

    # First try the python module from llama-cpp-python
    cmd = [
        sys.executable, "-m", "llama_cpp.convert",
        str(DST_MODEL_HF), # The model path is now the first argument in recent versions
        "--outfile", str(DST_GGUF_FILE),
        "--outtype", "q5_k_m"
    ]
    res = run(cmd)
    if res.returncode == 0 and DST_GGUF_FILE.exists():
        print("✅ HF → GGUF conversion successful (llama_cpp.convert).")
        return True
    else:
        # Fallback to older argument style for broader compatibility
        print("ℹ Retrying GGUF conversion with older argument style...")
        cmd_old_style = [
            sys.executable, "-m", "llama_cpp.convert",
            "--hf-path", str(DST_MODEL_HF),
            "--outtype", "q5_k_m",
            "--outfile", str(DST_GGUF_FILE)
        ]
        res = run(cmd_old_style)
        if res.returncode == 0 and DST_GGUF_FILE.exists():
            print("✅ HF → GGUF conversion successful (llama_cpp.convert with --hf-path).")
            return True

    print("❌ HF → GGUF conversion failed.")
    print("Hint: `pip install --upgrade llama-cpp-python` or clone llama.cpp and run its converter.")
    if res and (res.stderr or res.stdout):
        print("\n--- Error details ---")
        print(res.stderr.strip())
        print(res.stdout.strip())
        print("---------------------\n")
    return False

# 3) Modelfile for Ollama (GGUF)
def write_modelfile_for_gguf():
    print("\n=== Step 3: Write Modelfile ===")
    content = f"""FROM {DST_GGUF_FILE.resolve()}

# Simple Nami chat prompt template (adjust to your tokenizer/chat format as needed)
TEMPLATE \"\"\"<|im_start|>system
You are Nami, a playful, witty assistant. Stay in character.
<|im_end|>
<|im_start|>user
{{{{ .Prompt }}}}
<|im_end|>
<|im_start|>assistant
\"\"\"

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER num_ctx 4096

SYSTEM \"\"\"You are Nami, a helpful, honest, and mischievous assistant fine-tuned by Otter. Keep replies concise and in character.\"\"\"
"""
    modelfile_path = Path("Modelfile")
    modelfile_path.write_text(content)
    print(f"✅ Wrote Modelfile (GGUF) → {modelfile_path.resolve()}")

# 4) Create Ollama model
def create_ollama_model() -> bool:
    print("\n=== Step 4: Create Ollama model ===")
    if not DST_GGUF_FILE.exists():
        print(f"❌ GGUF file missing: {DST_GGUF_FILE.resolve()}")
        return False

    write_modelfile_for_gguf()

    cmd = ["ollama", "create", "nami", "-f", "Modelfile"]
    res = run(cmd)
    if res.returncode == 0:
        print("✅ Ollama model 'nami' created!")
        return True
    print("❌ Ollama create failed:")
    print(res.stderr.strip())
    print(res.stdout.strip())
    return False

def main():
    print("🚀 Converting Nami to Ollama format")
    print("=" * 60)

    # --- CHANGE 2: Skipped the failing MLX->HF conversion step ---
    # if not convert_mlx_to_hf():
    #     sys.exit(1)

    if not convert_hf_to_gguf():
        sys.exit(2)

    if create_ollama_model():
        print("\n🎉 Success! Test with:\n  ollama run nami \"Hey Nami, say hi!\"")
    else:
        print("\n❌ Final step failed. Ensure Ollama is installed and reachable (try `ollama --version`).")

if __name__ == "__main__":
    main()