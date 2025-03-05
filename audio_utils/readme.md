# Transcription System with MongoDB and RabbitMQ

This document explains how to set up and use the enhanced transcription system that uses MongoDB for storage and RabbitMQ for message queuing.

## Prerequisites

Before you can run the system, you need to install the following:

1. **MongoDB**
   - [Download and install MongoDB Community Edition](https://www.mongodb.com/try/download/community)
   - Create a directory for MongoDB data: `mkdir -p data/db`

2. **RabbitMQ**
   - [Download and install RabbitMQ](https://www.rabbitmq.com/download.html)
   - RabbitMQ requires Erlang, which will be installed as a dependency

3. **Python Dependencies**
   ```bash
   pip install pymongo pika
   ```

## Project Structure

Ensure your project has the following structure:

```
audio_utils/
    __init__.py
    classifier.py       # Your existing speech/music classifier
    microphone.py       # Modified microphone transcription
    transcriber.py      # Modified desktop transcription
    transcript_manager.py  # New file for transcript management
audio_config.py         # Your existing configuration
hearing.py              # Modified main script
requirements.txt        # Updated with new dependencies
```

## Running the System

1. **Start MongoDB**
   ```bash
   mongod --dbpath data/db
   ```

2. **Start RabbitMQ**
   ```bash
   # On most systems, RabbitMQ runs as a service after installation
   rabbitmq-server
   ```

3. **Run the transcription system**
   ```bash
   python hearing.py
   ```

### Command-line Options

The system supports several command-line options:

```
python hearing.py --help
```

Key options:
- `--debug`: Enable debug mode for more verbose output
- `--keep-files`: Keep audio files after processing
- `--no-mongo`: Disable MongoDB storage
- `--no-mq`: Disable message queue
- `--mongo-uri`: MongoDB connection URI (default: "mongodb://localhost:27017/")
- `--rabbitmq-uri`: RabbitMQ connection URI (default: "amqp://guest:guest@localhost:5672/")
- `--db-name`: Database name (default: "transcriptions")
- `--queue-name`: Message queue name (default: "transcriptions")

## Using the Transcript Data

The transcript data is stored in MongoDB and can be accessed in several ways:

1. **MongoDB Compass**: A GUI tool for exploring MongoDB data
2. **MongoDB Shell**: Command-line tool for querying the database
3. **Programmatically**: Use the TranscriptManager class:

```python
from audio_utils.transcript_manager import TranscriptManager

# Initialize the manager
manager = TranscriptManager()

# Get recent transcripts
recent = manager.get_recent_transcripts(limit=10)
for transcript in recent:
    print(f"{transcript['source']}: {transcript['text']}")

# Search for specific content
results = manager.search_transcripts("search term")
for result in results:
    print(f"Match: {result['text']}")
```

## Integrating with AI Systems

To integrate with an AI system, modify the `process_transcript` function in `hearing.py`:

```python
def process_transcript(message):
    """
    Process incoming transcripts from the message queue.
    """
    source = message.get("source", "unknown")
    text = message.get("text", "")
    
    # Send to your AI system
    response = your_ai_system.process(text, source)
    
    # Handle the AI response
    print(f"AI Response: {response}")
```

Your AI system will now receive real-time transcripts from both desktop audio and microphone input through a single, consistent interface.

## Troubleshooting

If you encounter issues:

1. Check that MongoDB and RabbitMQ are running
2. Verify connection URIs if using non-default configurations
3. Enable debug mode with `--debug` for more detailed output
4. Check log files for MongoDB and RabbitMQ for service-specific errors