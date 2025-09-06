import asyncio
import websockets
import json
import threading
from nami.input_systems.input_handlers import handle_vision_input
# --- ADDED: Import UI emitter ---
from nami.ui.server import emit_vision_context

VISION_WEBSOCKET_URL = "ws://localhost:8001"

async def vision_client_listener():
    while True:
        try:
            async with websockets.connect(VISION_WEBSOCKET_URL) as websocket:
                print("[VISION CLIENT]  WebSocket connected successfully!")
                while True:
                    message_str = await websocket.recv()
                    try:
                        data = json.loads(message_str)
                        
                        # --- FIX: Look for the 'content' key instead of 'text' ---
                        analysis_text = data.get("content", "")
                        
                        confidence = data.get("confidence", 0.7)
                        metadata = data.get("metadata", {})
                        
                        if analysis_text:
                            # --- ADDED: Send context to UI ---
                            emit_vision_context(analysis_text)
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
    asyncio.run(vision_client_listener())

def start_vision_client():
    print("Starting WebSocket vision client...")
    client_thread = threading.Thread(target=run_vision_client, daemon=True)
    client_thread.start()
    print("Vision client thread started.")
    return client_thread