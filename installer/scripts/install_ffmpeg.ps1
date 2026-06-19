# Install FFmpeg to application directory

param(
    [Parameter(Mandatory=$true)]
    [string]$InstallDir
)

$FFmpegUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
$ZipPath = "$env:TEMP\ffmpeg.zip"
$ExtractPath = "$env:TEMP\ffmpeg-extract"
$BinDir = Join-Path $InstallDir "bin"

if ((Test-Path (Join-Path $BinDir "ffmpeg.exe")) -and (Test-Path (Join-Path $BinDir "ffprobe.exe"))) {
    Write-Host "FFmpeg is already installed."
    exit 0
}

New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

Write-Host "Downloading FFmpeg..."
try {
    Invoke-WebRequest -Uri $FFmpegUrl -OutFile $ZipPath -UseBasicParsing
} catch {
    Write-Error "Failed to download FFmpeg: $_"
    exit 1
}

Write-Host "Extracting FFmpeg..."
Expand-Archive -Path $ZipPath -DestinationPath $ExtractPath -Force

$ffmpegBin = Get-ChildItem -Path $ExtractPath -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
$ffprobeBin = Get-ChildItem -Path $ExtractPath -Recurse -Filter "ffprobe.exe" | Select-Object -First 1

if ($ffmpegBin) {
    Copy-Item $ffmpegBin.FullName -Destination $BinDir -Force
    Write-Host "ffmpeg.exe installed."
}
if ($ffprobeBin) {
    Copy-Item $ffprobeBin.FullName -Destination $BinDir -Force
    Write-Host "ffprobe.exe installed."
}

Remove-Item $ZipPath -Force -ErrorAction SilentlyContinue
Remove-Item $ExtractPath -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "FFmpeg installed successfully."
