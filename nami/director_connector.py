# Save as: nami/director_connector.py
import socketio
import threading
import time
import httpx
from typing import Dict, Any, Optional

DIRECTOR_URL = "http://localhost:8002"
PROMPT_SERVICE_URL = "http://localhost:8001"

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
            
            sio.connect(
                DIRECTOR_URL, 
                transports=['websocket', 'polling'],
                wait_timeout=10
            )
            consecutive_failures = 0
            
            while is_running and sio.connected:
                time.sleep(1)
                
        except socketio.exceptions.ConnectionError as e:
            consecutive_failures += 1
            wait_time = min(5 * consecutive_failures, 30)
            print(f"[DirectorConnector] Connection error (attempt {consecutive_failures}): {e}")
            print(f"[DirectorConnector] Retrying in {wait_time}s...")
            
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

def _http_fallback(url: str, payload: dict = None, method: str = "POST") -> bool:
    """HTTP fallback for any URL."""
    try:
        with httpx.Client(timeout=2.0) as client:
            if method == "POST":
                response = client.post(url, json=payload or {})
            else:
                response = client.get(url)
            return response.status_code == 200
    except Exception as e:
        print(f"[DirectorConnector] HTTP fallback failed for {url}: {e}")
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

# =====================================================
# SPEECH STATE — Now routes to PROMPT SERVICE (8001)
# =====================================================

def notify_speech_started(source: str = "UNKNOWN"):
    """
    Notify the Prompt Service that Nami has started speaking.
    
    CHANGED: Previously went to Director (8002).
    Now goes to Prompt Service (8001) which owns all speaking state.
    """
    payload = {"source": source}
    url = f"{PROMPT_SERVICE_URL}/speech_started"
    
    if _http_fallback(url, payload):
        print(f"[DirectorConnector] 🔇 Notified Prompt Service: speech_started (source: {source})")
    else:
        print(f"[DirectorConnector] ⚠️ Failed to notify speech_started (Prompt Service may be offline)")

def notify_speech_finished():
    """
    Notify the Prompt Service that Nami has finished speaking.
    
    CHANGED: Previously went to Director (8002).
    Now goes to Prompt Service (8001) which owns all speaking state.
    """
    url = f"{PROMPT_SERVICE_URL}/speech_finished"
    
    if _http_fallback(url):
        print("[DirectorConnector] 🔊 Notified Prompt Service: speech_finished")
    else:
        print("[DirectorConnector] ⚠️ Failed to notify speech_finished (Prompt Service may be offline)")