@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows-startup.ps1" -Remove
pause
