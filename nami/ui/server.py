import socketio
import uvicorn
import threading
import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import os

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
app.mount("/static", StaticFiles(directory=ui_path, html=True), name="static")

# --- NEW: Serve audio effects ---
@app.get("/audio_effects/{filename}")
async def serve_audio_effect(filename: str):
    """Serve audio effect files for SSML audio tags"""
    # Construct path to audio effects directory
    audio_effects_path = Path(__file__).parent.parent / "audio_effects"
    file_path = audio_effects_path / filename
    
    # Security check - make sure the file exists and is in the right directory
    if not file_path.exists() or not file_path.is_file():
        print(f"❌ Audio effect not found: {file_path}")
        return {"error": "Audio effect not found"}
    
    # Make sure the resolved path is actually within our audio_effects directory
    if not str(file_path.resolve()).startswith(str(audio_effects_path.resolve())):
        print(f"🚨 Security violation: Attempted to access {file_path}")
        return {"error": "Access denied"}
    
    print(f"🔊 Serving audio effect: {filename}")
    return FileResponse(
        file_path,
        media_type="audio/wav",
        headers={
            "Cache-Control": "public, max-age=3600",  # Cache for 1 hour
            "Access-Control-Allow-Origin": "*"  # Allow CORS for Azure TTS
        }
    )

# Mount the main static files directory to serve index.html at root
app.mount("/", StaticFiles(directory=ui_path, html=True), name="ui_static")

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

def emit_bot_reply(reply, prompt="", is_censored=False, censorship_reason=None, filtered_area=None):
    """Emit bot's replies from any thread with optional censorship flag."""
    global sio
    print(f"[UI EMIT] Attempting to send bot_reply to UI:")
    print(f"  Reply: {reply[:50]}...")
    print(f"  Prompt: {prompt[:50] if prompt else '(empty)'}...")
    print(f"  Is Censored: {is_censored}")
    print(f"  Reason: {censorship_reason}")
    print(f"  Filtered Area: {filtered_area}")
    
    data = {
        'reply': reply, 
        'prompt': prompt, 
        'is_censored': is_censored,
        'censorship_reason': censorship_reason,
        'filtered_area': filtered_area
    }
    print(f"[UI EMIT] Sending data: {data}")
    _emit_threadsafe('bot_reply', data)

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
    print(f"Audio effects will be served from: http://{UI_HOST}:{UI_PORT}/audio_effects/")
    
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

# --- NEW: Test function ---
def test_audio_effects_serving():
    """Test if audio effects directory is accessible"""
    audio_effects_path = Path(__file__).parent.parent / "audio_effects"
    print(f"Audio effects directory: {audio_effects_path}")
    
    if not audio_effects_path.exists():
        print("❌ Audio effects directory not found!")
        return False
    
    sound_files = ['airhorn.wav', 'bonk.wav', 'fart.wav']
    for sound_file in sound_files:
        file_path = audio_effects_path / sound_file
        if file_path.exists():
            print(f"✅ Found: {sound_file}")
        else:
            print(f"❌ Missing: {sound_file}")
    
    return True

if __name__ == "__main__":
    test_audio_effects_serving()