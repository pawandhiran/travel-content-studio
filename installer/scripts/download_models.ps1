# Download the appropriate Ollama model based on system RAM

$ollamaPath = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
if (-not (Test-Path $ollamaPath)) {
    $ollamaPath = "C:\Program Files\Ollama\ollama.exe"
}
if (-not (Test-Path $ollamaPath)) {
    $ollamaPath = (Get-Command ollama -ErrorAction SilentlyContinue).Source
}

if (-not $ollamaPath -or -not (Test-Path $ollamaPath)) {
    Write-Error "Ollama not found. Please install Ollama first."
    exit 1
}

# Start Ollama server if not running
$ollamaRunning = $false
try {
    $response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 5
    $ollamaRunning = $true
} catch {
    Write-Host "Starting Ollama server..."
    Start-Process -FilePath $ollamaPath -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 5
}

# Determine model based on RAM
$ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)

if ($ramGB -ge 32) {
    $model = "qwen3:32b"
} elseif ($ramGB -ge 16) {
    $model = "qwen3:14b"
} else {
    $model = "qwen3:8b"
}

Write-Host "System RAM: ${ramGB}GB -> Downloading model: $model"
Write-Host "This may take 10-30 minutes depending on your internet connection..."

& $ollamaPath pull $model

if ($LASTEXITCODE -eq 0) {
    Write-Host "Model $model downloaded successfully." -ForegroundColor Green
} else {
    Write-Error "Failed to download model $model"
    exit 1
}
