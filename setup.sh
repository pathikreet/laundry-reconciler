#!/usr/bin/env bash
# Laundry Reconciler — Local Setup Script (macOS / Linux)

set -e

echo "========================================"
echo " Laundry Reconciler - Local Setup"
echo "========================================"
echo

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed."
    echo "Please install Python 3.9+ from https://www.python.org/downloads/"
    exit 1
fi

# Create virtual environment
echo "[1/4] Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "      Virtual environment created."
else
    echo "      Virtual environment already exists."
fi

# Activate
echo "[2/4] Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "[3/4] Installing dependencies..."
pip install -r requirements.txt --quiet

# Initialize database
echo "[4/4] Initializing database..."
python -m src.cli init-db

echo
echo "========================================"
echo " Setup complete!"
echo
echo " Usage:"
echo "   streamlit run src/ui/app.py --server.address localhost  (Web UI)"
echo "   python -m src.cli --help             (CLI)"
echo "   pytest tests/ -v                     (Tests)"
echo "========================================"
