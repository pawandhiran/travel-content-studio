#!/bin/bash
# Travel Content Studio — Quick Launcher
# Double-click this file in Finder to start the app.

cd "$(dirname "$0")"

export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
unset ELECTRON_RUN_AS_NODE

if [ ! -d "node_modules" ]; then
  echo "First run detected — installing dependencies..."
  npm install --legacy-peer-deps
fi

echo "Starting Travel Content Studio..."
npm run dev
