@echo off
setlocal enabledelayedexpansion

REM ========================================
REM YoutubeDownloader - Windows Setup
REM ========================================
REM This script sets up the YoutubeDownloader API on Windows:
REM - Checks for Python 3.8+
REM - Creates a virtual environment
REM - Installs all required dependencies
REM - Optionally configures autostart

echo.
echo ===============================================
echo   ^^ YoutubeDownloader - Windows Setup
echo ===============================================
echo.

REM Change to project root directory
cd /d "%~dp0.."
set PROJECT_ROOT=%CD%

REM Check if Python is available
echo [*] Checking Python installation...
where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python is not installed or not on PATH.
  echo.
  echo Please install Python 3.8 or later from https://www.python.org/downloads/
  echo Make sure to check "Add Python to PATH" during installation.
  echo.
  pause
  exit /b 1
)

REM Check Python version
python --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Unable to determine Python version.
  pause
  exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [OK] Found Python %PYTHON_VERSION%
echo.

REM Create virtual environment if it doesn't exist
if exist ".venv" (
  echo [*] Virtual environment already exists.
  echo.
  echo Do you want to recreate it?
  choice /C YN
  if errorlevel 2 goto skip_venv_creation
  if errorlevel 1 (
    echo [*] Removing existing virtual environment...
    rmdir /s /q .venv
  )
)

echo [*] Creating virtual environment...
python -m venv .venv
if errorlevel 1 (
  echo [ERROR] Failed to create virtual environment.
  echo.
  echo Make sure you have the 'venv' module available.
  echo You may need to reinstall Python with all optional components.
  echo.
  pause
  exit /b 1
)
echo [OK] Virtual environment created.
echo.

:skip_venv_creation

REM Activate virtual environment
echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat
if errorlevel 1 (
  echo [ERROR] Failed to activate virtual environment.
  pause
  exit /b 1
)
echo [OK] Virtual environment activated.
echo.

REM Upgrade pip
echo [*] Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 (
  echo [WARNING] Failed to upgrade pip, continuing anyway...
) else (
  echo [OK] pip upgraded.
)
echo.

REM Install dependencies
echo [*] Installing dependencies from requirements.txt...
if not exist "requirements.txt" (
  echo [ERROR] requirements.txt not found in project root.
  pause
  exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Failed to install dependencies.
  echo.
  echo Please check the error messages above and ensure you have:
  echo - A stable internet connection
  echo - Proper permissions to install packages
  echo.
  pause
  exit /b 1
)
echo [OK] Dependencies installed successfully.
echo.

REM Verify installation
echo [*] Verifying installation...
python -m pip show flask >nul 2>&1
if errorlevel 1 (
  echo [WARNING] Could not verify all required packages.
  echo The installation may be incomplete.
) else (
  echo [OK] Installation verified.
)
echo.

REM Test if main.py exists
if not exist "src\main.py" (
  echo [WARNING] src\main.py not found. Project may be incomplete.
)

echo.
echo ===============================================
echo   Setup Complete!
echo ===============================================
echo.
echo You can now run the YoutubeDownloader using:
echo   scripts\run.bat
echo.
echo To run in verbose mode ^(see output^):
echo   scripts\run.bat --verbose
echo.

echo Do you want to configure autostart at Windows login?
choice /C YN
if errorlevel 2 goto skip_autostart
if errorlevel 1 goto configure_autostart

:configure_autostart
echo.
echo [*] Configuring autostart...

REM Create startup shortcut
set STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set SHORTCUT_PATH=%STARTUP_FOLDER%\YoutubeDownloader.lnk

REM Check if deployment\startup-windows.vbs exists
if exist "deployment\startup-windows.vbs" (
  REM Create shortcut to VBS script
  powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = '%PROJECT_ROOT%\deployment\startup-windows.vbs'; $s.WorkingDirectory = '%PROJECT_ROOT%'; $s.Save()"
  if errorlevel 1 (
    echo [ERROR] Failed to create startup shortcut.
  ) else (
    echo [OK] Autostart configured successfully.
    echo The service will start automatically at Windows login.
  )
) else (
  echo [ERROR] startup-windows.vbs not found in deployment folder.
  echo Please ensure the deployment files are present.
)
echo.

:skip_autostart

echo Press any key to exit...
pause >nul
endlocal
