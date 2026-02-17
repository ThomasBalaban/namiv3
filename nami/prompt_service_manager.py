# Save as: nami/prompt_service_manager.py
import subprocess
import os
import threading
import time

# --- Path to the prompt_service app ---
# Lives alongside director_engine as a sibling directory
PROMPT_SERVICE_PATH = "/Users/thomasbalaban/Downloads/projects/prompt_service"

# --- Uses the same conda env as director-engine ---
# (Only needs fastapi, uvicorn, httpx, pydantic — all already installed)
PROMPT_SERVICE_PYTHON = "/Users/thomasbalaban/miniconda3/envs/director-engine/bin/python"

# Global variable to hold the process
prompt_service_process = None


def _log_output(pipe, prefix="[PromptService]"):
    """Reads and logs output from the prompt service's stdout/stderr."""
    try:
        for line in iter(pipe.readline, b''):
            decoded_line = line.decode('utf-8', errors='ignore').strip()
            print(f"{prefix} {decoded_line}")
    finally:
        pipe.close()


def start_prompt_service():
    """Starts the prompt service process."""
    global prompt_service_process

    if not os.path.isdir(PROMPT_SERVICE_PATH):
        print("\n" + "=" * 60)
        print("⚠️ WARNING: prompt_service path not found.")
        print(f"Attempted: '{PROMPT_SERVICE_PATH}'")
        print("Prompt Service will NOT be running — speech gating disabled.")
        print("Director will still work, but all speech requests go ungated.")
        print("=" * 60 + "\n")
        return False

    if not os.path.exists(PROMPT_SERVICE_PYTHON):
        print("\n" + "=" * 60)
        print("⚠️ WARNING: prompt_service python executable not found.")
        print(f"Attempted: '{PROMPT_SERVICE_PYTHON}'")
        print("=" * 60 + "\n")
        return False

    main_script_path = os.path.join(PROMPT_SERVICE_PATH, 'main.py')

    if not os.path.exists(main_script_path):
        print(f"⚠️ Found directory '{PROMPT_SERVICE_PATH}', but no 'main.py' inside.")
        return False

    try:
        print(f"🎤 Starting Prompt Service (The Mouth) from: {main_script_path}")
        print(f"   Using Python: {PROMPT_SERVICE_PYTHON}")

        prompt_service_process = subprocess.Popen(
            [PROMPT_SERVICE_PYTHON, main_script_path],
            cwd=PROMPT_SERVICE_PATH,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "PYTHONUNBUFFERED": "1"}
        )

        stdout_thread = threading.Thread(
            target=_log_output,
            args=(prompt_service_process.stdout, "[PromptService]"),
            daemon=True
        )
        stderr_thread = threading.Thread(
            target=_log_output,
            args=(prompt_service_process.stderr, "[PromptService ERROR]"),
            daemon=True
        )
        stdout_thread.start()
        stderr_thread.start()

        print("⏳ Waiting for Prompt Service to boot...")
        time.sleep(3)

        if prompt_service_process.poll() is not None:
            print("❌ Prompt Service exited immediately. Check errors above.")
            return False

        print("✅ Prompt Service is running on port 8001")
        return True

    except Exception as e:
        print(f"❌ Error starting Prompt Service: {e}")
        return False


def stop_prompt_service():
    """Stops the prompt service process."""
    global prompt_service_process
    if prompt_service_process:
        print("🛑 Stopping Prompt Service...")
        prompt_service_process.terminate()
        try:
            prompt_service_process.wait(timeout=5)
            print("✅ Prompt Service terminated.")
        except subprocess.TimeoutExpired:
            print("⚠️ Prompt Service did not terminate, killing it.")
            prompt_service_process.kill()
            prompt_service_process.wait()
            print("✅ Prompt Service killed.")
        prompt_service_process = None
    else:
        print("ℹ️ Prompt Service was not running.")