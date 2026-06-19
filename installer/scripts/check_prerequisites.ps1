# Travel Content Studio - Prerequisite Check Script
# Validates system meets minimum requirements

param(
    [switch]$Quiet
)

$MinRAMGB = 8
$MinDiskGB = 20
$Errors = @()
$Warnings = @()

function Write-Status($message, $status) {
    if (-not $Quiet) {
        $color = if ($status -eq "OK") { "Green" } elseif ($status -eq "WARN") { "Yellow" } else { "Red" }
        Write-Host "  [$status] $message" -ForegroundColor $color
    }
}

Write-Host "`nTravel Content Studio - System Check`n" -ForegroundColor Cyan

# Windows Version
$os = Get-CimInstance Win32_OperatingSystem
$build = [int]$os.BuildNumber
if ($build -ge 17763) {
    Write-Status "Windows version: $($os.Caption) (Build $build)" "OK"
} else {
    $Errors += "Windows 10 1809+ required"
    Write-Status "Windows version: Build $build (minimum 17763 required)" "FAIL"
}

# RAM
$ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
if ($ramGB -ge $MinRAMGB) {
    Write-Status "System RAM: ${ramGB}GB" "OK"
} else {
    $Warnings += "Only ${ramGB}GB RAM detected"
    Write-Status "System RAM: ${ramGB}GB (minimum ${MinRAMGB}GB recommended)" "WARN"
}

# Disk Space
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
$freeGB = [math]::Round($disk.FreeSpace / 1GB)
if ($freeGB -ge $MinDiskGB) {
    Write-Status "Free disk space: ${freeGB}GB" "OK"
} else {
    $Errors += "Need ${MinDiskGB}GB free disk space"
    Write-Status "Free disk space: ${freeGB}GB (need ${MinDiskGB}GB)" "FAIL"
}

# GPU
$gpus = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -like "*NVIDIA*" }
if ($gpus) {
    foreach ($gpu in $gpus) {
        Write-Status "GPU: $($gpu.Name)" "OK"
    }
} else {
    $Warnings += "No NVIDIA GPU detected"
    Write-Status "GPU: No NVIDIA GPU found (CPU mode only)" "WARN"
}

# CUDA
$nvidiaSmi = "C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"
if (Test-Path $nvidiaSmi) {
    $smiOutput = & $nvidiaSmi --query-gpu=driver_version,memory.total --format=csv,noheader 2>$null
    if ($smiOutput) {
        Write-Status "CUDA driver: $($smiOutput.Trim())" "OK"
    }
} elseif ($gpus) {
    Write-Status "nvidia-smi not found (CUDA driver may need update)" "WARN"
}

# Ollama
$ollamaPath = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
if (-not (Test-Path $ollamaPath)) {
    $ollamaPath = "C:\Program Files\Ollama\ollama.exe"
}
if (Test-Path $ollamaPath) {
    Write-Status "Ollama: Installed" "OK"
} else {
    Write-Status "Ollama: Not installed (will be installed)" "WARN"
}

# FFmpeg
$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($ffmpeg) {
    Write-Status "FFmpeg: $($ffmpeg.Source)" "OK"
} else {
    Write-Status "FFmpeg: Not found (will be installed)" "WARN"
}

# Summary
Write-Host ""
if ($Errors.Count -gt 0) {
    Write-Host "FAILED: $($Errors.Count) blocking issue(s) found." -ForegroundColor Red
    exit 1
} elseif ($Warnings.Count -gt 0) {
    Write-Host "PASSED with $($Warnings.Count) warning(s)." -ForegroundColor Yellow
    exit 0
} else {
    Write-Host "PASSED: All checks OK." -ForegroundColor Green
    exit 0
}
