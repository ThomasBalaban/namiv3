# Save as nami/director_process_manager.py
import subprocess
import os
import sys
import threading
import time

# --- ASSUMED Path to the director_engine app ---
# !!! USER, PLEASE VERIFY THIS PATH !!!
DIRECTOR_ENGINE_PATH = "/Users/thomasbalaban/Downloads/projects/director_engine"

# --- ASSUMED Path to the director-engine conda env python ---
# !!! USER, PLEASE VERIFY THIS PATH !!!
# (Run `conda activate director-engine` then `which python`)
DIRECTOR_ENGINE_PYTHON = "/Users/thomasbalaban/miniconda3/envs/director-engine/bin/python"

# Global variable to hold the director_engine process
director_process = None

def _log_output(pipe, prefix="[DirectorEngine]"):
    """Reads and logs output from the director_engine app's stdout/stderr."""
    try:
        for line in iter(pipe.readline, b''):
            decoded_line = line.decode('utf-8', errors='ignore').strip()
            # We want to see the server logs
            print(f"{prefix} {decoded_line}")
    finally:
        pipe.close()

def start_director_process():
    """Starts the director_engine process using the explicit path."""
    global director_process

    if not os.path.isdir(DIRECTOR_ENGINE_PATH):
        print("\n" + "="*60)
        print("FATAL ERROR: director_engine path is not configured correctly.")
        print(f"Attempted to use path: '{DIRECTOR_ENGINE_PATH}'")
        print("Please check 'nami/director_process_manager.py' file.")
        print("="*60 + "\n")
        return False
        
    if not os.path.exists(DIRECTOR_ENGINE_PYTHON):
        print("\n" + "="*60)
        print("FATAL ERROR: director_engine python executable not found.")
        print(f"Attempted to use path: '{DIRECTOR_ENGINE_PYTHON}'")
        print("Please check 'nami/director_process_manager.py' file.")
        print("Run `conda activate director-engine` and `which python` to get the correct path.")
        print("="*60 + "\n")
        return False

    main_script_path = os.path.join(DIRECTOR_ENGINE_PATH, 'main.py')

    if not os.path.exists(main_script_path):
        print(f"Error: Found the directory '{DIRECTOR_ENGINE_PATH}', but could not find 'main.py' inside it.")
        return False

    try:
        print(f"🧠 Starting Director Engine (Brain 1) from: {main_script_path}")
        print(f"   Using Python: {DIRECTOR_ENGINE_PYTHON}")
        
        director_process = subprocess.Popen(
            [DIRECTOR_ENGINE_PYTHON, main_script_path],
            cwd=DIRECTOR_ENGINE_PATH,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "PYTHONUNBUFFERED": "1"} # Force unbuffered output
        )

        stdout_thread = threading.Thread(
            target=_log_output, 
            args=(director_process.stdout, "[DirectorEngine]"), 
            daemon=True
        )
        stderr_thread = threading.Thread(
            target=_log_output, 
            args=(director_process.stderr, "[DirectorEngine ERROR]"), 
            daemon=True
        )
        stdout_thread.start()
        stderr_thread.start()

        print("✅ Director Engine process starting...")
        # Give it time to boot, as it's a server and UI
        time.sleep(5) 
        
        if director_process.poll() is not None:
            print("❌ Director Engine process exited immediately. Check errors above.")
            return False
            
        print("✅ Director Engine is running and ready for connections")
        return True

    except Exception as e:
        print(f"❌ An unexpected error occurred while starting Director Engine: {e}")
        return False

def stop_director_process():
    """Stops the director_engine process."""
    global director_process
    if director_process:
        print("🛑 Stopping Director Engine process...")
        director_process.terminate()
        try:
            director_process.wait(timeout=5)
            print("✅ Director Engine process terminated.")
        except subprocess.TimeoutExpired:
            print("⚠️ Director Engine did not terminate, killing it.")
            director_process.kill()
            director_process.wait()
            print("✅ Director Engine process killed.")
        director_process = None
    else:
        print("ℹ️ Director Engine process was not running.")