@echo off
setlocal
cd /d "%~dp0"
echo.
echo  CONCEPT TRACKING CRM - SETUP
echo  -----------------------------
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 --version >nul 2>nul
  if %errorlevel%==0 (set "PYTHON_CMD=py -3") else (set "PYTHON_CMD=python")
) else (
  set "PYTHON_CMD=python"
)
if not exist ".venv\Scripts\python.exe" (
  echo Creating the app environment...
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 goto :failed
)
echo Installing app packages. An internet connection may be needed on the first setup...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -c "from app import init_db; init_db(); print('Database initialized.')"
if errorlevel 1 goto :failed
echo.
echo Creating a desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0create_desktop_shortcut.ps1"
echo.
echo Setup complete. Launch using the Concept Tracking CRM icon on your Desktop.
echo On first launch, create your own username and password.
pause
exit /b 0
:failed
echo.
echo Setup could not finish. Please check that Python 3.10 or newer is installed and try again.
echo You can also run setup.bat again after connecting to the internet.
pause
exit /b 1
