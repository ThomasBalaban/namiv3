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
from collections import deque
import threading
import imagehash
from concurrent.futures import ThreadPoolExecutor

# Configuration
MODEL = "llava:7b"
SUMMARY_MODEL = "llama2:7b"
CAPTURE_REGION = MONITOR_AREA
SUMMARY_INTERVAL = 12  # Seconds between summaries

# Context storage
analysis_history = deque(maxlen=10)  # Store last 10 analyses
summarized_context = deque(maxlen=3)   # Store last 3 summaries
summary_lock = threading.Lock()
last_summary_time = 0

os.environ['CV_IMPORT_VERBOSE'] = '0'
os.environ['CV_IO_SUPPRESS_MSGF'] = '1'
os.environ['PYTHONWARNINGS'] = 'ignore::UserWarning'

cv2.setNumThreads(2)
cv2.ocl.setUseOpenCL(False)

PROMPT = """
Analyze visible screen content with focus for stuff like the following
1. Primary focus/activity
2. Key visual elements
4. Potential context clues

Example: "Code editor with Python file, multiple terminal windows running processes, alert notification in top-right corner"
Example: Playing game, possible Elden Ring. A warrior draws their sword facing a dragon in murky wetlands."

Rules:
1. 25-60 words
2. Describe observable elements
3. No assumptions about content type
4. Note both persistent and transient elements
"""

# Image optimization pipeline
def optimize_frame(frame):
    frame = frame.resize((512, 512))
    buffered = BytesIO()
    frame.save(buffered, format="JPEG", quality=85, optimize=True)
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

def generate_summary():
    with summary_lock:
        recent_analyses = list(analysis_history)[-5:]  # Last 5 analyses

    if not recent_analyses:
        return "No recent activity"

    summary_prompt = f"""
    Create a concise gameplay summary from these sequential events.
    Focus on persistent elements and ongoing actions.
    Maximum 2 sentences. Structure:
    1. Main ongoing activity
    2. Recent developments
    3. Current immediate focus

    Events:
    {chr(10).join(recent_analyses)}

    Rules: 
    1. Limit reply to 300 characters
    """

    try:
        response = ollama.generate(
            model=SUMMARY_MODEL,
            prompt=summary_prompt,
            options={'temperature': 0.3, 'num_predict': 180}
        )
        return "Summary: " + response['response'].strip()
    except Exception as e:
        return f"Summary error: {str(e)}"

def summary_worker():
    global last_summary_time
    while True:
        time.sleep(3)  # Check every 3 seconds
        if time.time() - last_summary_time > SUMMARY_INTERVAL:
            summary = generate_summary()
            with summary_lock:
                summarized_context.append(summary)
                last_summary_time = time.time()
                print(f"\n[CONTEXT UPDATE] {summary}\n")

# Pure vision analysis without summarization
def analyze_frame(frame):
    start_time = time.time()
    try:
        response = ollama.chat(
            model=MODEL,
            messages=[
                {"role": "user", "content": PROMPT, "images": [optimize_frame(frame)]}
            ],
            options={'temperature': 0.3, 'num_predict': 60}
        )
        result = '[analyze_frame]: ' + response['message']['content']
        process_time = time.time() - start_time
        with summary_lock:
            analysis_history.append(result)
        return result, process_time
    except Exception as e:
        return f"Error: {str(e)}", 0

# Helper function to offload analysis
def analyze_and_print(frame):
    analysis, process_time = analyze_frame(frame)
    print(f"[{process_time:.1f}s] {analysis}")

# Main analysis loop with asynchronous analysis using a thread pool
def video_analysis_loop():
    last_phash = None
    last_analysis_time = time.time()
    # Set a lower analysis interval for more frequent checks (e.g., 0.2 seconds)
    analysis_interval = 0.2

    # Start summary thread
    threading.Thread(target=summary_worker, daemon=True).start()

    with mss() as sct, ThreadPoolExecutor(max_workers=2) as executor:
        while True:
            sct_img = sct.grab(CAPTURE_REGION)
            frame = Image.frombytes('RGB', sct_img.size, sct_img.rgb)
            current_phash = imagehash.phash(frame)

            # Update preview as fast as possible
            cv2.imshow('Preview', cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR))

            if time.time() - last_analysis_time > analysis_interval:
                phash_changed = (current_phash - last_phash) > 5 if last_phash else True
                if phash_changed:
                    last_analysis_time = time.time()
                    last_phash = current_phash
                    # Offload the analysis to a separate thread
                    executor.submit(analyze_and_print, frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cv2.destroyAllWindows()

if __name__ == "__main__":
    # Warm up the models
    ollama.generate(model=MODEL, prompt="Warm up")
    ollama.generate(model=SUMMARY_MODEL, prompt="Warm up")
    video_analysis_loop()
