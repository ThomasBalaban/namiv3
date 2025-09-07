import threading
import time
import signal
import sys

# Import the main function from each of our new self-contained transcribers
from .desktop_transcriber import run_desktop_transcriber
from .microphone import transcribe_microphone, stop_event as mic_stop_event

def main():
    print("🎙️ Initializing Hybrid Audio Transcription System (Vosk + Whisper)...")

    # --- Create a thread for the VOSK Desktop Transcriber ---
    desktop_thread = threading.Thread(
        target=run_desktop_transcriber,
        daemon=True,
        name="VoskDesktopThread"
    )

    # --- Create a thread for the Whisper Microphone Transcriber ---
    mic_thread = threading.Thread(
        target=transcribe_microphone,
        daemon=True,
        name="WhisperMicThread"
    )

    # --- Start both threads ---
    desktop_thread.start()
    time.sleep(1) # Give it a second to initialize before starting the next one
    mic_thread.start()

    print("✅ Both transcription systems are running in the background.")
    print("Press Ctrl+C to stop.")

    # --- Graceful Shutdown Logic ---
    def shutdown(sig, frame):
        print("\n🛑 Shutting down all systems...")
        # Signal the microphone thread to stop its loops
        mic_stop_event.set()
        # The desktop thread is a daemon and will exit when the main script exits.
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Keep the main thread alive to wait for the shutdown signal
    while desktop_thread.is_alive() and mic_thread.is_alive():
        time.sleep(1)

if __name__ == "__main__":
    main()