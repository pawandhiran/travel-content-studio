# Install Python 3.11 embeddable for the backend

param(
    [Parameter(Mandatory=$true)]
    [string]$InstallDir
)

$PythonVersion = "3.11.9"
$PythonUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$ZipPath = "$env:TEMP\python-embed.zip"
$PythonDir = Join-Path $InstallDir "python"

if (Test-Path (Join-Path $PythonDir "python.exe")) {
    Write-Host "Python embeddable is already installed."
    exit 0
}

New-Item -ItemType Directory -Force -Path $PythonDir | Out-Null

Write-Host "Downloading Python $PythonVersion embeddable..."
try {
    Invoke-WebRequest -Uri $PythonUrl -OutFile $ZipPath -UseBasicParsing
} catch {
    Write-Error "Failed to download Python: $_"
    exit 1
}

Write-Host "Extracting Python..."
Expand-Archive -Path $ZipPath -DestinationPath $PythonDir -Force

# Enable pip by uncommenting import site in python311._pth
$pthFile = Get-ChildItem -Path $PythonDir -Filter "python*._pth" | Select-Object -First 1
if ($pthFile) {
    $content = Get-Content $pthFile.FullName
    $content = $content -replace '#import site', 'import site'
    Set-Content -Path $pthFile.FullName -Value $content
}

# Install pip
$getPipUrl = "https://bootstrap.pypa.io/get-pip.py"
$getPipPath = "$env:TEMP\get-pip.py"
Invoke-WebRequest -Uri $getPipUrl -OutFile $getPipPath -UseBasicParsing

$pythonExe = Join-Path $PythonDir "python.exe"
& $pythonExe $getPipPath --no-warn-script-location

Remove-Item $ZipPath -Force -ErrorAction SilentlyContinue
Remove-Item $getPipPath -Force -ErrorAction SilentlyContinue

Write-Host "Python $PythonVersion installed successfully."
