import time
import threading
from queue import PriorityQueue, Empty
from dataclasses import dataclass
from typing import Any, Callable, Optional, Dict

@dataclass
class FunnelItem:
    """Represents an item in the input funnel"""
    priority: float
    timestamp: float
    content: str
    source_info: dict
    response_callback: Optional[Callable] = None

class InputFunnel:
    def __init__(self, bot_callback: Callable[[str], str], 
                 response_handler: Optional[Callable[[str, Dict[str, Any]], None]] = None,
                 min_prompt_interval: float = 2.0):
        """Initialize the input funnel
        
        Args:
            bot_callback: Function to call to get bot responses (e.g., ask_question)
            response_handler: Function to handle responses (takes response text and source_info)
            min_prompt_interval: Minimum time between prompts in seconds
        """
        self.bot_callback = bot_callback
        self.response_handler = response_handler
        self.input_queue = PriorityQueue()
        self.processing = False
        self.shutdown_requested = False
        self.processing_lock = threading.Lock()
        self.last_prompt_time = 0
        self.min_prompt_interval = min_prompt_interval
        self.processing_thread = None
        
        print(f"InputFunnel initialized with {min_prompt_interval}s interval")
        
    def add_input(self, content, priority=0.5, source_info=None, response_callback=None):
        """Add an input to the funnel
        
        Args:
            content: The text content to send to the bot
            priority: Priority value (lower number = higher priority)
            source_info: Dictionary with source information
            response_callback: Optional callback for handling the response
        """
        if self.shutdown_requested:
            print("InputFunnel is shutting down, not accepting new inputs")
            return False
            
        if source_info is None:
            source_info = {}
            
        # Create funnel item
        item = FunnelItem(
            priority=priority,
            timestamp=time.time(),
            content=content,
            source_info=source_info,
            response_callback=response_callback
        )
        
        print(f"Added to funnel: {content[:50]}... (priority: {priority})")
        
        # Add to queue with priority and timestamp for uniqueness
        self.input_queue.put((priority, time.time(), item))
        
        # Start processing if not already running
        with self.processing_lock:
            if not self.processing and not self.shutdown_requested:
                self.processing = True
                self.processing_thread = threading.Thread(
                    target=self._process_queue, 
                    daemon=True
                )
                self.processing_thread.start()
                print("Started funnel processing thread")
                
        return True
            
    def _process_queue(self):
        """Process items in the queue at a controlled rate"""
        while not self.shutdown_requested:
            try:
                # Check if we have items to process
                try:
                    # Use a timeout so we can check shutdown_requested periodically
                    _, _, item = self.input_queue.get(timeout=0.5)
                except Empty:
                    # If queue is empty, check if we should stop
                    with self.processing_lock:
                        if self.input_queue.empty():
                            self.processing = False
                            print("Funnel processing thread stopping (queue empty)")
                            break
                    continue
                
                # Apply rate limiting
                time_since_last = time.time() - self.last_prompt_time
                if time_since_last < self.min_prompt_interval:
                    sleep_time = self.min_prompt_interval - time_since_last
                    # Sleep in small increments to check shutdown_requested
                    end_time = time.time() + sleep_time
                    while time.time() < end_time and not self.shutdown_requested:
                        time.sleep(0.1)
                    
                    # If shutdown was requested during sleep, exit
                    if self.shutdown_requested:
                        self.input_queue.task_done()
                        break
                
                # Process the item
                print(f"\nProcessing input via funnel: {item.content[:50]}...")
                
                try:
                    # Get response from bot
                    self.last_prompt_time = time.time()
                    if self.bot_callback and not self.shutdown_requested:
                        response = self.bot_callback(item.content)
                    else:
                        print("No bot callback configured or shutdown requested")
                        response = "No response (bot callback not configured or shutdown in progress)"
                    
                    # Handle the response
                    if not self.shutdown_requested:
                        self._handle_response(response, item)
                except Exception as e:
                    print(f"Error getting bot response: {e}")
                
                # Mark as done
                self.input_queue.task_done()
                
            except Exception as e:
                print(f"Error in funnel processing: {e}")
                time.sleep(0.1)  # Shorter sleep to check shutdown more frequently
        
        print("Funnel processing thread exited due to shutdown request")
        
    def _handle_response(self, response, item):
        """Handle a response from the bot"""
        if not response:
            print("Empty response from bot")
            return
            
        # Print the response
        print(f"\nBot response via funnel: {response[:100]}...")
        
        # Use the global response handler if provided
        if self.response_handler and not self.shutdown_requested:
            try:
                self.response_handler(response, item.source_info)
            except Exception as e:
                print(f"Error in response handler: {e}")
        
        # Use the item-specific response callback if provided
        if item.response_callback and not self.shutdown_requested:
            try:
                item.response_callback(response)
            except Exception as e:
                print(f"Error in response callback: {e}")
    
    def stop(self):
        """Stop the funnel processing"""
        print("InputFunnel shutdown requested")
        self.shutdown_requested = True
        
        # Wait for processing thread to exit
        if self.processing_thread and self.processing_thread.is_alive():
            print("Waiting for funnel processing thread to exit...")
            # Wait with timeout in case thread is stuck
            self.processing_thread.join(timeout=2.0)
            if self.processing_thread.is_alive():
                print("Funnel thread did not exit in time")
            else:
                print("Funnel thread exited successfully")
        
        with self.processing_lock:
            self.processing = False
        
        # Empty the queue to prevent memory leaks
        while not self.input_queue.empty():
            try:
                self.input_queue.get(block=False)
                self.input_queue.task_done()
            except Empty:
                break
            
        print("InputFunnel shutdown complete")
    
    def set_prompt_interval(self, interval: float):
        """Set the minimum interval between prompts"""
        if interval < 0.1:
            interval = 0.1
        self.min_prompt_interval = interval
        print(f"Prompt interval set to {interval} seconds")