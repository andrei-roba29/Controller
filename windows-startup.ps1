param([switch]$Remove)
$ErrorActionPreference = 'Stop'
# Per-user Startup shortcut: no administrator rights, service, or scheduled task.
$startup = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startup 'PadLink.lnk'
if ($Remove) {
    if (Test-Path -LiteralPath $shortcutPath) { Remove-Item -LiteralPath $shortcutPath }
    Write-Host 'PadLink will no longer start at sign-in. Stop the running agent separately.'
    exit 0
}
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$agent = Join-Path $PSScriptRoot 'agent.py'
if (!(Test-Path -LiteralPath $python)) { throw 'Run enable-startup.cmd to install dependencies first.' }
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $python
$shortcut.Arguments = '"' + $agent + '" --no-browser'
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.WindowStyle = 7 # Minimized console; restore it to see errors or stop with Ctrl+C.
$shortcut.Description = 'PadLink phone controller PC agent'
$shortcut.Save()
Write-Host 'PadLink enabled for this user at Windows sign-in (minimized).'
Write-Host 'PC dashboard: http://127.0.0.1:8765/host'
Write-Host 'Keep this folder in place. Run disable-startup.cmd to undo.'
