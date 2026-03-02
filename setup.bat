@echo off
REM Laundry Reconciler — Local Setup Script (Windows)

echo ========================================
echo  Laundry Reconciler - Local Setup
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.9+ from https://www.python.org/downloads/
    exit /b 1
)

REM Create virtual environment
echo [1/4] Creating virtual environment...
if not exist venv (
    python -m venv venv
    echo       Virtual environment created.
) else (
    echo       Virtual environment already exists.
)

REM Activate
echo [2/4] Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo [3/4] Installing dependencies...
pip install -r requirements.txt --quiet

REM Initialize database
echo [4/4] Initializing database...
python -m src.cli init-db

echo.
echo ========================================
echo  Setup complete!
echo.
echo  Usage:
echo    streamlit run src/ui/app.py --server.address localhost  (Web UI)
echo    python -m src.cli --help             (CLI)
echo    pytest tests/ -v                     (Tests)
echo ========================================
