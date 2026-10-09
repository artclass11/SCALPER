@echo off
setlocal
cd /d "%~dp0\.."
if not exist .venv (
  py -3.11 -m venv .venv
  if errorlevel 1 exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -e ".[dev,mcp]"
if errorlevel 1 exit /b 1
echo Starting SCALPER on http://127.0.0.1:8000
scalper
