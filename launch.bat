@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Concept Tracking is not installed yet.
  echo Please double-click setup.bat first.
  pause
  exit /b 1
)
start "Concept Tracking CRM" ".venv\Scripts\pythonw.exe" "%~dp0run_desktop.py"
exit /b 0
