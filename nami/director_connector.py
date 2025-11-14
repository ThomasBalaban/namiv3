# Save as: nami/director_connector.py
import socketio
import threading
import time
from typing import Dict, Any, Optional

DIRECTOR_URL = "http://localhost:8002"

# Create a standard Socket.IO client
sio = socketio.Client(reconnection_attempts=10, reconnection_delay=5)
connector_thread = None
is_running = False

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
    """Runs the Socket.IO client in a persistent loop."""
    global is_running
    is_running = True
    while is_running:
        try:
            print(f"[DirectorConnector] Attempting to connect to {DIRECTOR_URL}...")
            sio.connect(DIRECTOR_URL, transports=['websocket'])
            sio.wait() # This blocks until disconnected
        except socketio.exceptions.ConnectionError as e:
            print(f"[DirectorConnector] Connection error: {e}. Retrying in 5s...")
            time.sleep(5)
        except Exception as e:
            print(f"[DirectorConnector] An unknown error occurred: {e}. Retrying in 5s...")
            time.sleep(5)

def start_connector_thread():
    """Starts the connector in a background daemon thread."""
    global connector_thread
    if connector_thread is None or not connector_thread.is_alive():
        connector_thread = threading.Thread(target=run_connector, daemon=True)
        connector_thread.start()
        print("[DirectorConnector] Connector thread started.")

def stop_connector():
    """Stops the Socket.IO client."""
    global is_running
    is_running = False
    if sio.connected:
        sio.disconnect()
    print("[DirectorConnector] Connector stopped.")

def send_event(
    source_str: str,
    text: str,
    metadata: Dict[str, Any],
    username: Optional[str] = None
):
    """
    Sends an event to the Director Engine via Socket.IO.
    This is thread-safe and non-blocking.
    """
    if not sio.connected:
        # Don't flood logs if director is down
        # print("[DirectorConnector] Not connected, cannot send event.")
        return

    payload = {
        "source_str": source_str,
        "text": text,
        "metadata": metadata or {},
        "username": username
    }
    
    try:
        # .emit() is thread-safe
        sio.emit("event", payload)
        # print(f"Sent event: {source_str}") # Optional: for debugging
    except Exception as e:
        print(f"[DirectorConnector] Error sending event: {e}")