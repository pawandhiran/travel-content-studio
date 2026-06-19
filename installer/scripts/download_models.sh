#!/bin/bash
# Download the appropriate Ollama model based on system RAM

set -e

if ! command -v ollama &>/dev/null; then
    echo "Error: Ollama not found. Please install Ollama first."
    exit 1
fi

# Start Ollama server if not running
if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
    echo "Starting Ollama server..."
    ollama serve &>/dev/null &
    sleep 5
fi

# Determine model based on RAM
ram_bytes=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
ram_gb=$((ram_bytes / 1073741824))

if [ "$ram_gb" -ge 32 ]; then
    MODEL="qwen3:32b"
elif [ "$ram_gb" -ge 16 ]; then
    MODEL="qwen3:14b"
else
    MODEL="qwen3:8b"
fi

echo "System RAM: ${ram_gb}GB -> Downloading model: $MODEL"
echo "This may take 10-30 minutes depending on your internet connection..."

ollama pull "$MODEL"

if [ $? -eq 0 ]; then
    echo "Model $MODEL downloaded successfully."
else
    echo "Error: Failed to download model $MODEL"
    exit 1
fi
