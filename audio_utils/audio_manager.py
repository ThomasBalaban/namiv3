import json
import time
import datetime
from typing import Dict, Any, Optional
from pymongo import MongoClient
import pika
import threading

class TranscriptManager:
    """
    Manages transcription data flow between transcription sources,
    message queue, and database storage.
    """
    def __init__(self, mongodb_uri="mongodb://localhost:27017/", 
                 rabbitmq_uri="amqp://guest:guest@localhost:5672/",
                 db_name="transcriptions",
                 collection_name="transcripts",
                 queue_name="transcriptions",
                 debug=False):
        
        self.debug = debug
        self.queue_name = queue_name
        
        # Initialize MongoDB connection
        try:
            self.mongo_client = MongoClient(mongodb_uri)
            self.db = self.mongo_client[db_name]
            self.collection = self.db[collection_name]
            
            # Create indices for efficient querying
            self.collection.create_index([("text", "text")])  # For text search
            self.collection.create_index("timestamp")  # For time-based queries
            self.collection.create_index("source")  # For filtering by source
            
            if self.debug:
                print(f"Connected to MongoDB: {db_name}.{collection_name}")
        except Exception as e:
            print(f"MongoDB connection error: {e}")
            raise
        
        # Initialize RabbitMQ connection
        try:
            self.connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_uri))
            self.channel = self.connection.channel()
            
            # Declare queue with persistence
            self.channel.queue_declare(queue=queue_name, durable=True)
            
            if self.debug:
                print(f"Connected to RabbitMQ queue: {queue_name}")
        except Exception as e:
            print(f"RabbitMQ connection error: {e}")
            raise
            
        # Start consumer thread if requested
        self.consumer_thread = None
        self.stop_event = threading.Event()
    
    def publish_transcript(self, source: str, text: str, 
                         timestamp: Optional[str] = None, 
                         metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Publish a transcript to the message queue and store in MongoDB.
        
        Args:
            source: Source of the transcript (e.g., "desktop", "microphone")
            text: The transcribed text
            timestamp: ISO format timestamp (if None, current time is used)
            metadata: Additional metadata to store with the transcript
        """
        if not text.strip():
            return  # Skip empty transcripts
            
        # Create timestamp if not provided
        if timestamp is None:
            timestamp = datetime.datetime.utcnow().isoformat()
            
        # Create the message
        message = {
            "source": source,
            "text": text,
            "timestamp": timestamp,
            "metadata": metadata or {}
        }
        
        # Send to message queue
        try:
            self.channel.basic_publish(
                exchange='',
                routing_key=self.queue_name,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Make message persistent
                )
            )
            
            if self.debug:
                print(f"Published to queue: {source} - {text[:30]}...")
        except Exception as e:
            print(f"Failed to publish to RabbitMQ: {e}")
        
        # Store in MongoDB
        try:
            self.collection.insert_one(message)
            
            if self.debug:
                print(f"Stored in MongoDB: {source} - {text[:30]}...")
        except Exception as e:
            print(f"Failed to store in MongoDB: {e}")
    
    def start_consumer(self, callback):
        """
        Start a consumer that processes messages from the queue.
        
        Args:
            callback: Function to call for each message. Should accept a dict parameter.
        """
        def _consumer_thread():
            def _on_message(ch, method, properties, body):
                try:
                    message = json.loads(body)
                    callback(message)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:
                    print(f"Error processing message: {e}")
                    # Negative acknowledge to requeue the message
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                    
                # Check if we should stop
                if self.stop_event.is_set():
                    ch.stop_consuming()
            
            # Set up consumer
            self.channel.basic_qos(prefetch_count=1)
            self.channel.basic_consume(
                queue=self.queue_name,
                on_message_callback=_on_message
            )
            
            if self.debug:
                print(f"Starting consumer on queue: {self.queue_name}")
                
            # Start consuming
            try:
                self.channel.start_consuming()
            except Exception as e:
                if not self.stop_event.is_set():
                    print(f"Consumer error: {e}")
                
            if self.debug:
                print("Consumer stopped")
        
        # Start the consumer thread
        self.consumer_thread = threading.Thread(target=_consumer_thread)
        self.consumer_thread.daemon = True
        self.consumer_thread.start()
    
    def stop_consumer(self):
        """Stop the consumer thread"""
        if self.consumer_thread and self.consumer_thread.is_alive():
            self.stop_event.set()
            
            # Close the connection to trigger the consumer to stop
            try:
                self.connection.close()
            except:
                pass
                
            # Wait for thread to terminate
            self.consumer_thread.join(timeout=2.0)
            
            if self.debug:
                print("Consumer stopped")
    
    def get_recent_transcripts(self, limit=10, source=None):
        """
        Get recent transcripts from MongoDB.
        
        Args:
            limit: Maximum number of transcripts to return
            source: Filter by source (e.g., "desktop", "microphone")
            
        Returns:
            List of transcript documents
        """
        query = {}
        if source:
            query["source"] = source
            
        return list(self.collection.find(
            query, 
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit))
    
    def search_transcripts(self, query_text, limit=10):
        """
        Search transcripts by text content.
        
        Args:
            query_text: Text to search for
            limit: Maximum number of results to return
            
        Returns:
            List of matching transcript documents
        """
        return list(self.collection.find(
            {"$text": {"$search": query_text}},
            {"score": {"$meta": "textScore"}, "_id": 0}
        ).sort([("score", {"$meta": "textScore"})]).limit(limit))
    
    def close(self):
        """Close all connections"""
        self.stop_consumer()
        
        try:
            if hasattr(self, 'connection') and self.connection.is_open:
                self.connection.close()
        except:
            pass
            
        try:
            if hasattr(self, 'mongo_client'):
                self.mongo_client.close()
        except:
            pass