@echo off
echo Creating Travel Content Studio shortcuts...
powershell -ExecutionPolicy Bypass -File "%~dp0create-shortcut.ps1"
echo Done!
pause
