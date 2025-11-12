import subprocess
import os
import sys
import threading
import time

# --- Path to the audio_mon app ---
AUDIO_MON_PATH = "/Users/thomasbalaban/Downloads/projects/audio_mon"
AUDIO_MON_PYTHON = "/Users/thomasbalaban/miniconda3/envs/nami-hearing/bin/python"

# Global variable to hold the audio_mon process
audio_mon_process = None

def _log_output(pipe, prefix="[AudioMon]"):
    """Reads and logs output from the audio_mon app's stdout/stderr."""
    try:
        for line in iter(pipe.readline, b''):
            decoded_line = line.decode('utf-8', errors='ignore').strip()
            # Filter out some noise if you want
            if decoded_line and not decoded_line.startswith('['):
                print(f"{prefix} {decoded_line}")
            else:
                print(decoded_line)
    finally:
        pipe.close()

def start_audio_mon_process():
    """Starts the audio_mon process using the explicit path."""
    global audio_mon_process

    if not os.path.isdir(AUDIO_MON_PATH):
        print("\n" + "="*60)
        print("FATAL ERROR: audio_mon path is not configured correctly.")
        print(f"Attempted to use path: '{AUDIO_MON_PATH}'")
        print("Please check 'nami/audio_process_manager.py' file.")
        print("="*60 + "\n")
        return

    main_script_path = os.path.join(AUDIO_MON_PATH, 'main.py')

    if not os.path.exists(main_script_path):
        print(f"Error: Found the directory '{AUDIO_MON_PATH}', but could not find 'main.py' inside it.")
        return

    try:
        print(f"🎙️ Starting audio_mon process from: {main_script_path}")
        print(f"   Using Python: {AUDIO_MON_PYTHON}")
        
        audio_mon_process = subprocess.Popen(
            [AUDIO_MON_PYTHON, main_script_path],
            cwd=AUDIO_MON_PATH,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Start threads to log output
        stdout_thread = threading.Thread(
            target=_log_output, 
            args=(audio_mon_process.stdout, "[AudioMon]"), 
            daemon=True
        )
        stderr_thread = threading.Thread(
            target=_log_output, 
            args=(audio_mon_process.stderr, "[AudioMon ERROR]"), 
            daemon=True
        )
        stdout_thread.start()
        stderr_thread.start()

        print("✅ audio_mon process started successfully")
        
        # Give it a moment to initialize
        time.sleep(3)
        
        # Check if it's still running
        if audio_mon_process.poll() is not None:
            print("❌ audio_mon process exited immediately. Check the error output above.")
            return False
            
        print("✅ audio_mon is running and ready for connections")
        return True

    except Exception as e:
        print(f"❌ An unexpected error occurred while starting audio_mon: {e}")
        return False

def stop_audio_mon_process():
    """Stops the audio_mon process."""
    global audio_mon_process
    if audio_mon_process:
        print("🛑 Stopping audio_mon process...")
        audio_mon_process.terminate()
        try:
            audio_mon_process.wait(timeout=5)
            print("✅ audio_mon process terminated.")
        except subprocess.TimeoutExpired:
            print("⚠️ audio_mon did not terminate gracefully, killing it.")
            audio_mon_process.kill()
            audio_mon_process.wait()
            print("✅ audio_mon process killed.")
        audio_mon_process = None
    else:
        print("ℹ️ audio_mon process was not running.")