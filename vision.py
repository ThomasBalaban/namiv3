import ollama
import cv2
import time
import base64
from mss import mss
import numpy as np
from PIL import Image
from io import BytesIO
from config import MONITOR_AREA
import os
import threading
import queue
import sys
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
MIN_FRAME_CHANGE = 0.10
SUMMARY_INTERVAL = 5

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

PROMPT = """
Analyze ONLY what is currently visible. Describe concisely in 1-3 sentences. Do not assume what or try to guess what the content is. Try to describe the subject focus, what they are, what they look like, what they are doing, and where they are.
"""

def optimize_frame(frame):
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

def generate_summary():
    with summary_lock:
        recent_analyses = list(analysis_history)[-5:]

    if not recent_analyses:
        return "No recent activity"

    summary_prompt = f"""Current situation summary from these events:
    {chr(10).join(recent_analyses)}
    Concise 1-3 sentence overview that attempts to guess what is happening currently from all of the image descriptions providing. Then try to guess what is currently happening. Try to follow the details of specific characters described."""
    
    try:
        response = ollama.generate(
            model=SUMMARY_MODEL,
            prompt=summary_prompt,
            options={'temperature': 0.2, 'num_predict': 250}
        )
        summary_text = response['response']
        
        # Add to queue with confidence score
        add_to_queue("summary", summary_text, 0.9, {
            "model": SUMMARY_MODEL,
            "source_type": "SUMMARY"
        })
        
        return summary_text
    except Exception as e:
        error_msg = f"Summary error: {str(e)}"
        add_to_queue("error", error_msg, 0.1)
        return error_msg

def validate_frame(frame):
    global last_valid_frame
    
    if last_valid_frame is None:
        return True
        
    current_np = np.array(frame)
    last_np = np.array(last_valid_frame)
    
    # Ensure arrays are compatible for comparison
    if current_np.shape != last_np.shape:
        return True
    
    diff = cv2.absdiff(current_np, last_np)
    change_percent = np.count_nonzero(diff) / diff.size
    
    # Add frame change information to queue if significant
    if change_percent > MIN_FRAME_CHANGE:
        add_to_queue("frame_change", f"Screen changed ({change_percent:.2f})", 
                    change_percent, {"change_percent": change_percent})
        return True
    return False

def summary_worker():
    global last_summary_time
    while True:
        time.sleep(1)
        if time.time() - last_summary_time > SUMMARY_INTERVAL:
            summary = generate_summary()
            with summary_lock:
                summarized_context.append(summary)
                last_summary_time = time.time()

def analyze_frame(frame):
    start_time = time.time()
    try:
        response = ollama.chat(
            model=MODEL,
            messages=[{
                "role": "user", 
                "content": PROMPT, 
                "images": [optimize_frame(frame)]
            }],
            options={
                'temperature': 0.2,
                'num_ctx': 1024,
                'num_gqa': 4,
                'seed': int(time.time())
            }
        )
        result = response['message']['content'].strip()
        process_time = time.time() - start_time
        
        with summary_lock:
            analysis_history.append(f"{result}")
        
        # Add analysis to queue with confidence and metadata
        confidence = min(0.95, max(0.5, 1.0 - (process_time / 10.0)))  # Higher confidence for faster processing
        add_to_queue("analysis", result, confidence, {
            "process_time": process_time,
            "model": MODEL,
            "source_type": "VISUAL_ANALYSIS"
        })
        
        return result, process_time
    
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        add_to_queue("error", error_msg, 0.1)
        return error_msg, 0

def video_analysis_loop():
    global last_valid_frame
    
    # Configure stdout to be line-buffered
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(line_buffering=True)
    else:
        # For older Python versions
        sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 1)
    
    # Start summary worker
    threading.Thread(target=summary_worker, daemon=True).start()
    
    add_to_queue("system", "Vision system initialized", 0.99)

    with mss() as sct:
        while True:
            try:
                # Capture frame
                frame = Image.frombytes('RGB', sct.grab(CAPTURE_REGION).size, sct.grab(CAPTURE_REGION).rgb)
                
                if validate_frame(frame):
                    last_valid_frame = frame.copy()
                    
                    # Process synchronously
                    analyze_frame(last_valid_frame)
                else:
                    # Even if frame didn't change, let the system know we're still active
                    time.sleep(0.1)  # Prevent CPU overload

                # Exit check
                if cv2.waitKey(25) & 0xFF == ord('q'):
                    break
            except Exception as e:
                error_msg = f"Frame capture error: {str(e)}"
                add_to_queue("error", error_msg, 0.1)
                time.sleep(1)  # Pause briefly on error

    cv2.destroyAllWindows()

def get_vision_queue():
    """Function to access the vision queue from external modules"""
    return vision_queue

if __name__ == "__main__":
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
        video_analysis_loop()
    except Exception as e:
        add_to_queue("error", f"Startup error: {str(e)}", 0.1)
        print(f"Fatal error: {str(e)}", flush=True)