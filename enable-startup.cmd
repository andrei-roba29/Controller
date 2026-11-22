@echo off
setlocal
cd /d "%~dp0"
echo Setting up PadLink to start when you sign in to Windows...
call start-padlink.cmd --setup-only
if errorlevel 1 exit /b 1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows-startup.ps1"
if errorlevel 1 (
  echo Could not enable startup. See the error above.
  pause
  exit /b 1
)
echo Startup enabled. Opening PadLink now. No PowerShell command needed next time.
start "PadLink" "%~dp0.venv\Scripts\python.exe" "%~dp0agent.py"
pause
