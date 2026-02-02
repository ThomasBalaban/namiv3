# Save as: nami/director_connector.py
import socketio
import threading
import time
import httpx
from typing import Dict, Any, Optional

DIRECTOR_URL = "http://localhost:8002"

# Create a standard Socket.IO client with more aggressive reconnection
sio = socketio.Client(
    reconnection=True,
    reconnection_attempts=0,  # Infinite retries
    reconnection_delay=2,
    reconnection_delay_max=10,
    logger=False,
    engineio_logger=False
)

connector_thread = None
is_running = False
connection_lock = threading.Lock()

@sio.event
def connect():
    print("[DirectorConnector] ✅ Connected to Director Engine (Brain 1)")

@sio.event
def connect_error(data):
    print(f"[DirectorConnector] 🔥 Connection failed: {data}")

@sio.event
def disconnect():
    print("[DirectorConnector] 🔌 Disconnected from Director Engine")

def run_connector():
    """Runs the Socket.IO client in a persistent loop with better error handling."""
    global is_running
    is_running = True
    consecutive_failures = 0
    
    while is_running:
        try:
            with connection_lock:
                if sio.connected:
                    time.sleep(1)
                    continue
            
            print(f"[DirectorConnector] Attempting to connect to {DIRECTOR_URL}...")
            
            # Use a timeout for the connection attempt
            sio.connect(
                DIRECTOR_URL, 
                transports=['websocket', 'polling'],  # Allow fallback to polling
                wait_timeout=10
            )
            consecutive_failures = 0
            
            # Wait while connected
            while is_running and sio.connected:
                time.sleep(1)
                
        except socketio.exceptions.ConnectionError as e:
            consecutive_failures += 1
            wait_time = min(5 * consecutive_failures, 30)  # Cap at 30 seconds
            print(f"[DirectorConnector] Connection error (attempt {consecutive_failures}): {e}")
            print(f"[DirectorConnector] Retrying in {wait_time}s...")
            
            # Sleep in small increments so we can exit quickly if needed
            for _ in range(wait_time * 2):
                if not is_running:
                    break
                time.sleep(0.5)
                
        except Exception as e:
            consecutive_failures += 1
            print(f"[DirectorConnector] Unexpected error: {type(e).__name__}: {e}")
            time.sleep(5)

def start_connector_thread():
    """Starts the connector in a background daemon thread."""
    global connector_thread
    if connector_thread is None or not connector_thread.is_alive():
        connector_thread = threading.Thread(target=run_connector, daemon=True, name="DirectorConnector")
        connector_thread.start()
        print("[DirectorConnector] Connector thread started.")

def stop_connector():
    """Stops the Socket.IO client."""
    global is_running
    is_running = False
    
    try:
        if sio.connected:
            sio.disconnect()
    except Exception as e:
        print(f"[DirectorConnector] Error during disconnect: {e}")
    
    print("[DirectorConnector] Connector stopped.")

def _safe_emit(event: str, payload: dict) -> bool:
    """Safely emit an event, handling connection issues."""
    try:
        if sio.connected:
            sio.emit(event, payload)
            return True
        else:
            print(f"[DirectorConnector] Cannot emit '{event}' - not connected")
            return False
    except Exception as e:
        print(f"[DirectorConnector] Error emitting '{event}': {e}")
        return False

def _http_fallback(endpoint: str, payload: dict = None, method: str = "POST") -> bool:
    """HTTP fallback when socket is disconnected."""
    try:
        with httpx.Client(timeout=2.0) as client:
            url = f"{DIRECTOR_URL}{endpoint}"
            if method == "POST":
                response = client.post(url, json=payload or {})
            else:
                response = client.get(url)
            return response.status_code == 200
    except Exception as e:
        print(f"[DirectorConnector] HTTP fallback failed for {endpoint}: {e}")
        return False

def send_event(
    source_str: str,
    text: str,
    metadata: Dict[str, Any],
    username: Optional[str] = None
):
    """
    Sends an event to the Director Engine via Socket.IO.
    """
    payload = {
        "source_str": source_str,
        "text": text,
        "metadata": metadata or {},
        "username": username
    }
    
    _safe_emit("event", payload)

def send_bot_reply(reply_text, prompt_text="", is_censored=False, censorship_reason=None, filtered_area=None):
    payload = {
        "reply": reply_text,
        "prompt": prompt_text,
        "is_censored": is_censored,
        "censorship_reason": censorship_reason,
        "filtered_area": filtered_area
    }
    
    _safe_emit("bot_reply", payload)

def notify_speech_started(source: str = "UNKNOWN"):
    """
    Notify Director that Nami has started speaking.
    source should be 'USER_DIRECT' for responses to user, 'IDLE_THOUGHT' for idle chatter
    """
    payload = {"source": source}
    
    # Try socket first
    if _safe_emit("speech_started", payload):
        print(f"[DirectorConnector] 🔇 Notified Director: speech_started (source: {source})")
        return
    
    # HTTP fallback
    if _http_fallback("/speech_started", payload):
        print(f"[DirectorConnector] 🔇 Notified Director (HTTP): speech_started (source: {source})")
    else:
        print(f"[DirectorConnector] ⚠️ Failed to notify speech_started")

def notify_speech_finished():
    """
    Notify Director that Nami has finished speaking.
    This allows Director to resume sending interjections.
    """
    # Try socket first
    if _safe_emit("speech_finished", {}):
        print("[DirectorConnector] 🔊 Notified Director: speech_finished")
        return
    
    # HTTP fallback
    if _http_fallback("/speech_finished"):
        print("[DirectorConnector] 🔊 Notified Director (HTTP): speech_finished")
    else:
        print("[DirectorConnector] ⚠️ Failed to notify speech_finished")