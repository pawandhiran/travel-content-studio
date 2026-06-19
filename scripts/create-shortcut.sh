#!/bin/bash
# create-shortcut.sh — Set up Desktop shortcut and optional Dock pin
# for Travel Content Studio (macOS only).
#
# Windows equivalent: scripts/create-shortcut.bat (or create-shortcut.ps1)
#
# Usage:  ./scripts/create-shortcut.sh [--dock]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APP_BUNDLE="$PROJECT_DIR/Travel Content Studio.app"
DESKTOP_LINK="$HOME/Desktop/Travel Content Studio.app"

if [ ! -d "$APP_BUNDLE" ]; then
  echo "Error: .app bundle not found at $APP_BUNDLE"
  exit 1
fi

# Ensure launcher is executable
chmod +x "$APP_BUNDLE/Contents/MacOS/launcher"

# --- Desktop symlink ---
if [ -L "$DESKTOP_LINK" ] || [ -e "$DESKTOP_LINK" ]; then
  echo "Removing existing Desktop shortcut..."
  rm -f "$DESKTOP_LINK"
fi

ln -sf "$APP_BUNDLE" "$DESKTOP_LINK"
echo "Desktop shortcut created: $DESKTOP_LINK"

# --- Dock (optional) ---
if [[ "${1:-}" == "--dock" ]]; then
  DOCK_ENTRY="<dict><key>tile-data</key><dict><key>file-data</key><dict><key>_CFURLString</key><string>$APP_BUNDLE</string><key>_CFURLStringType</key><integer>0</integer></dict></dict></dict>"

  ALREADY_IN_DOCK=$(defaults read com.apple.dock persistent-apps 2>/dev/null | grep -c "Travel Content Studio" || true)
  if [ "$ALREADY_IN_DOCK" -gt 0 ]; then
    echo "Already in Dock — skipping."
  else
    defaults write com.apple.dock persistent-apps -array-add "$DOCK_ENTRY"
    killall Dock
    echo "Added to Dock (Dock will restart)."
  fi
else
  echo "Tip: Run with --dock to also pin to the Dock."
fi

echo "Done."
