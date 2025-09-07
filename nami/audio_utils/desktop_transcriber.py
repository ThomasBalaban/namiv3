import sounddevice as sd
import vosk
import json
import queue
import sys
import time

# --- Configuration ---
# This should point to your Vosk model folder.
# --- FIX: Changed to point to the larger, more accurate lgraph model ---
VOSK_MODEL_PATH = "local_models/vosk-model-en-us-0.42-gigaspeech"
SAMPLE_RATE = 16000
BLOCK_SIZE = 4000  # How often to process audio (in samples)

# --- How often to force a transcription result, in seconds ---
FORCE_RESULT_TIMEOUT = 4.0

# A queue to hold audio data between the callback and the main processing loop
audio_queue = queue.Queue()

def audio_callback(indata, frames, time, status):
    """This is called by sounddevice for each new audio chunk."""
    if status:
        print(f"[VOSK STATUS] {status}", file=sys.stderr)
    audio_queue.put(bytes(indata))

def process_and_print_result(recognizer, is_final_result=False):
    """
    Helper function to process a Vosk result (either partial or final) and print it.
    Using FinalResult() will reset the recognizer for a new utterance.
    """
    if is_final_result:
        result_str = recognizer.FinalResult()
    else:
        result_str = recognizer.Result()

    result = json.loads(result_str)
    text = result.get('text', '').strip()

    if text:
        confidence = 0.7  # Default confidence
        words = result.get('result', [])
        if words:
            conf_sum = sum(w.get('conf', 0) for w in words)
            confidence = conf_sum / len(words) if words else 0.7

        # Print the final transcription for the hearing.py script to capture
        print(f"[SPEECH {confidence:.2f}] {text}")
        sys.stdout.flush()
        return True
    return False

def run_desktop_transcriber():
    """
    Initializes Vosk and starts transcribing the default audio output device.
    """
    try:
        print(f"🎙️ Initializing VOSK for Desktop Audio with model: {VOSK_MODEL_PATH}...")
        model = vosk.Model(VOSK_MODEL_PATH)
        recognizer = vosk.KaldiRecognizer(model, SAMPLE_RATE)
        recognizer.SetWords(True)
        print("✅ VOSK model loaded successfully.")

    except Exception as e:
        print(f"❌ Failed to initialize VOSK model. Make sure the path '{VOSK_MODEL_PATH}' is correct.")
        print(f"Error: {e}")
        return

    try:
        with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE, device=None,
                               dtype='int16', channels=1, callback=audio_callback):

            print("🎧 VOSK is now listening to desktop audio...")
            last_result_time = time.time()

            while True:
                try:
                    # Use a timeout so we can check for silence
                    data = audio_queue.get(timeout=1.0)

                    # Feed audio to Vosk. If a natural pause is detected, it returns True.
                    if recognizer.AcceptWaveform(data):
                        if process_and_print_result(recognizer):
                            last_result_time = time.time()

                    # If it's been too long since the last result, force one.
                    elif time.time() - last_result_time > FORCE_RESULT_TIMEOUT:
                        if process_and_print_result(recognizer, is_final_result=True):
                            last_result_time = time.time()

                except queue.Empty:
                    # If the queue is empty, it means there's silence.
                    # This is a good time to flush any pending text.
                    if process_and_print_result(recognizer, is_final_result=True):
                         last_result_time = time.time()

    except Exception as e:
        print(f"❌ An error occurred with VOSK desktop transcription: {e}")

if __name__ == '__main__':
    run_desktop_transcriber()