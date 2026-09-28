@echo off
rem Start the OpenJev local AI server
setlocal

cd /d "%~dp0jev-server" || goto error

if not exist venv\Scripts\python.exe (
  echo Creating virtual environment...
  python -m venv venv
)

call venv\Scripts\activate.bat
echo Installing/Verifying dependencies...
call pip install -r requirements.txt || goto error

echo Starting OpenJev AI Server on ws://localhost:8000 ...
python server.py || goto error
pause
exit /b 0

:error
echo.
echo [ERROR] The script encountered an error and stopped.
pause
exit /b 1
