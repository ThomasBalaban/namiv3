Step 1: Export from Ollama
# Create a directory for the extracted model
mkdir mistral-nemo-extracted

# Export the model from Ollama
# This creates a Modelfile and extracts the weights
ollama show mistral-nemo:latest --modelfile > mistral-nemo-extracted/Modelfile

Step 2: Get the model files
The tricky part is Ollama stores models in a specific format. Let's try a different approach - use an open equivalent:

# Copy the model blob to our working directory
cp "/Users/thomasbalaban/.ollama/models/blobs/sha256-b559938ab7a0392fc9ea9675b82280f2a15669ec3e0e0fc491c9cb0a7681cf94" ./mistral-nemo-extracted/model.bin

# Check the file size to make sure it copied
ls -lh mistral-nemo-extracted/

python -c "from mlx_lm import load; model, tokenizer = load('mistralai/Mistral-Nemo-Instruct-2407'); print('Model loaded successfully!')"

# test to see if its working 
python -c "from mlx_lm import load; model, tokenizer = load('mistralai/Mistral-Nemo-Instruct-2407'); print(f'Model loaded! Vocab size: {tokenizer.vocab_size}')"