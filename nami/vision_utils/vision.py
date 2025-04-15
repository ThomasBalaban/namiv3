import ollama
import cv2
import time
import base64
import os
import threading
import queue
import sys
import numpy as np
from mss import mss
from PIL import Image
from io import BytesIO
from nami.config import MONITOR_AREA
from collections import deque

# Create a queue for external access to ALL vision data
vision_queue = queue.Queue()

os.environ['OLLAMA_GPU_LAYERS'] = "99"
os.environ['OLLAMA_GGML_METAL'] = "1"
os.environ['OLLAMA_KEEP_ALIVE'] = "0"

# Configuration
MODEL = "llava:13b"
SUMMARY_MODEL = "mistral-nemo:latest"
CAPTURE_REGION = MONITOR_AREA

# Context storage
analysis_history = deque(maxlen=10)
summarized_context = deque(maxlen=3)
summary_lock = threading.Lock()
last_summary_time = 0
last_valid_frame = None  # Global frame tracker

# Reduce OpenCV verbose output
os.environ['CV_IMPORT_VERBOSE'] = '0'
os.environ['CV_IO_SUPPRESS_MSGF'] = '1'
os.environ['PYTHONWARNINGS'] = 'ignore::UserWarning'

cv2.setNumThreads(2)
cv2.ocl.setUseOpenCL(False)

def optimize_frame(frame):
    """Convert a PIL image to base64 encoded JPEG for LLM processing"""
    # Resize the image to reduce processing time/tokens
    frame = frame.resize((800, 800), Image.BILINEAR)
    buffered = BytesIO()
    frame.save(buffered, format="JPEG", quality=95, optimize=True)
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

def add_to_queue(source_type, text, confidence=None, metadata=None):
    """Unified function to add items to the vision queue"""
    timestamp = time.strftime("%H:%M:%S")
    
    # Create consistent message format
    message = {
        "source": "VISUAL_CHANGE",  # Fixed source for compatibility with other systems
        "type": source_type,        # Type for internal differentiation
        "text": text,
        "score": confidence or 0.7, # Default confidence score if not provided
        "timestamp": timestamp,
        "metadata": metadata or {}
    }
    
    # Add to queue
    vision_queue.put(message)
    
    # Print to console for debugging
    if source_type == "error":
        print(f"[VISION ERROR] {text}", flush=True)
    else:
        # Format consistently with other output in the system
        print(f"[VISION] 👁️ {text}", flush=True)
    
    return message

def get_vision_queue():
    """Function to access the vision queue from external modules"""
    return vision_queue

# Import the processor module - do this AFTER defining the functions it depends on
from nami.vision_utils import vision_processor

# Initialize the processor module
processor = vision_processor.init(
    vision_queue,
    analysis_history,
    summarized_context,
    summary_lock,
    add_to_queue
)

# Get functions from the processor
validate_frame = processor["validate_frame"]
summary_worker = processor["summary_worker"]
analyze_frame = processor["analyze_frame"]
video_analysis_loop = processor["video_analysis_loop"]
generate_summary = processor["generate_summary"]

def start_vision():
    """Function to start the vision analysis loop"""
    # Disable output buffering
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(line_buffering=True)
    else:
        # For older Python versions
        sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 1)
    
    add_to_queue("system", "Starting vision system", 0.99)
    
    try:
        # Warmup model with timeout protection
        add_to_queue("system", "Loading model...", 0.8)
        ollama.generate(model=MODEL, prompt="Ready")
        add_to_queue("system", "Model loaded successfully", 0.99)
        
        # Start the vision analysis loop
        with mss() as sct:
            video_analysis_loop(sct, CAPTURE_REGION, optimize_frame)
            
    except Exception as e:
        add_to_queue("error", f"Startup error: {str(e)}", 0.1)
        print(f"Fatal error: {str(e)}", flush=True)

# Run directly if this script is executed as the main program
if __name__ == "__main__":
    start_vision()