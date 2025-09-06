import sys
import threading
import subprocess
import atexit
from nami.audio_utils import hearing
from nami.ui import emit_audio_context

# Global variables
hearing_process = None

def _output_reader_thread(process, callback):
    """
    Internal thread function to read subprocess output and invoke a callback.
    """
    for line in iter(process.stdout.readline, b''):
        line_str = line.decode('utf-8').rstrip()
        
        # Send audio context to UI
        if line_str:
            emit_audio_context(line_str)
        
        # Pass the line to the processing function in main.py
        if callback:
            try:
                callback(line_str)
            except Exception as e:
                print(f"Error in hearing system callback: {e}")

def start_hearing_system(callback=None):
    """
    Start the hearing.py script as a subprocess and process its output
    with a provided callback function.
    """
    global hearing_process
    cmd = [sys.executable, hearing.__file__]

    try:
        hearing_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=False,
            bufsize=0
        )

        atexit.register(lambda: hearing_process.terminate() if hearing_process else None)

        # Start the thread that reads output and calls our new processor
        output_thread = threading.Thread(
            target=_output_reader_thread,
            args=(hearing_process, callback),
            daemon=True
        )
        output_thread.start()

        print("Hearing system started successfully!")
        return True
    except Exception as e:
        print(f"Error starting hearing system: {e}")
        return False

def stop_hearing_system():
    """Stop the hearing system by sending a terminate signal without waiting."""
    global hearing_process
    if hearing_process:
        print("Sending stop signal to hearing system...")
        hearing_process.terminate()
        hearing_process = None
        print("Hearing system stop signal sent.")

