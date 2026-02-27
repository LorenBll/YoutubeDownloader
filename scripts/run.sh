#!/bin/bash

# YouTube Downloader - Run Script
# This script sets up the environment and starts the service

VERBOSE=0
if [ "$1" = "--verbose" ]; then
  VERBOSE=1
fi

# Navigate to project root (parent of scripts directory)
cd "$(dirname "$0")/.." || exit 1
PROJECT_ROOT=$(pwd)

if [ $VERBOSE -eq 1 ]; then
  echo ""
  echo "==============================================="
  echo "  YouTube Downloader - Starting"
  echo "==============================================="
  echo ""
fi

# Check if Python is available
if ! command -v python3 &> /dev/null; then
  if [ $VERBOSE -eq 1 ]; then
    echo "[ERROR] Python 3 is not installed or not on PATH."
  fi
  exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
  if [ $VERBOSE -eq 1 ]; then
    echo "[*] Creating virtual environment..."
  fi
  python3 -m venv .venv
  if [ $? -ne 0 ]; then
    if [ $VERBOSE -eq 1 ]; then
      echo "[ERROR] Failed to create virtual environment."
    fi
    exit 1
  fi
  if [ $VERBOSE -eq 1 ]; then
    echo "[OK] Virtual environment created."
  fi
fi

# Activate virtual environment
source .venv/bin/activate
if [ $? -ne 0 ]; then
  if [ $VERBOSE -eq 1 ]; then
    echo "[ERROR] Failed to activate virtual environment."
  fi
  exit 1
fi
if [ $VERBOSE -eq 1 ]; then
  echo "[OK] Virtual environment activated."
fi

# Install/upgrade dependencies
if [ $VERBOSE -eq 1 ]; then
  echo "[*] Installing dependencies..."
fi
python -m pip install --quiet --upgrade pip > /dev/null 2>&1
if [ $? -ne 0 ]; then
  if [ $VERBOSE -eq 1 ]; then
    echo "[ERROR] Failed to upgrade pip."
  fi
  exit 1
fi

python -m pip install --quiet -r requirements.txt > /dev/null 2>&1
if [ $? -ne 0 ]; then
  if [ $VERBOSE -eq 1 ]; then
    echo "[ERROR] Failed to install requirements."
  fi
  exit 1
fi
if [ $VERBOSE -eq 1 ]; then
  echo "[OK] Dependencies installed."
fi

if [ $VERBOSE -eq 1 ]; then
  echo ""
  echo "==============================================="
  echo ""
  echo "  Starting YouTube Downloader API..."
  echo ""
  python src/main.py
else
  nohup python src/main.py > /dev/null 2>&1 &
  if [ $? -ne 0 ]; then
    echo ""
    echo "[!] Failed to start YouTube Downloader."
    echo ""
    exit 1
  fi
  echo ""
  echo "[*] YouTube Downloader started in background"
  echo "    Use './run.sh --verbose' to see output"
  echo ""
fi
