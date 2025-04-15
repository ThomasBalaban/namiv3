import ollama
import cv2
import time
import threading
import numpy as np
from collections import deque
import os
from PIL import Image

# These will be imported from vision.py
vision_queue = None
last_valid_frame = None
analysis_history = None
summarized_context = None
summary_lock = None
last_summary_time = None

# Configuration constants - these could be moved to a config file later
MIN_FRAME_CHANGE = 0.10
SUMMARY_INTERVAL = 5
MODEL = "llava:13b"
SUMMARY_MODEL = "mistral-nemo:latest"

PROMPT = """
Analyze ONLY what is currently visible. Describe concisely in 1-3 sentences. Do not assume what or try to guess what the content is. Try to describe the subject focus, what they are, what they look like, what they are doing, and where they are.
"""

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

def analyze_frame(frame, optimize_frame_func):
    start_time = time.time()
    try:
        # Convert frame to PIL Image if it's not already
        if not isinstance(frame, Image.Image):
            pil_frame = Image.fromarray(frame)
        else:
            pil_frame = frame
            
        response = ollama.chat(
            model=MODEL,
            messages=[{
                "role": "user", 
                "content": PROMPT, 
                "images": [optimize_frame_func(pil_frame)]
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

def video_analysis_loop(sct, CAPTURE_REGION, optimize_frame_func):
    global last_valid_frame
    
    # Start summary worker
    threading.Thread(target=summary_worker, daemon=True).start()
    
    add_to_queue("system", "Vision system initialized", 0.99)

    while True:
        try:
            # Capture frame - ensure we get the right format
            sct_img = sct.grab(CAPTURE_REGION)
            
            # Create a PIL Image from the screenshot
            frame = Image.frombytes(
                'RGB', 
                (sct_img.width, sct_img.height), 
                sct_img.rgb
            )
            
            if validate_frame(frame):
                last_valid_frame = frame.copy()
                
                # Process synchronously
                analyze_frame(last_valid_frame, optimize_frame_func)
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

# Initialize function to be called from vision.py
def init(queue, history, context, lock, queue_function):
    global vision_queue, analysis_history, summarized_context, summary_lock, last_summary_time, add_to_queue
    
    vision_queue = queue
    analysis_history = history
    summarized_context = context
    summary_lock = lock
    last_summary_time = time.time()
    add_to_queue = queue_function
    
    return {
        "validate_frame": validate_frame,
        "summary_worker": summary_worker,
        "analyze_frame": analyze_frame,
        "video_analysis_loop": video_analysis_loop,
        "generate_summary": generate_summary
    }