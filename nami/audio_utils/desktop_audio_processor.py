import os
import time
import numpy as np
import soundfile as sf
import re
from scipy import signal

class AudioProcessor:
    def __init__(self, transcriber):
        self.transcriber = transcriber
        self.desktop_audio_buffer = np.array([], dtype=np.float32)

    def desktop_audio_callback(self, indata, frames, timestamp, status):
        """Callback for desktop audio. Puts chunks on the desktop queue."""
        try:
            from nami.config import FS, CHUNK_DURATION, OVERLAP
        except ImportError:
            FS, CHUNK_DURATION, OVERLAP = 16000, 3, 0.5

        if self.transcriber.stop_event.is_set(): return
        new_audio = np.squeeze(indata).astype(np.float32)
        self.desktop_audio_buffer = np.concatenate([self.desktop_audio_buffer, new_audio])

        while len(self.desktop_audio_buffer) >= FS * CHUNK_DURATION:
            chunk = self.desktop_audio_buffer[:FS*CHUNK_DURATION].copy()
            self.desktop_audio_buffer = self.desktop_audio_buffer[int(FS*(CHUNK_DURATION-OVERLAP)):]
            self.transcriber.desktop_audio_queue.put(chunk)

    def _transcribe_chunk(self, chunk):
        """A common transcription function used by both mic and desktop processors."""
        # This is a simplified version of your original transcription logic
        whisper_input = chunk.astype(np.float32)
        if whisper_input.size < 1000: # Ignore very short chunks
             return ""
        
        params = {"beam_size": 1, "language": "en"}
        segments, info = self.transcriber.model.transcribe(whisper_input, **params)
        return "".join(segment.text for segment in segments).strip()

    def process_mic_chunk(self, chunk):
        """Processes a chunk of audio from the microphone."""
        try:
            text = self._transcribe_chunk(chunk)
            if text:
                metadata = {"latency": time.time() - self.transcriber.last_processed_time}
                self.transcriber.result_queue.put((text, None, "microphone", metadata))
        except Exception as e:
            print(f"Mic processing error: {e}")

    def process_desktop_chunk(self, chunk):
        """Processes a chunk of audio from the desktop."""
        try:
            # Perform speech/music classification only for desktop audio
            if self.transcriber.auto_detect:
                audio_type, confidence = self.transcriber.classifier.classify(chunk)
            else:
                audio_type, confidence = self.transcriber.classifier.current_type, 0.8
            
            if confidence < 0.4: return # Skip low-confidence chunks

            filename = self._save_audio(chunk, "desktop")
            text = self._transcribe_chunk(chunk)

            if text:
                metadata = {
                    "audio_type": audio_type,
                    "confidence": float(confidence),
                    "latency": time.time() - self.transcriber.last_processed_time
                }
                self.transcriber.result_queue.put((text, filename, "desktop", metadata))
        except Exception as e:
            print(f"Desktop processing error: {e}")

    def _save_audio(self, chunk, prefix):
        """Saves audio chunk to file and returns filename."""
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = os.path.join(self.transcriber.SAVE_DIR, f"{prefix}_{timestamp}.wav")
        sf.write(filename, chunk, self.transcriber.FS, subtype='PCM_16')
        self.transcriber.saved_files.append(filename)
        return filename