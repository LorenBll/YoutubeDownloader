@echo off
setlocal enabledelayedexpansion

REM ========================================
REM YoutubeDownloader - Windows Setup
REM ========================================
REM This script sets up the YoutubeDownloader on Windows:
REM - Checks for Python 3.10+
REM - Creates a virtual environment
REM - Installs all required dependencies

echo.
echo ===============================================
echo   YoutubeDownloader - Windows Setup
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
  echo Please install Python 3.10 or later from https://www.python.org/downloads/
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
  choice /C YN /M "Recreate virtual environment"
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
  echo [ERROR] requirements.txt not found!
  pause
  exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Failed to install dependencies.
  echo.
  echo Please check your internet connection and requirements.txt file.
  pause
  exit /b 1
)
echo [OK] Dependencies installed successfully.
echo.

REM Check configuration file
echo [*] Checking configuration...
if not exist "resources\configuration.json" (
  echo [WARNING] Configuration file not found at resources\configuration.json
  echo [*] You need to create this file before running the service.
  echo.
) else (
  echo [OK] Configuration file found.
)
echo.

echo ===============================================
echo   Setup Complete!
echo ===============================================
echo.
echo Next steps:
echo   1. Review/edit resources\configuration.json
echo   2. Run the service with: scripts\run.bat
echo   3. Test with: http://localhost:PORT/api/health
echo.
echo For auto-startup on Windows:
echo   1. Edit deployment\startup-windows.vbs (update paths if needed)
echo   2. Press Win+R, type: shell:startup
echo   3. Copy startup-windows.vbs to the Startup folder
echo.
pause
