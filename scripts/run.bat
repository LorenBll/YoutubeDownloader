@echo off
setlocal enabledelayedexpansion

REM Start YouTube Downloader.

set VERBOSE=0
if "%1"=="--verbose" (
  set VERBOSE=1
)

pushd "%~dp0\.."

REM Check Python 3.10+.
where python >nul 2>&1
if errorlevel 1 (
  if %VERBOSE% equ 1 echo ERROR: Python not installed or not on PATH.
  popd
  exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i

for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
  set MAJOR=%%a
  set MINOR=%%b
)

if %MAJOR% lss 3 (
  if %VERBOSE% equ 1 echo ERROR: Python 3.10+ required; found %PYTHON_VERSION%
  popd
  exit /b 1
)

if %MAJOR% equ 3 if %MINOR% lss 10 (
  if %VERBOSE% equ 1 echo ERROR: Python 3.10+ required; found %PYTHON_VERSION%
  popd
  exit /b 1
)

if %VERBOSE% equ 1 echo Python %PYTHON_VERSION% detected.

REM Create or reuse virtual environment.
if not exist ".venv" (
  if %VERBOSE% equ 1 echo Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    if %VERBOSE% equ 1 echo ERROR: Failed to create virtual environment.
    popd
    exit /b 1
  )
  if %VERBOSE% equ 1 echo Virtual environment created.
)

REM Activate virtual environment.
call .venv\Scripts\activate.bat
if errorlevel 1 (
  if %VERBOSE% equ 1 echo ERROR: Failed to activate virtual environment.
  popd
  exit /b 1
)
if %VERBOSE% equ 1 echo Virtual environment activated.

REM Install or upgrade dependencies.
if %VERBOSE% equ 1 echo Installing dependencies...
python -m pip install --quiet --upgrade pip >nul 2>&1
python -m pip install --quiet -r requirements.txt >nul 2>&1
if %VERBOSE% equ 1 echo Dependencies installed.

REM Start YouTube Downloader.
if %VERBOSE% equ 1 (
  echo.
  echo YouTube Downloader starting...
  echo.
  python src/main.py
) else (
  start /B python src/main.py >nul 2>&1
  if errorlevel 1 (
    echo ERROR: Failed to start YouTube Downloader.
    popd
    exit /b 1
  )
  echo YouTube Downloader started in background. Run 'run.bat --verbose' to see output.
)

popd
endlocal
