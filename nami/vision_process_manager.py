import subprocess
import os
import sys
import threading

# --- MODIFIED: Import the config variable directly ---
try:
    from nami.config import VISION_APP_PATH
except ImportError:
    VISION_APP_PATH = None

# --- NEW: Set the path to the specific python executable here ---
# This path is the exact location found using 'which python' in your environment.
PYTHON_EXECUTABLE = "/Users/thomasbalaban/miniconda3/envs/gemini-screen-watcher/bin/python"

# Global variable to hold the vision process
vision_process = None

def _log_output(pipe):
    """Reads and logs output from the vision app's stdout/stderr."""
    try:
        for line in iter(pipe.readline, b''):
            print(f"[VisionApp] {line.decode('utf-8', errors='ignore').strip()}")
    finally:
        pipe.close()

def start_vision_process():
    """Starts the desktop_monitor_gemini process using the explicit path from config."""
    global vision_process

    if not VISION_APP_PATH or not os.path.isdir(VISION_APP_PATH):
        print("\n" + "="*60)
        print("FATAL ERROR: Vision process path is not configured correctly.")
        print(f"Attempted to use path: '{VISION_APP_PATH}'")
        print("Please check your 'nami/config.py' file.")
        print("="*60 + "\n")
        return

    gemini_path = VISION_APP_PATH
    main_script_path = os.path.join(gemini_path, 'main.py')

    if not os.path.exists(main_script_path):
        print(f"Error: Found the directory '{gemini_path}', but could not find 'main.py' inside it.")
        return

    try:
        print(f"Starting vision process from: {main_script_path} using executable: {PYTHON_EXECUTABLE}")
        vision_process = subprocess.Popen(
            [PYTHON_EXECUTABLE, main_script_path],
            cwd=gemini_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout_thread = threading.Thread(target=_log_output, args=(vision_process.stdout,), daemon=True)
        stderr_thread = threading.Thread(target=_log_output, args=(vision_process.stderr,), daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        print("Vision process started successfully. Monitoring its output.")

    except Exception as e:
        print(f"An unexpected error occurred while starting the vision process: {e}")

def stop_vision_process():
    """Stops the desktop_monitor_gemini process."""
    global vision_process
    if vision_process:
        print("Stopping vision process...")
        vision_process.terminate()
        try:
            vision_process.wait(timeout=5)
            print("Vision process terminated.")
        except subprocess.TimeoutExpired:
            print("Vision process did not terminate gracefully, killing it.")
            vision_process.kill()
            vision_process.wait()
            print("Vision process killed.")
        vision_process = None