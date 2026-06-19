#!/bin/bash
# Install FFmpeg on macOS

set -e

if command -v ffmpeg &>/dev/null; then
    echo "FFmpeg is already installed at $(which ffmpeg)"
    exit 0
fi

if command -v brew &>/dev/null; then
    echo "Installing FFmpeg via Homebrew..."
    brew install ffmpeg
    echo "FFmpeg installed successfully."
else
    echo "Homebrew not found. Installing Homebrew first..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Add Homebrew to PATH for Apple Silicon
    if [ -f /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi

    echo "Installing FFmpeg via Homebrew..."
    brew install ffmpeg
    echo "FFmpeg installed successfully."
fi
