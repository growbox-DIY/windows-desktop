@echo off
rem Installs Pillow, adds GrowBox to the Start menu and the desktop, then starts it (no console window).
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python not found. Install it with:
  echo   winget install Python.Python.3.12
  echo and run this file again.
  pause
  exit /b 1
)
py -m pip install --user --upgrade pillow
for /f "delims=" %%i in ('where pyw') do set "PYW=%%i" & goto :found
:found
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = New-Object -ComObject WScript.Shell;" ^
  "foreach ($dir in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {" ^
  "  $l = $s.CreateShortcut((Join-Path $dir 'GrowBox.lnk'));" ^
  "  $l.TargetPath = '%PYW%'; $l.Arguments = '\"%~dp0growbox_desktop.pyw\"';" ^
  "  $l.WorkingDirectory = '%~dp0'; $l.Save() }"
start "" pyw "%~dp0growbox_desktop.pyw"
