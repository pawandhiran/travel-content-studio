@echo off
title Travel Content Studio
cd /d "%~dp0"

:: Electron must NOT run as a plain Node.js process
set ELECTRON_RUN_AS_NODE=

echo Starting Travel Content Studio...
echo.

:: Check if node_modules exists
if not exist "node_modules" (
    echo Installing dependencies...
    call npm install --legacy-peer-deps
)

:: Check if backend venv exists
if not exist "backend\.venv" (
    echo Setting up Python backend...
    cd backend
    python -m venv .venv
    call .venv\Scripts\activate
    pip install -e ".[dev]"
    cd ..
)

:: Start Ollama if not running
tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | find /I /N "ollama.exe">NUL
if errorlevel 1 (
    echo Starting Ollama...
    start /B ollama serve
    timeout /t 3 /nobreak >NUL
)

:: Start the app
echo Starting app...
call npm run dev

pause
