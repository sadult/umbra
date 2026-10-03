@echo off
cd /d "%~dp0"
if not exist .venv (
  echo Creating virtual environment...
  py -3 -m venv .venv
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)
start "" pythonw main.py %*
