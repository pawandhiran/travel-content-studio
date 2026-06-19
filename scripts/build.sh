#!/bin/bash
# Travel Content Studio -- Build Script
# Usage: ./scripts/build.sh [windows|macos|all]

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLATFORM="${1:-$(uname -s | tr '[:upper:]' '[:lower:]')}"

echo "Building Travel Content Studio for: $PLATFORM"

# Step 1: Build Python backend with PyInstaller
echo "=== Building Python backend ==="
cd "$PROJECT_ROOT/backend"
pip install pyinstaller
pyinstaller travel_content_studio.spec --noconfirm
echo "Backend built: backend/dist/travel-content-studio-backend/"

# Step 2: Build Electron + React frontend
echo "=== Building Electron frontend ==="
cd "$PROJECT_ROOT"
npm install
npm run build

# Step 3: Package with electron-builder
echo "=== Packaging application ==="
if [ "$PLATFORM" = "darwin" ] || [ "$PLATFORM" = "macos" ]; then
    npm run dist -- --mac
    echo "macOS DMG created in release/"
elif [ "$PLATFORM" = "windows" ] || [ "$PLATFORM" = "linux" ]; then
    npm run dist -- --win
    echo "Windows installer created in release/"
else
    npm run dist
fi

echo "=== Build complete ==="
ls -la "$PROJECT_ROOT/release/"
