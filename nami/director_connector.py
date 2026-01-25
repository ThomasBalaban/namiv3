# Save as: nami/director_connector.py
import socketio
import threading
import time
import httpx
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
    """
    if not sio.connected:
        return

    payload = {
        "source_str": source_str,
        "text": text,
        "metadata": metadata or {},
        "username": username
    }
    
    try:
        sio.emit("event", payload)
    except Exception as e:
        print(f"[DirectorConnector] Error sending event: {e}")

def send_bot_reply(reply_text, prompt_text="", is_censored=False):
    """Sends a bot reply to the Director Engine for UI display."""
    if not sio.connected:
        return

    payload = {
        "reply": reply_text,
        "prompt": prompt_text,
        "is_censored": is_censored
    }
    
    try:
        sio.emit("bot_reply", payload)
    except Exception as e:
        print(f"[DirectorConnector] Error sending bot reply: {e}")

# --- NEW: Speech State Notifications ---
def notify_speech_started():
    """
    Notify Director that Nami has started speaking.
    This prevents Director from sending new interjections while TTS is playing.
    """
    # Try Socket.IO first
    if sio.connected:
        try:
            sio.emit("speech_started", {})
            print("[DirectorConnector] 🔇 Notified Director: speech_started")
            return
        except Exception as e:
            print(f"[DirectorConnector] Socket emit failed, trying HTTP: {e}")
    
    # Fallback to HTTP
    try:
        with httpx.Client(timeout=1.0) as client:
            client.post(f"{DIRECTOR_URL}/speech_started")
            print("[DirectorConnector] 🔇 Notified Director (HTTP): speech_started")
    except Exception as e:
        print(f"[DirectorConnector] Failed to notify speech_started: {e}")

def notify_speech_finished():
    """
    Notify Director that Nami has finished speaking.
    This allows Director to resume sending interjections.
    """
    # Try Socket.IO first
    if sio.connected:
        try:
            sio.emit("speech_finished", {})
            print("[DirectorConnector] 🔊 Notified Director: speech_finished")
            return
        except Exception as e:
            print(f"[DirectorConnector] Socket emit failed, trying HTTP: {e}")
    
    # Fallback to HTTP
    try:
        with httpx.Client(timeout=1.0) as client:
            client.post(f"{DIRECTOR_URL}/speech_finished")
            print("[DirectorConnector] 🔊 Notified Director (HTTP): speech_finished")
    except Exception as e:
        print(f"[DirectorConnector] Failed to notify speech_finished: {e}")