# nami/input_systems/priority_core.py

import time
import threading
import queue
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, Optional, Any, Callable
from ..bot_core import add_message  # ADDED: To add context directly to memory

# Define input source types
class InputSource(Enum):
    DIRECT_MICROPHONE = auto()
    TWITCH_MENTION = auto()
    AMBIENT_AUDIO = auto()
    VISUAL_CHANGE = auto()
    TWITCH_CHAT = auto()

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
            InputSource.TWITCH_CHAT: 0.2
        }
        
        self.current_state = ConversationState.IDLE
        self.last_response_time = 0
        self.recent_inputs = []
        self.max_recent_inputs = 10
        
        self.input_queue = queue.PriorityQueue()
        self.processing = False
        self.queue_lock = threading.Lock()
        
        self.response_callback = None

        self.last_ambient_response_time = 0
        self.ambient_cooldown_seconds = 20
        
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
        
        # --- MODIFIED: Add ambient events to context immediately ---
        is_ambient = item.source in [InputSource.AMBIENT_AUDIO, InputSource.VISUAL_CHANGE]
        if is_ambient:
            # Format the text the way the AI expects to see it and add to memory.
            # This ensures the bot is "aware" even if it doesn't reply.
            if item.source == InputSource.AMBIENT_AUDIO:
                context_text = f"You're overhearing: {item.text}"
            else: # VISUAL_CHANGE
                context_text = f"You notice: {item.text}"
            
            add_message("user", context_text)
            print(f"Context added: {source.name} - {text[:30]}...")
        # --- END MODIFICATION ---

        score = self._calculate_score(item)
        item.score = score
        
        with self.queue_lock:
            self.recent_inputs.append(item)
            if len(self.recent_inputs) > self.max_recent_inputs:
                self.recent_inputs.pop(0)
        
        self.input_queue.put((-score, time.time(), item))
        print(f"Input added - Source: {source.name}, Score: {score:.2f}, Text: {text[:30]}...")
    
    def _calculate_score(self, item: InputItem) -> float:
        from .priority_scoring import calculate_input_score
        return calculate_input_score(item, self.source_weights, self.recent_inputs, self.last_response_time)
    
    def _process_queue(self):
        while self.processing:
            try:
                if self.input_queue.empty():
                    time.sleep(0.1)
                    continue
                
                current_threshold = self.thresholds[self.current_state]
                
                _, _, item = self.input_queue.get(block=False)
                
                is_ambient = item.source in [InputSource.AMBIENT_AUDIO, InputSource.VISUAL_CHANGE]
                time_since_last_ambient = time.time() - self.last_ambient_response_time

                if is_ambient and time_since_last_ambient < self.ambient_cooldown_seconds:
                    print(f"Input below threshold (ambient cooldown) - Score: {item.score:.2f}")
                    self.input_queue.task_done()
                    continue
                
                if item.score >= current_threshold:
                    print(f"Processing input - Score: {item.score:.2f}, Threshold: {current_threshold:.2f}")
                    
                    if self.response_callback:
                        self.response_callback(item)
                        self.last_response_time = time.time()
                        if is_ambient:
                            self.last_ambient_response_time = time.time()
                else:
                    print(f"Input below threshold - Score: {item.score:.2f}, Threshold: {current_threshold:.2f}")
                
                self.input_queue.task_done()
                
                time.sleep(0.5)
                
            except queue.Empty:
                time.sleep(0.1)
            except Exception as e:
                print(f"Error in priority queue processing: {e}")
                time.sleep(1)
    
    def empty_queue(self):
        with self.queue_lock:
            while not self.input_queue.empty():
                try:
                    self.input_queue.get(block=False)
                    self.input_queue.task_done()
                except:
                    pass