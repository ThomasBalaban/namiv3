import time
import threading
import queue
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, Optional, Any, Callable
# --- MODIFIED: Import from the new context manager ---
from ..context import update_vision_context, update_spoken_word_context, update_audio_context, update_twitch_chat_context

# Define input source types
class InputSource(Enum):
    DIRECT_MICROPHONE = auto()
    TWITCH_MENTION = auto()
    AMBIENT_AUDIO = auto()
    VISUAL_CHANGE = auto()
    TWITCH_CHAT = auto()
    MICROPHONE = auto()


# Define conversation states that affect thresholds
class ConversationState(Enum):
    IDLE = auto()
    ENGAGED = auto()
    OBSERVING = auto()
    BUSY = auto()

@dataclass
class InputItem:
    """Represents a single input with metadata for priority calculation"""
    source: InputSource
    text: str
    timestamp: float
    metadata: Dict[str, Any]
    raw_data: Any = None
    score: Optional[float] = None

class PrioritySystem:
    def __init__(self):
        self.thresholds = {
            ConversationState.IDLE: 0.5,
            ConversationState.ENGAGED: 0.7,
            ConversationState.OBSERVING: 0.8,
            ConversationState.BUSY: 0.9
        }
        
        self.source_weights = {
            InputSource.DIRECT_MICROPHONE: 0.8,
            InputSource.TWITCH_MENTION: 0.7,
            InputSource.AMBIENT_AUDIO: 0.3,
            InputSource.VISUAL_CHANGE: 0.4,
            InputSource.TWITCH_CHAT: 0.2,
            InputSource.MICROPHONE: 0.5
        }
        
        self.current_state = ConversationState.IDLE
        self.last_response_time = 0
        self.recent_inputs = []
        self.max_recent_inputs = 10
        
        self.input_queue = queue.PriorityQueue()
        self.processing = False
        self.queue_lock = threading.Lock()
        
        self.response_callback = None
        self.start_processing()
    
    def set_response_callback(self, callback: Callable[[InputItem], None]):
        self.response_callback = callback
    
    def start_processing(self):
        self.processing = True
        thread = threading.Thread(target=self._process_queue, daemon=True)
        thread.start()
    
    def stop_processing(self):
        self.processing = False
    
    def set_state(self, state: ConversationState):
        self.current_state = state
        print(f"Conversation state changed to: {state.name}")
    
    def add_input(self, source: InputSource, text: str, metadata: Dict[str, Any] = None, raw_data: Any = None):
        if metadata is None: metadata = {}
            
        item = InputItem(source=source, text=text, timestamp=time.time(), metadata=metadata, raw_data=raw_data)
        
        # --- Route inputs to their respective context updaters ---
        if item.source == InputSource.DIRECT_MICROPHONE or item.source == InputSource.MICROPHONE:
            update_spoken_word_context(item.text)
            print(f"Context updated: {source.name} - {text[:30]}...")
        elif item.source == InputSource.AMBIENT_AUDIO:
            update_audio_context(item.text)
            print(f"Context updated: {source.name} - {text[:30]}...")
        elif item.source == InputSource.VISUAL_CHANGE:
            update_vision_context(item.text)
            print(f"Context updated: {source.name} - {text[:30]}...")
        # --- FIX: Added TWITCH_MENTION to this condition ---
        elif item.source == InputSource.TWITCH_CHAT or item.source == InputSource.TWITCH_MENTION:
            username = item.metadata.get('username', 'Someone')
            update_twitch_chat_context(username, item.text)
            print(f"Twitch context updated: {username}: {text[:30]}...")
        
        score = self._calculate_score(item)
        item.score = score
        
        with self.queue_lock:
            self.recent_inputs.append(item)
            if len(self.recent_inputs) > self.max_recent_inputs:
                self.recent_inputs.pop(0)
        
        # Only queue direct interactions for a potential response.
        # General chat will now only serve as context.
        if item.source in [InputSource.DIRECT_MICROPHONE, InputSource.TWITCH_MENTION]:
             self.input_queue.put((-score, time.time(), item))
        else:
            print(f"Input logged (context only) - Source: {source.name}, Text: {text[:30]}...")
    
    def _calculate_score(self, item: InputItem) -> float:
        from .priority_scoring import calculate_input_score
        return calculate_input_score(item, self.source_weights, self.recent_inputs, self.last_response_time)
    
    def _process_queue(self):
        """Processes DIRECT inputs only. Ambient inputs are now context-only."""
        while self.processing:
            try:
                if self.input_queue.empty():
                    time.sleep(0.1)
                    continue
                
                current_threshold = self.thresholds[self.current_state]
                _, _, item = self.input_queue.get(block=False)
                
                if item.score >= current_threshold:
                    if self.response_callback:
                        self.response_callback(item)
                        self.last_response_time = time.time()
                
                self.input_queue.task_done()
                # --- MODIFIED: Reduced sleep time for faster queue processing ---
                time.sleep(0.1)
                
            except queue.Empty:
                time.sleep(0.1)
            except Exception as e:
                print(f"Error in priority queue processing: {e}")
                time.sleep(1)