import os
import torch

# Optimized configuration
FS = 16000
CHUNK_DURATION = 3
OVERLAP = 1
MODEL_SIZE = "medium.en"  # More efficient for CPU
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
SAVE_DIR = "audio_captures"
MAX_THREADS = 3  # Limit concurrent processing threads