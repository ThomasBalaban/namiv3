import sounddevice as sd

def list_input_devices():
    print("Available input devices:\n")
    devices = sd.query_devices()
    for index, device in enumerate(devices):
        if device["max_input_channels"] > 0:
            print(f"ID: {index} | {device['name']}")
            print(f"  Channels: {device['max_input_channels']}")
            print(f"  Default Sample Rate: {device['default_samplerate']} Hz\n")

if __name__ == "__main__":
    try:
        list_input_devices()
    except Exception as e:
        print(f"Error: {e}\nIs sounddevice installed? Run 'pip install sounddevice'")