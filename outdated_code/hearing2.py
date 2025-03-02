import sys
import json
import sounddevice as sd
from vosk import Model, KaldiRecognizer

# Path to your downloaded Vosk model directory
MODEL_PATH = "local_models/vosk-model-en-us-0.42-gigaspeech"  # Update with your model path
SAMPLE_RATE = 16000

# Load the Vosk model
print("Loading Vosk model...")
model = Model(MODEL_PATH)
recognizer = KaldiRecognizer(model, SAMPLE_RATE)

def callback(indata, frames, time_info, status):
    """This callback is called for each audio block."""
    if status:
        print(status, file=sys.stderr)
    # Convert the incoming audio data to bytes.
    data = bytes(indata)
    if recognizer.AcceptWaveform(data):
        result = recognizer.Result()
        result_dict = json.loads(result)
        text = result_dict.get("text", "")
        if text:
            print("Final:", text)
    else:
        partial_result = recognizer.PartialResult()
        result_dict = json.loads(partial_result)
        partial_text = result_dict.get("partial", "")
        if partial_text:
            print("Partial:", partial_text, end="\r")

# Set up a raw audio input stream. Vosk expects int16 audio.
with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=8000,
                         device=None, dtype='int16', channels=1,
                         callback=callback):
    print("Listening... Press Ctrl+C to stop.")
    try:
        while True:
            sd.sleep(1000)
    except KeyboardInterrupt:
        print("\nStopped.")
