#!/usr/bin/env python3
import os, json
from transformers import AutoConfig, AutoTokenizer

SRC_MODEL_ID = "mistralai/Mistral-Nemo-Instruct-2407"
MODEL_DIR = "./nami-trained"

print("Fetching base config from", SRC_MODEL_ID)
base_config = AutoConfig.from_pretrained(SRC_MODEL_ID).to_dict()

cfg_path = os.path.join(MODEL_DIR, "config.json")
os.makedirs(MODEL_DIR, exist_ok=True)
with open(cfg_path, "w") as f:
    json.dump(base_config, f, indent=2)
print("Wrote", cfg_path)

print("Fetching tokenizer files…")
tok = AutoTokenizer.from_pretrained(SRC_MODEL_ID)
tok.save_pretrained(MODEL_DIR)

print("✅ Done. Your nami-trained folder now has a real config.json + tokenizer files.")
print("Try generation again with:")
print("  python -m mlx_lm generate --model ./nami-trained --prompt 'User: hey Nami, roast me\\nNami:' --max-tokens 128")
