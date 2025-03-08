"""
Core Priority System for PeepingNami Bot

Contains the main PrioritySystem class and basic data structures.
"""

import time
import threading
import queue
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional, Any, Callable

# Define input source types
class InputSource(Enum):
    DIRECT_MICROPHONE = auto()  # Direct address via microphone
    TWITCH_MENTION = auto()     # Bot mentioned in Twitch chat
    AMBIENT_AUDIO = auto()      # Background audio detected
    VISUAL_CHANGE = auto()      # Significant visual change
    TWITCH_CHAT = auto()        # Regular Twitch chat (not mentioning bot)

# Define conversation states that affect thresholds
class ConversationState(Enum):
    IDLE = auto()               # No active conversation
    ENGAGED = auto()            # Active conversation in progress
    OBSERVING = auto()          # Watching content, less interactive
    BUSY = auto()               # High-intensity period (e.g., gaming)

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
        # Base thresholds for different states (can be tuned)
        self.thresholds = {
            ConversationState.IDLE: 0.5,       # Low threshold when idle
            ConversationState.ENGAGED: 0.7,     # Medium threshold when engaged
            ConversationState.OBSERVING: 0.8,   # High threshold when observing
            ConversationState.BUSY: 0.9         # Very high threshold when busy
        }
        
        # Base weights for different sources (can be tuned)
        self.source_weights = {
            InputSource.DIRECT_MICROPHONE: 0.8,  # High priority
            InputSource.TWITCH_MENTION: 0.7,     # High priority
            InputSource.AMBIENT_AUDIO: 0.3,      # Low priority
            InputSource.VISUAL_CHANGE: 0.4,      # Medium-low priority
            InputSource.TWITCH_CHAT: 0.2         # Low priority
        }
        
        # Current state
        self.current_state = ConversationState.IDLE
        self.last_response_time = 0
        self.recent_inputs = []  # Track recent inputs for context
        self.max_recent_inputs = 10
        
        # Input queue
        self.input_queue = queue.PriorityQueue()
        self.processing = False
        self.queue_lock = threading.Lock()
        
        # Hook for response callback
        self.response_callback = None
        
        # Start processing thread
        self.start_processing()
    
    def set_response_callback(self, callback: Callable[[InputItem], None]):
        """Set the callback function to handle responses"""
        self.response_callback = callback
    
    def start_processing(self):
        """Start the background thread to process inputs"""
        self.processing = True
        thread = threading.Thread(target=self._process_queue, daemon=True)
        thread.start()
    
    def stop_processing(self):
        """Stop the background processing thread"""
        self.processing = False
    
    def set_state(self, state: ConversationState):
        """Update the current conversation state"""
        self.current_state = state
        print(f"Conversation state changed to: {state.name}")
    
    def add_input(self, source: InputSource, text: str, metadata: Dict[str, Any] = None, raw_data: Any = None):
        """Add a new input to be evaluated"""
        if metadata is None:
            metadata = {}
            
        # Create input item
        item = InputItem(
            source=source,
            text=text,
            timestamp=time.time(),
            metadata=metadata,
            raw_data=raw_data
        )
        
        # Calculate initial score
        score = self._calculate_score(item)
        item.score = score
        
        # Add to recent inputs for context
        with self.queue_lock:
            self.recent_inputs.append(item)
            if len(self.recent_inputs) > self.max_recent_inputs:
                self.recent_inputs.pop(0)
        
        # Add to priority queue with a unique identifier to avoid comparing InputItems
        # Use timestamp to ensure uniqueness
        self.input_queue.put((-score, time.time(), item))
        print(f"Input added - Source: {source.name}, Score: {score:.2f}, Text: {text[:30]}...")
    
    def _calculate_score(self, item: InputItem) -> float:
        """Calculate priority score for an input"""
        from .priority_scoring import calculate_input_score
        return calculate_input_score(
            item, 
            self.source_weights, 
            self.recent_inputs,
            self.last_response_time
        )
    
    def _process_queue(self):
        """Background thread to process the input queue"""
        while self.processing:
            try:
                # Check if we have items to process
                if self.input_queue.empty():
                    time.sleep(0.1)
                    continue
                
                # Get current threshold based on state
                current_threshold = self.thresholds[self.current_state]
                
                # Get highest priority item
                _, _, item = self.input_queue.get(block=False)
                
                # Check if it meets threshold
                if item.score >= current_threshold:
                    print(f"Processing input - Score: {item.score:.2f}, Threshold: {current_threshold:.2f}")
                    
                    # Call response callback if set
                    if self.response_callback:
                        self.response_callback(item)
                        self.last_response_time = time.time()
                    else:
                        print("No response callback set, item would be processed")
                else:
                    print(f"Input below threshold - Score: {item.score:.2f}, Threshold: {current_threshold:.2f}")
                
                # Mark as done
                self.input_queue.task_done()
                
                # Don't process too quickly
                time.sleep(0.5)
                
            except queue.Empty:
                # No items in queue
                time.sleep(0.1)
            except Exception as e:
                print(f"Error in priority queue processing: {e}")
                time.sleep(1)  # Sleep to avoid tight error loops
    
    def empty_queue(self):
        """Clear all pending inputs"""
        with self.queue_lock:
            while not self.input_queue.empty():
                try:
                    self.input_queue.get(block=False)
                    self.input_queue.task_done()
                except:
                    pass