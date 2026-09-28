@echo off
rem Start the OpenJev local AI server
setlocal

cd /d "%~dp0jev-server" || exit /b 1

if not exist venv\Scripts\python.exe (
  echo Creating virtual environment and installing dependencies...
  python -m venv venv
  call venv\Scripts\activate.bat
  call pip install -r requirements.txt || exit /b 1
) else (
  call venv\Scripts\activate.bat
)

echo Starting OpenJev AI Server on ws://localhost:8000 ...
python server.py
