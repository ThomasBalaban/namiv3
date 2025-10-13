import sys
import asyncio
import websockets
import json
import threading

# Global variables
hearing_websocket = None
hearing_thread = None

def _output_reader_thread(callback):
    """
    Connect to the audio_mon WebSocket server and process incoming transcriptions.
    """
    asyncio.run(_websocket_client(callback))

async def _websocket_client(callback):
    """
    WebSocket client that connects to the audio_mon server.
    """
    uri = "ws://localhost:8003"
    
    while True:
        try:
            print(f"[HEARING] Connecting to audio_mon server at {uri}...")
            async with websockets.connect(uri) as websocket:
                print("[HEARING] ✅ Connected to audio_mon server!")
                
                while True:
                    try:
                        # Receive message from audio_mon
                        message_str = await websocket.recv()
                        data = json.loads(message_str)
                        
                        # Extract the data
                        source = data.get('source', 'unknown')
                        text = data.get('text', '')
                        confidence = data.get('confidence', 0.0)
                        audio_type = data.get('audio_type', 'speech')
                        
                        if text:
                            # Format the output line based on source
                            if source == 'microphone':
                                line_str = f"[Microphone Input] {text}"
                            elif source == 'desktop':
                                line_str = f"[{audio_type.upper()} {confidence:.2f}] {text}"
                            else:
                                line_str = f"[{source}] {text}"
                            
                            # Pass to the callback
                            if callback:
                                try:
                                    callback(line_str)
                                except Exception as e:
                                    print(f"[HEARING] Error in callback: {e}")
                                    
                    except websockets.exceptions.ConnectionClosed:
                        print("[HEARING] Connection closed by server")
                        break
                    except json.JSONDecodeError as e:
                        print(f"[HEARING] JSON decode error: {e}")
                    except Exception as e:
                        print(f"[HEARING] Error processing message: {e}")
                        
        except ConnectionRefusedError:
            print("[HEARING] ❌ Could not connect to audio_mon server")
            print("[HEARING] Make sure audio_mon is running: cd audio_mon && python main.py")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[HEARING] Connection error: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)

def start_hearing_system(callback=None):
    """
    Start the hearing system by connecting to the audio_mon WebSocket server.
    
    Args:
        callback: Function to call with each transcription line
    """
    global hearing_thread
    
    print("[HEARING] Starting hearing system (WebSocket client mode)...")
    print("[HEARING] This will connect to the audio_mon app on ws://localhost:8003")
    
    hearing_thread = threading.Thread(
        target=_output_reader_thread,
        args=(callback,),
        daemon=True,
        name="HearingWebSocketClient"
    )
    hearing_thread.start()
    
    print("[HEARING] Hearing system thread started")
    return True

def stop_hearing_system():
    """Stop the hearing system"""
    global hearing_thread
    
    print("[HEARING] Stopping hearing system...")
    # The thread is daemon, so it will stop when the main program exits
    hearing_thread = None
    print("[HEARING] Hearing system stopped")