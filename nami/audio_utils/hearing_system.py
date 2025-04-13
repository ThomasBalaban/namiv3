import sys
import threading
import subprocess
import atexit

# Import the hearing module from the package structure
from nami.audio_utils import hearing

# Global variables
hearing_process = None

def hearing_output_reader(process):
    """Read and format output from the hearing.py process"""
    for line in iter(process.stdout.readline, b''):
        # Decode the line
        line_str = line.decode('utf-8').rstrip()
        
        # Check if it's a transcription line
        if ("[Microphone Input]" in line_str or
            ("]" in line_str and any(x in line_str for x in ["SPEECH", "MUSIC"]))):
            
            # Format based on source
            if "[Microphone Input]" in line_str:
                formatted = line_str.replace("[Microphone Input]", "[HEARING] 🎤")
            else:
                formatted = line_str.replace("[", "[HEARING] 🔊 [", 1)
            
            # Print formatted transcript with clear separation
            print(f"\n{formatted}")
            print("You: ", end="", flush=True)
        
        # Print other important output lines (like startup messages)
        elif any(x in line_str for x in ["Loading", "Starting", "Initializing", "Error", "Vosk"]):
            print(f"[Hearing] {line_str}")

def start_hearing_system(debug_mode=False, output_reader=None):
    """Start the hearing.py script as a subprocess"""
    global hearing_process
    
    # Use the module's file path directly
    cmd = [sys.executable, hearing.__file__]
    if debug_mode:
        cmd.append("--debug")
    
    try:
        # Start the process without specifying bufsize to avoid the warning
        hearing_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=False,
            bufsize=0  # No buffering to avoid truncation
        )
        
        # Register cleanup function to terminate the process on exit
        atexit.register(lambda: hearing_process.terminate() if hearing_process else None)
        
        # Use custom output reader if provided, otherwise use default
        reader_func = output_reader if output_reader else hearing_output_reader
        
        # Start thread to read its output
        output_thread = threading.Thread(
            target=reader_func,
            args=(hearing_process,),
            daemon=True
        )
        output_thread.start()
        
        print("Hearing system started successfully!")
        return True
    except Exception as e:
        print(f"Error starting hearing system: {e}")
        return False

def stop_hearing_system():
    """Stop the hearing system"""
    global hearing_process
    if hearing_process:
        hearing_process.terminate()
        hearing_process.wait()
        hearing_process = None
        print("Hearing system stopped.")