@echo off
setlocal
set "ROOT=%~dp0.."
if not defined FRONTEND_HOST set "FRONTEND_HOST=127.0.0.1"
if not defined FRONTEND_PORT set "FRONTEND_PORT=5173"
pushd "%ROOT%\frontend"
if not exist "node_modules\vite\bin\vite.js" (
  echo Frontend packages not found. Run scripts\setup_windows.cmd first.
  popd
  exit /b 1
)
call npm.cmd run dev -- --host "%FRONTEND_HOST%" --port "%FRONTEND_PORT%"
popd
