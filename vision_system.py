import sys
import threading
import subprocess
import atexit
import importlib.util
import time

# Global variables
vision_process = None
vision_queue = None

def vision_output_reader(process):
    """Read and format output from the vision.py process"""
    for line in iter(process.stdout.readline, b''):
        # Decode the line
        line_str = line.decode('utf-8').rstrip()
        
        # Skip empty lines
        if not line_str.strip():
            continue
        
        # First, handle special line formats
        if line_str.strip().startswith(("[SUMMARY]", "[Summary]")):
            # Format summary line - don't truncate!
            formatted = line_str.replace("[SUMMARY]", "[VISION SUMMARY] 👁️")
            formatted = formatted.replace("[Summary]", "[VISION SUMMARY] 👁️")
            print(f"\n{formatted}")
            print("You: ", end="", flush=True)
        elif any(x in line_str for x in ["Error", "Exception", "WARNING"]):
            # Print error messages
            print(f"\n[VISION ERROR] ⚠️ {line_str}")
            print("You: ", end="", flush=True)
        elif line_str.strip().startswith(("0.", "1.", "2.")):
            # Analysis line with time prefix (e.g. "1.2s: The image shows...")
            parts = line_str.split(":", 1)
            if len(parts) > 1:
                time_part = parts[0].strip()
                content_part = parts[1].strip()
                formatted = f"[VISION] 👁️ ({time_part}): {content_part}"
                print(f"\n{formatted}")
                print("You: ", end="", flush=True)
        else:
            # Any other analysis output
            if len(line_str.strip()) > 0:  # Skip truly empty lines
                print(f"\n[VISION] 👁️ {line_str}")
                print("You: ", end="", flush=True)

def monitor_vision_queue():
    """Monitor the vision queue for new items"""
    if vision_queue is None:
        print("Vision queue is not available.")
        return
        
    print("Starting vision queue monitor...")
    # Track processed summaries to avoid duplication
    processed_items = set()
    
    while True:
        try:
            # Check if there are items in the queue
            item = vision_queue.get(block=False)
            
            # Create a unique identifier for this item
            item_id = f"{item.get('type', 'unknown')}-{hash(item.get('text', ''))}"
            
            # Only process if we haven't seen this exact item before
            if item_id not in processed_items:
                if item['type'] == 'analysis':
                    print(f"\n[VISION QUEUE] 👁️ Analysis: {item['text']}")
                    print("You: ", end="", flush=True)
                elif item['type'] == 'summary':
                    # Only print summaries from queue if they're not coming through stdout
                    # This is a backup in case the summary doesn't appear in stdout
                    print(f"\n[VISION QUEUE] 👁️ Summary: {item['text']}")
                    print("You: ", end="", flush=True)
                elif item['type'] == 'error':
                    print(f"\n[VISION QUEUE] ⚠️ Error: {item['text']}")
                    print("You: ", end="", flush=True)
                
                # Track that we've processed this item
                processed_items.add(item_id)
                
                # Limit the size of the processed set to avoid memory issues
                if len(processed_items) > 1000:
                    processed_items.clear()
            
            # Mark as done
            vision_queue.task_done()
        except Exception:
            # No items in queue, wait a bit
            time.sleep(0.1)

def start_vision_system(output_reader=None):
    """Start the vision.py script as a subprocess"""
    global vision_process, vision_queue
    
    try:
        # Try to import the vision module to access its queue
        spec = importlib.util.spec_from_file_location("vision", "vision.py")
        vision_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(vision_module)
        
        # Get access to the vision queue
        if hasattr(vision_module, 'get_vision_queue'):
            vision_queue = vision_module.get_vision_queue()
            
            # Start a thread to monitor the queue
            queue_thread = threading.Thread(
                target=monitor_vision_queue,
                daemon=True
            )
            queue_thread.start()
            
            print("Vision queue monitoring started.")
        
        # Start the process with full buffer size to avoid truncation
        cmd = [sys.executable, "vision.py"]
        vision_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=False,
            bufsize=0  # No buffering to avoid truncation
        )
        
        # Register cleanup function to terminate the process on exit
        atexit.register(lambda: vision_process.terminate() if vision_process else None)
        
        # Use custom output reader if provided, otherwise use default
        reader_func = output_reader if output_reader else vision_output_reader
        
        # Start thread to read its output
        output_thread = threading.Thread(
            target=reader_func,
            args=(vision_process,),
            daemon=True
        )
        output_thread.start()
        
        print("Vision system started successfully!")
        return True
    except Exception as e:
        print(f"Error starting vision system: {e}")
        return False

def check_vision_queue():
    """Check the current state of the vision queue"""
    if vision_queue is None:
        print("Vision queue is not available.")
        return
        
    try:
        # Report on the queue state
        queue_size = vision_queue.qsize()
        print(f"Vision queue has {queue_size} items.")
    except Exception as e:
        print(f"Error checking vision queue: {e}")

def stop_vision_system():
    """Stop the vision system"""
    global vision_process
    if vision_process:
        vision_process.terminate()
        vision_process.wait()
        vision_process = None
        print("Vision system stopped.")