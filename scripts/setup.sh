#!/usr/bin/env bash

# ========================================
# YoutubeDownloader - macOS Setup
# ========================================
# This script sets up the YoutubeDownloader API on macOS:
# - Checks for Python 3.8+
# - Creates a virtual environment
# - Installs all required dependencies
# - Optionally configures LaunchAgent for autostart

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo "========================================"
echo "  YoutubeDownloader - macOS Setup"
echo "========================================"
echo ""

# Change to project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
PROJECT_ROOT="$(pwd)"

# Check if Python is available
echo "[*] Checking Python installation..."
PYTHON_BIN=""
PYTHON_VERSION=""

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
  PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
  PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
else
  echo -e "${RED}[ERROR]${NC} Python is not installed or not on PATH."
  echo ""
  echo "Please install Python 3.8 or later:"
  echo "  - Using Homebrew: brew install python3"
  echo "  - From https://www.python.org/downloads/"
  echo ""
  exit 1
fi

# Check Python version (require at least 3.8)
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
  echo -e "${RED}[ERROR]${NC} Python $PYTHON_VERSION is too old."
  echo "This application requires Python 3.8 or later."
  echo ""
  exit 1
fi

echo -e "${GREEN}[OK]${NC} Found Python $PYTHON_VERSION"
echo ""

# Create virtual environment if it doesn't exist
if [ -d ".venv" ]; then
  echo "[*] Virtual environment already exists."
  read -p "Do you want to recreate it? (y/N): " -n 1 -r
  echo ""
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "[*] Removing existing virtual environment..."
    rm -rf .venv
  else
    echo "[*] Keeping existing virtual environment."
    echo ""
  fi
fi

if [ ! -d ".venv" ]; then
  echo "[*] Creating virtual environment..."
  "$PYTHON_BIN" -m venv .venv
  if [ $? -ne 0 ]; then
    echo -e "${RED}[ERROR]${NC} Failed to create virtual environment."
    echo ""
    echo "Make sure you have the 'venv' module available."
    echo "You may need to reinstall Python or install python3-venv."
    echo ""
    exit 1
  fi
  echo -e "${GREEN}[OK]${NC} Virtual environment created."
  echo ""
fi

# Activate virtual environment
echo "[*] Activating virtual environment..."
source .venv/bin/activate
if [ $? -ne 0 ]; then
  echo -e "${RED}[ERROR]${NC} Failed to activate virtual environment."
  exit 1
fi
echo -e "${GREEN}[OK]${NC} Virtual environment activated."
echo ""

# Upgrade pip
echo "[*] Upgrading pip..."
python -m pip install --upgrade pip --quiet
if [ $? -ne 0 ]; then
  echo -e "${YELLOW}[WARNING]${NC} Failed to upgrade pip, continuing anyway..."
else
  echo -e "${GREEN}[OK]${NC} pip upgraded."
fi
echo ""

# Install dependencies
echo "[*] Installing dependencies from requirements.txt..."
if [ ! -f "requirements.txt" ]; then
  echo -e "${RED}[ERROR]${NC} requirements.txt not found in project root."
  exit 1
fi

python -m pip install -r requirements.txt
if [ $? -ne 0 ]; then
  echo -e "${RED}[ERROR]${NC} Failed to install dependencies."
  echo ""
  echo "Please check the error messages above and ensure you have:"
  echo "- A stable internet connection"
  echo "- Proper permissions to install packages"
  echo ""
  exit 1
fi
echo -e "${GREEN}[OK]${NC} Dependencies installed successfully."
echo ""

# Verify installation
echo "[*] Verifying installation..."
python -c "import flask; import pytube" 2>/dev/null
if [ $? -ne 0 ]; then
  python -c "import flask; import pytubefix" 2>/dev/null
  if [ $? -ne 0 ]; then
    echo -e "${YELLOW}[WARNING]${NC} Could not verify all required packages."
    echo "The installation may be incomplete."
  else
    echo -e "${GREEN}[OK]${NC} Installation verified (using pytubefix)."
  fi
else
  echo -e "${GREEN}[OK]${NC} Installation verified."
fi
echo ""

# Test if main.py exists
if [ ! -f "src/main.py" ]; then
  echo -e "${YELLOW}[WARNING]${NC} src/main.py not found. Project may be incomplete."
  echo ""
fi

echo "========================================"
echo "  Setup Complete!"
echo "========================================"
echo ""
echo "You can now run the YoutubeDownloader using:"
echo "  ./scripts/run.sh"
echo ""
echo "To run in verbose mode (see output):"
echo "  ./scripts/run.sh --verbose"
echo ""

# Ask about autostart configuration
read -p "Do you want to configure autostart at login? (y/N): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
  echo ""
  echo "[*] Configuring LaunchAgent for autostart..."
  
  LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
  PLIST_SOURCE="$PROJECT_ROOT/deployment/com.youtube-downloader.plist"
  PLIST_DEST="$LAUNCH_AGENTS_DIR/com.youtube-downloader.plist"
  
  # Check if plist file exists
  if [ ! -f "$PLIST_SOURCE" ]; then
    echo -e "${RED}[ERROR]${NC} $PLIST_SOURCE not found."
    echo "Please ensure the deployment files are present."
  else
    # Create LaunchAgents directory if it doesn't exist
    mkdir -p "$LAUNCH_AGENTS_DIR"
    
    # Copy and update the plist file with absolute paths
    cp "$PLIST_SOURCE" "$PLIST_DEST"
    
    # Update paths in plist file (replace placeholder with actual project root)
    if command -v sed >/dev/null 2>&1; then
      # macOS sed requires different syntax
      sed -i '' "s|/path/to/project|$PROJECT_ROOT|g" "$PLIST_DEST" 2>/dev/null || true
    fi
    
    # Load the LaunchAgent
    launchctl unload "$PLIST_DEST" 2>/dev/null || true
    launchctl load "$PLIST_DEST"
    
    if [ $? -eq 0 ]; then
      echo -e "${GREEN}[OK]${NC} LaunchAgent configured successfully."
      echo "The service will start automatically at login."
      echo ""
      echo "Useful commands:"
      echo "  Start:   launchctl start com.youtube-downloader"
      echo "  Stop:    launchctl stop com.youtube-downloader"
      echo "  Disable: launchctl unload $PLIST_DEST"
    else
      echo -e "${RED}[ERROR]${NC} Failed to load LaunchAgent."
      echo "You may need to configure it manually."
    fi
  fi
  echo ""
fi

echo "Setup complete! Press Enter to exit..."
read -r
