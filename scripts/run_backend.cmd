@echo off
setlocal
set "ROOT=%~dp0.."
if not defined BACKEND_HOST set "BACKEND_HOST=127.0.0.1"
if not defined BACKEND_PORT set "BACKEND_PORT=8000"
pushd "%ROOT%\backend"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host "%BACKEND_HOST%" --port "%BACKEND_PORT%"
) else (
  echo Backend environment not found. Run scripts\setup_windows.cmd first.
  popd
  exit /b 1
)
popd
