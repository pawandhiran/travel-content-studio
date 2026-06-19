# Create Desktop shortcut for Travel Content Studio
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\Travel Content Studio.lnk")
$Shortcut.TargetPath = "$PSScriptRoot\..\Travel Content Studio.bat"
$Shortcut.WorkingDirectory = "$PSScriptRoot\.."
$Shortcut.IconLocation = "$PSScriptRoot\..\installer\assets\icon.ico"
$Shortcut.Description = "AI-powered travel content creation studio"
$Shortcut.Save()

# Also create Start Menu shortcut
$StartMenu = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
$Shortcut2 = $WshShell.CreateShortcut("$StartMenu\Travel Content Studio.lnk")
$Shortcut2.TargetPath = "$PSScriptRoot\..\Travel Content Studio.bat"
$Shortcut2.WorkingDirectory = "$PSScriptRoot\.."
$Shortcut2.IconLocation = "$PSScriptRoot\..\installer\assets\icon.ico"
$Shortcut2.Description = "AI-powered travel content creation studio"
$Shortcut2.Save()

Write-Host "Shortcuts created on Desktop and Start Menu!"
