#!/bin/bash
# Install Ollama on macOS

set -e

if command -v ollama &>/dev/null; then
    echo "Ollama is already installed at $(which ollama)"
    exit 0
fi

if command -v brew &>/dev/null; then
    echo "Installing Ollama via Homebrew..."
    brew install --cask ollama
    echo "Ollama installed successfully."
    echo "Launch Ollama from Applications to start the server."
else
    echo "Downloading Ollama installer..."
    curl -fsSL https://ollama.com/install.sh | sh
    echo "Ollama installed successfully."
fi
