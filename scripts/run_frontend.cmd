@echo off
setlocal
set "ROOT=%~dp0.."
pushd "%ROOT%\frontend"
if not exist "node_modules\vite\bin\vite.js" (
  echo Frontend packages not found. Run scripts\setup_windows.cmd first.
  popd
  exit /b 1
)
call npm.cmd run dev -- --host 127.0.0.1 --port 5173
popd
