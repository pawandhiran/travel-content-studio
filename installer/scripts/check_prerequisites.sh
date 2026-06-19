#!/bin/bash
# Travel Content Studio - macOS Prerequisite Check Script

set -e

MIN_RAM_GB=8
MIN_DISK_GB=20
ERRORS=0
WARNINGS=0

green() { printf "\033[32m  [OK] %s\033[0m\n" "$1"; }
yellow() { printf "\033[33m  [WARN] %s\033[0m\n" "$1"; }
red() { printf "\033[31m  [FAIL] %s\033[0m\n" "$1"; }

echo ""
echo "Travel Content Studio - macOS System Check"
echo ""

# macOS Version
macos_ver=$(sw_vers -productVersion 2>/dev/null || echo "unknown")
major=$(echo "$macos_ver" | cut -d. -f1)
if [ "$major" -ge 13 ] 2>/dev/null; then
    green "macOS version: $macos_ver"
else
    red "macOS version: $macos_ver (minimum 13.0 Ventura required)"
    ERRORS=$((ERRORS + 1))
fi

# RAM
ram_bytes=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
ram_gb=$((ram_bytes / 1073741824))
if [ "$ram_gb" -ge "$MIN_RAM_GB" ]; then
    green "System RAM: ${ram_gb}GB"
else
    yellow "System RAM: ${ram_gb}GB (minimum ${MIN_RAM_GB}GB recommended)"
    WARNINGS=$((WARNINGS + 1))
fi

# Disk Space
free_gb=$(df -g / | awk 'NR==2 {print $4}')
if [ "$free_gb" -ge "$MIN_DISK_GB" ]; then
    green "Free disk space: ${free_gb}GB"
else
    red "Free disk space: ${free_gb}GB (need ${MIN_DISK_GB}GB)"
    ERRORS=$((ERRORS + 1))
fi

# CPU / Apple Silicon
cpu_brand=$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "unknown")
arch=$(uname -m)
if [ "$arch" = "arm64" ]; then
    green "CPU: $cpu_brand (Apple Silicon)"
else
    yellow "CPU: $cpu_brand (Intel - no Metal/MPS GPU acceleration)"
    WARNINGS=$((WARNINGS + 1))
fi

# GPU
gpu_name=$(system_profiler SPDisplaysDataType 2>/dev/null | grep "Chipset Model" | head -1 | sed 's/.*: //')
if [ -n "$gpu_name" ]; then
    green "GPU: $gpu_name"
else
    yellow "GPU: Could not detect"
    WARNINGS=$((WARNINGS + 1))
fi

# Python 3
if command -v python3 &>/dev/null; then
    py_ver=$(python3 --version 2>&1)
    green "Python: $py_ver"
else
    yellow "Python 3: Not found (needed for development only)"
    WARNINGS=$((WARNINGS + 1))
fi

# Ollama
if command -v ollama &>/dev/null; then
    green "Ollama: $(which ollama)"
else
    yellow "Ollama: Not installed (will be installed)"
    WARNINGS=$((WARNINGS + 1))
fi

# FFmpeg
if command -v ffmpeg &>/dev/null; then
    green "FFmpeg: $(which ffmpeg)"
else
    yellow "FFmpeg: Not found (will be installed)"
    WARNINGS=$((WARNINGS + 1))
fi

# Homebrew
if command -v brew &>/dev/null; then
    green "Homebrew: $(which brew)"
else
    yellow "Homebrew: Not found (recommended for installing dependencies)"
    WARNINGS=$((WARNINGS + 1))
fi

# Summary
echo ""
if [ "$ERRORS" -gt 0 ]; then
    printf "\033[31mFAILED: %d blocking issue(s) found.\033[0m\n" "$ERRORS"
    exit 1
elif [ "$WARNINGS" -gt 0 ]; then
    printf "\033[33mPASSED with %d warning(s).\033[0m\n" "$WARNINGS"
    exit 0
else
    printf "\033[32mPASSED: All checks OK.\033[0m\n"
    exit 0
fi
