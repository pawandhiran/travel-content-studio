# Install Ollama silently

$InstallerUrl = "https://ollama.com/download/OllamaSetup.exe"
$InstallerPath = "$env:TEMP\OllamaSetup.exe"

$ollamaPath = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
if (Test-Path $ollamaPath) {
    Write-Host "Ollama is already installed at $ollamaPath"
    exit 0
}

$altPath = "C:\Program Files\Ollama\ollama.exe"
if (Test-Path $altPath) {
    Write-Host "Ollama is already installed at $altPath"
    exit 0
}

Write-Host "Downloading Ollama installer..."
try {
    Invoke-WebRequest -Uri $InstallerUrl -OutFile $InstallerPath -UseBasicParsing
} catch {
    Write-Error "Failed to download Ollama: $_"
    exit 1
}

Write-Host "Installing Ollama..."
$proc = Start-Process -FilePath $InstallerPath -ArgumentList "/VERYSILENT", "/NORESTART" -Wait -PassThru
if ($proc.ExitCode -ne 0) {
    Write-Error "Ollama installation failed with exit code $($proc.ExitCode)"
    exit 1
}

Remove-Item $InstallerPath -Force -ErrorAction SilentlyContinue
Write-Host "Ollama installed successfully."
