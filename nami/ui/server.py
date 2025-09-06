import socketio
import uvicorn
import threading
import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# --- Configuration ---
UI_HOST = "0.0.0.0"
UI_PORT = 8002

# --- FastAPI and Socket.IO Setup ---
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
app = FastAPI()
# This mounts the socket.io server on top of the FastAPI app
app.mount('/socket.io', socketio.ASGIApp(sio))

# Mount the static files directory to serve index.html
ui_path = Path(__file__).parent.resolve()
app.mount("/", StaticFiles(directory=ui_path, html=True), name="static")


# --- Thread-Safe Event Emission ---
# This section provides a robust way to send events to the UI from any thread.

# Global variable to hold the UI server's event loop
ui_event_loop = None

def _emit_threadsafe(event, data):
    """
    A thread-safe function to schedule an emit call on the UI's event loop.
    """
    global ui_event_loop
    if ui_event_loop:
        try:
            # Schedule the coroutine to be executed on the UI server's event loop
            asyncio.run_coroutine_threadsafe(
                sio.emit(event, data),
                ui_event_loop
            )
        except Exception as e:
            # This might happen during shutdown
            print(f"UI Emit Error: Could not send event '{event}' to UI. Reason: {e}")
    else:
        print(f"UI Emit Warning: Event loop not ready. Dropped event '{event}'.")

def emit_log(level, message):
    """Emit a generic log message from any thread."""
    _emit_threadsafe('log_message', {'level': level, 'message': message})

def emit_vision_context(context):
    """Emit vision context updates from any thread."""
    _emit_threadsafe('vision_context', {'context': context})

def emit_spoken_word_context(context):
    """Emit spoken word context updates from any thread."""
    _emit_threadsafe('spoken_word_context', {'context': context})

def emit_audio_context(context):
    """Emit audio context updates from any thread."""
    _emit_threadsafe('audio_context', {'context': context})

def emit_twitch_message(username, message):
    """Emit incoming Twitch messages from any thread."""
    _emit_threadsafe('twitch_message', {'username': username, 'message': message})

def emit_bot_reply(reply):
    """Emit bot's replies from any thread."""
    _emit_threadsafe('bot_reply', {'reply': reply})


# --- Server Control ---
def run_server():
    """Run the Uvicorn server in a blocking manner."""
    global ui_event_loop
    
    # --- FIX: Create and set a new event loop for this background thread ---
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Get the current event loop for this thread (which we just created)
    ui_event_loop = asyncio.get_event_loop()
    
    print(f"Starting Nami UI server at http://{UI_HOST}:{UI_PORT}")
    
    # Disable Uvicorn's default logging to prevent crashes
    config = uvicorn.Config(app, host=UI_HOST, port=UI_PORT, log_config=None)
    server = uvicorn.Server(config)
    
    # Run the server on the event loop we captured
    ui_event_loop.run_until_complete(server.serve())


def start_ui_server():
    """Start the UI server in a non-blocking background thread."""
    server_thread = threading.Thread(target=run_server, daemon=True, name="UI Server")
    server_thread.start()
    print("UI server thread started.")