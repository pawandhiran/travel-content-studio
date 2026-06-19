# Travel Content Studio - Windows Build Script

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Write-Host "Building Travel Content Studio for Windows"

# Step 1: Build Python backend
Write-Host "=== Building Python backend ==="
Set-Location "$ProjectRoot\backend"
pip install pyinstaller
pyinstaller travel_content_studio.spec --noconfirm

# Step 2: Build Electron frontend
Write-Host "=== Building Electron frontend ==="
Set-Location $ProjectRoot
npm install
npm run build

# Step 3: Package
Write-Host "=== Packaging application ==="
npm run dist -- --win

# Step 4: Compile Inno Setup installer (if iscc is available)
$iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (Test-Path $iscc) {
    Write-Host "=== Compiling Inno Setup installer ==="
    & $iscc "$ProjectRoot\installer\setup.iss"
    Write-Host "Installer created: installer/Output/TravelContentStudioSetup.exe"
} else {
    Write-Host "Inno Setup not found, skipping .exe installer"
}

Write-Host "=== Build complete ==="
