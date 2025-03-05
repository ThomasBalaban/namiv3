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

# Create a queue for external access to vision data
vision_queue = queue.Queue()

os.environ['OLLAMA_GPU_LAYERS'] = "99"
os.environ['OLLAMA_GGML_METAL'] = "1"
os.environ['OLLAMA_KEEP_ALIVE'] = "0"

# Configuration
#MODEL = "llava:7b-v1.6-mistral-q4_K_M"  # Super fast but seems inaccurate for phas
MODEL = "llava:13b"
#MODEL = "llama3.2-vision:latest"
#MODEL = "minicpm-v:latest"
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

def generate_summary():
    with summary_lock:
        recent_analyses = list(analysis_history)[-5:]

    if not recent_analyses:
        return "No recent activity"

    summary_prompt = f"""Current situation summary from these events:
    {chr(10).join(recent_analyses)}
    Concise 1-3 sentence overview that attempts to guess what is happening currently from all of the image descriptions providing. Then try to guess what is currently happening. Try to follow the details of spcefic characters described."""
    
    try:
        response = ollama.generate(
            model=SUMMARY_MODEL,
            prompt=summary_prompt,
            options={'temperature': 0.2, 'num_predict': 250}
        )
        summary_text = "Summary: " + response['response']
        
        # Add to the queue for external access
        vision_queue.put({
            "type": "summary",
            "text": summary_text,
            "timestamp": time.strftime("%H:%M:%S")
        })
        
        # Print with explicit flush to ensure immediate output
        print(f"\n[SUMMARY] {summary_text}\n", flush=True)
        
        return summary_text
    except Exception as e:
        error_msg = f"Summary error: {str(e)}"
        
        # Add error to the queue
        vision_queue.put({
            "type": "error",
            "text": error_msg,
            "timestamp": time.strftime("%H:%M:%S")
        })
        
        # Print with explicit flush
        print(f"\nError: {error_msg}\n", flush=True)
        
        return error_msg

def validate_frame(frame):
    global last_valid_frame
    
    if last_valid_frame is None:
        return True
        
    current_np = np.array(frame)
    last_np = np.array(last_valid_frame)
    
    diff = cv2.absdiff(current_np, last_np)
    return (np.count_nonzero(diff) / diff.size) > MIN_FRAME_CHANGE

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
        
        # Add the analysis to the queue for external access
        vision_queue.put({
            "type": "analysis",
            "text": result,
            "process_time": process_time,
            "timestamp": time.strftime("%H:%M:%S")
        })
        
        # Print with explicit flush to ensure immediate output
        print(f"\n{process_time:.1f}s: {result}", flush=True)
        return result, process_time
    
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        
        # Add error to the queue
        vision_queue.put({
            "type": "error",
            "text": error_msg,
            "timestamp": time.strftime("%H:%M:%S")
        })
        
        # Print with explicit flush
        print(f"\nError: {error_msg}", flush=True)
        
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
    
    print("Vision system initialized", flush=True)

    with mss() as sct:
        while True:
            # Capture and validate frame
            frame = Image.frombytes('RGB', sct.grab(CAPTURE_REGION).size, sct.grab(CAPTURE_REGION).rgb)
            
            if validate_frame(frame):
                last_valid_frame = frame.copy()
                
                # Process synchronously
                analyze_frame(last_valid_frame)

            # Exit check
            if cv2.waitKey(25) & 0xFF == ord('q'):
                break

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
    
    print("Starting vision system", flush=True)
    ollama.generate(model=MODEL, prompt="Ready")  # Warmup
    print("Model loaded", flush=True)
    video_analysis_loop()