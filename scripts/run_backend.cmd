@echo off
setlocal
set "ROOT=%~dp0.."
pushd "%ROOT%\backend"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
) else (
  echo Backend environment not found. Run scripts\setup_windows.cmd first.
  popd
  exit /b 1
)
popd
