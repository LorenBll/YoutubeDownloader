@echo off
setlocal enabledelayedexpansion

set VERBOSE=0
if "%1"=="--verbose" (
  set VERBOSE=1
)

REM Navigate to project root (parent of scripts directory)
pushd "%~dp0\.."
set PROJECT_ROOT=%CD%

if %VERBOSE% equ 1 (
  echo.
  echo ===============================================
  echo   ^^ YoutubeDownloader - Starting
  echo ===============================================
  echo.
)

REM Check if Python is available
where python >nul 2>&1
if errorlevel 1 (
  if %VERBOSE% equ 1 echo [ERROR] Python is not installed or not on PATH.
  popd
  exit /b 1
)

REM Create virtual environment if it doesn't exist
if not exist ".venv" (
  if %VERBOSE% equ 1 echo [*] Creating virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    if %VERBOSE% equ 1 echo [ERROR] Failed to create virtual environment.
    popd
    exit /b 1
  )
  if %VERBOSE% equ 1 echo [OK] Virtual environment created.
)

REM Activate virtual environment
call .venv\Scripts\activate.bat
if errorlevel 1 (
  if %VERBOSE% equ 1 echo [ERROR] Failed to activate virtual environment.
  popd
  exit /b 1
)
if %VERBOSE% equ 1 echo [OK] Virtual environment activated.

REM Install/upgrade dependencies
if %VERBOSE% equ 1 echo [*] Installing dependencies...
python -m pip install --quiet --upgrade pip >nul 2>&1
if errorlevel 1 (
  if %VERBOSE% equ 1 echo [ERROR] Failed to upgrade pip.
  popd
  exit /b 1
)

python -m pip install --quiet -r requirements.txt >nul 2>&1
if errorlevel 1 (
  if %VERBOSE% equ 1 echo [ERROR] Failed to install requirements.
  popd
  exit /b 1
)
if %VERBOSE% equ 1 echo [OK] Dependencies installed.

if %VERBOSE% equ 1 (
  echo.
  echo ===============================================
  echo.   Starting YoutubeDownloader...
  echo.
  python src/main.py
) else (
  start /B python src/main.py >nul 2>&1
  if errorlevel 1 (
    echo.
    echo [!] Failed to start YoutubeDownloader.
    echo.
    popd
    exit /b 1
  )
  echo.
  echo ^[*^] YoutubeDownloader started in background
  echo     Use 'run.bat --verbose' to see output
  echo.
)

popd
endlocal
