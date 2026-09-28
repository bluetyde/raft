@echo off
rem Start RAFT (Reactor Agnostic Framework for Testing) in the browser: installs the web dependencies if needed, starts the dev server and opens the page.
rem Port: VR_PORT if set, else 5187 (docs/WORKFLOWS.md section 0). Stop it with Ctrl+C in this window.
setlocal
if "%VR_PORT%"=="" set VR_PORT=5187
cd /d "%~dp0web" || exit /b 1
if not exist node_modules\.bin\vite.cmd (
  echo Installing web dependencies ^(first run only^)...
  call npm ci --ignore-scripts || exit /b 1
)
start "" "http://localhost:%VR_PORT%/"
call npm run dev
