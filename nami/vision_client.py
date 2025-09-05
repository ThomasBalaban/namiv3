# nami/vision_client.py
import asyncio
import websockets
import json
import threading
from nami.input_systems.input_handlers import handle_vision_input

VISION_WEBSOCKET_URL = "ws://localhost:8001"

async def vision_client_listener():
    """Connects to the vision WebSocket and processes incoming messages."""
    while True:
        try:
            async with websockets.connect(VISION_WEBSOCKET_URL) as websocket:
                print("[VISION CLIENT]  WebSocket connected successfully!")
                while True:
                    message_str = await websocket.recv()
                    try:
                        # Assuming the WebSocket sends JSON data
                        data = json.loads(message_str)
                        
                        # Extract data - adjust keys if the format is different
                        analysis_text = data.get("text", "")
                        confidence = data.get("confidence", 0.7)
                        metadata = data.get("metadata", {})
                        
                        if analysis_text:
                            # Use the existing handler to process the vision input
                            handle_vision_input(analysis_text, confidence, metadata)
                            
                    except json.JSONDecodeError:
                        print(f"[VISION CLIENT] Received non-JSON message: {message_str}")
                    except Exception as e:
                        print(f"[VISION CLIENT] Error processing message: {e}")

        except (websockets.exceptions.ConnectionClosedError, ConnectionRefusedError) as e:
            print(f"[VISION CLIENT] WebSocket connection failed: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[VISION CLIENT] An unexpected error occurred: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)

def run_vision_client():
    """Runs the async listener in a new event loop."""
    asyncio.run(vision_client_listener())

def start_vision_client():
    """Starts the vision client in a background thread."""
    print("Starting WebSocket vision client...")
    client_thread = threading.Thread(target=run_vision_client, daemon=True)
    client_thread.start()
    print("Vision client thread started.")
    return client_thread