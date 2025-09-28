import asyncio
import websockets
import json
import threading
from nami.input_systems.input_handlers import handle_websocket_audio_input

AUDIO_WEBSOCKET_URL = "ws://localhost:8003"

async def audio_client_listener():
    """Listens for audio data from the `audio_mon` app and forwards it to the main bot."""
    while True:
        try:
            async with websockets.connect(AUDIO_WEBSOCKET_URL) as websocket:
                print("[AUDIO CLIENT] WebSocket connected successfully!")
                while True:
                    message_str = await websocket.recv()
                    try:
                        data = json.loads(message_str)
                        if data:
                            handle_websocket_audio_input(data)
                    except json.JSONDecodeError:
                        print(f"[AUDIO CLIENT] Received non-JSON message: {message_str}")
                    except Exception as e:
                        print(f"[AUDIO CLIENT] Error processing message: {e}")

        except (websockets.exceptions.ConnectionClosedError, ConnectionRefusedError) as e:
            print(f"[AUDIO CLIENT] WebSocket connection failed: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[AUDIO CLIENT] An unexpected error occurred: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)

def run_audio_client():
    """Starts the asyncio event loop for the WebSocket client."""
    asyncio.run(audio_client_listener())

def start_audio_client():
    """Starts the WebSocket client in a non-blocking background thread."""
    print("Starting WebSocket audio client...")
    client_thread = threading.Thread(target=run_audio_client, daemon=True)
    client_thread.start()
    print("Audio client thread started.")
    return client_thread