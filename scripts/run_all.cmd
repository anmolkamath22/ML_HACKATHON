@echo off
setlocal
set "ROOT=%~dp0.."
if not defined BACKEND_PORT set "BACKEND_PORT=8000"
if not defined FRONTEND_PORT set "FRONTEND_PORT=5173"
if not exist "%ROOT%\backend\.venv\Scripts\python.exe" (
  echo Backend environment missing. Run scripts\setup_windows.cmd first.
  exit /b 1
)
if not exist "%ROOT%\frontend\node_modules\vite\bin\vite.js" (
  echo Frontend dependencies missing. Run scripts\setup_windows.cmd first.
  exit /b 1
)
where netstat >nul 2>nul
if errorlevel 1 (
  echo netstat is required to check server ports.
  exit /b 1
)
netstat -ano | findstr /r /c:":%BACKEND_PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo Backend port %BACKEND_PORT% is already in use.
  exit /b 1
)
netstat -ano | findstr /r /c:":%FRONTEND_PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo Frontend port %FRONTEND_PORT% is already in use.
  exit /b 1
)
start "Sketch2Shape Backend" cmd.exe /k ""%ROOT%\scripts\run_backend.cmd""
start "Sketch2Shape Frontend" cmd.exe /k ""%ROOT%\scripts\run_frontend.cmd""
echo Backend:  http://127.0.0.1:%BACKEND_PORT%
echo Swagger:  http://127.0.0.1:%BACKEND_PORT%/docs
echo Frontend: http://127.0.0.1:%FRONTEND_PORT%
