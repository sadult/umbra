@echo off
rem Builds a standalone Umbra.exe in dist\Umbra
cd /d "%~dp0"
if exist .venv call .venv\Scripts\activate.bat
pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --name Umbra ^
  --icon umbra\assets\umbra.ico ^
  --add-data "umbra\assets;umbra\assets" ^
  --collect-all sounddevice --collect-all soundfile --collect-data yt_dlp ^
  main.py
echo.
echo Done: dist\Umbra\Umbra.exe
pause
