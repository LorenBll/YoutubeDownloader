#!/bin/bash

# ========================================
# YouTube Downloader - Unix Setup
# ========================================
# This script sets up YouTube Downloader on macOS/Linux:
# - Checks for Python 3.10+
# - Creates a virtual environment
# - Installs all required dependencies

echo ""
echo "==============================================="
echo "  YouTube Downloader - Setup"
echo "==============================================="
echo ""

# Change to project root directory
cd "$(dirname "$0")/.." || exit 1
PROJECT_ROOT=$(pwd)

# Check if Python 3 is available
echo "[*] Checking Python installation..."
if ! command -v python3 &> /dev/null; then
  echo "[ERROR] Python 3 is not installed."
  echo ""
  echo "Please install Python 3.10 or later:"
  echo "  - macOS: brew install python3"
  echo "  - Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
  echo "  - Fedora: sudo dnf install python3"
  echo ""
  exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "[OK] Found Python $PYTHON_VERSION"
echo ""

# Create virtual environment if it doesn't exist
if [ -d ".venv" ]; then
  echo "[*] Virtual environment already exists."
  read -p "Do you want to recreate it? (y/N): " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "[*] Removing existing virtual environment..."
    rm -rf .venv
  else
    echo "[*] Using existing virtual environment."
  fi
fi

if [ ! -d ".venv" ]; then
  echo "[*] Creating virtual environment..."
  python3 -m venv .venv
  if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to create virtual environment."
    echo ""
    echo "Make sure python3-venv is installed:"
    echo "  - Ubuntu/Debian: sudo apt install python3-venv"
    echo "  - Fedora: sudo dnf install python3-venv"
    echo ""
    exit 1
  fi
  echo "[OK] Virtual environment created."
fi
echo ""

# Activate virtual environment
echo "[*] Activating virtual environment..."
source .venv/bin/activate
if [ $? -ne 0 ]; then
  echo "[ERROR] Failed to activate virtual environment."
  exit 1
fi
echo "[OK] Virtual environment activated."
echo ""

# Upgrade pip
echo "[*] Upgrading pip..."
python -m pip install --upgrade pip > /dev/null
if [ $? -ne 0 ]; then
  echo "[WARNING] Failed to upgrade pip, continuing anyway..."
else
  echo "[OK] pip upgraded."
fi
echo ""

# Install dependencies
echo "[*] Installing dependencies from requirements.txt..."
if [ ! -f "requirements.txt" ]; then
  echo "[ERROR] requirements.txt not found!"
  exit 1
fi

python -m pip install -r requirements.txt
if [ $? -ne 0 ]; then
  echo "[ERROR] Failed to install dependencies."
  echo ""
  echo "Please check your internet connection and requirements.txt file."
  exit 1
fi
echo "[OK] Dependencies installed."
echo ""

# Check configuration file
echo "[*] Checking configuration..."
if [ ! -f "resources/configuration.json" ]; then
  echo "[WARNING] Configuration file not found at resources/configuration.json"
  echo "[*] You need to create this file before running the service."
  echo ""
else
  echo "[OK] Configuration file found."
fi
echo ""

echo "==============================================="
echo "  Setup Complete!"
echo "==============================================="
echo ""
echo "Next steps:"
echo "  1. Review/edit resources/configuration.json"
echo "  2. Make run script executable: chmod +x scripts/run.sh"
echo "  3. Run the service with: ./scripts/run.sh"
echo "  4. Test with: curl http://localhost:PORT/api/health"
echo ""

# OS-specific autostart instructions
if [[ "$OSTYPE" == "darwin"* ]]; then
  echo "For auto-startup on macOS:"
  echo "  1. Edit deployment/com.service.plist (update paths)"
  echo "  2. cp deployment/com.service.plist ~/Library/LaunchAgents/"
  echo "  3. launchctl load ~/Library/LaunchAgents/com.service.plist"
  echo ""
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
  echo "For auto-startup on Linux (systemd):"
  echo "  1. Edit deployment/service.service (update paths and user)"
  echo "  2. sudo cp deployment/service.service /etc/systemd/system/youtube-downloader.service"
  echo "  3. sudo systemctl enable youtube-downloader"
  echo "  4. sudo systemctl start youtube-downloader"
  echo ""
fi
