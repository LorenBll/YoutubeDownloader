#!/usr/bin/env sh
set -e

VERBOSE=0
if [ "$1" = "--verbose" ]; then
  VERBOSE=1
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")"; pwd)
cd "$SCRIPT_DIR"

if [ $VERBOSE -eq 1 ]; then
  echo ""
  echo "========================================"
  echo "  YoutubeDownloader Setup"
  echo "========================================"
  echo ""
fi

# Find Python executable
PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  if [ $VERBOSE -eq 1 ]; then
    echo "[ERROR] Python is not installed or not on PATH." >&2
    echo ""
  fi
  exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
  if [ $VERBOSE -eq 1 ]; then
    echo "[*] Creating virtual environment..."
  fi
  "$PYTHON_BIN" -m venv .venv
  if [ $VERBOSE -eq 1 ]; then
    echo "[OK] Virtual environment created."
  fi
else
  if [ $VERBOSE -eq 1 ]; then
    echo "[OK] Virtual environment already exists."
  fi
fi

# Activate virtual environment
. ./.venv/bin/activate

# Install dependencies
if [ $VERBOSE -eq 1 ]; then
  echo ""
  echo "[*] Installing dependencies..."
  python -m pip install --quiet --upgrade pip
  python -m pip install --quiet -r requirements.txt
  echo "[OK] Dependencies installed."
  echo ""
else
  python -m pip install --quiet --upgrade pip 2>/dev/null || true
  python -m pip install --quiet -r requirements.txt 2>/dev/null || true
fi

# Run the application
if [ $VERBOSE -eq 1 ]; then
  echo "========================================"
  echo "Starting YoutubeDownloader API..."
  echo "========================================"
  echo ""
  python src/main.py
else
  nohup python src/main.py >/dev/null 2>&1 &
  echo "Service started in background. Use './run.sh --verbose' to see output."
fi
