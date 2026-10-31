@echo off
rem Build the UI and serve it together with the API on one port.
rem   scripts\serve.cmd            anyone on the same Wi-Fi/LAN can open it
rem   scripts\serve.cmd --public   also creates a public https link that works on any
rem                                device and any network (Cloudflare quick tunnel)
setlocal
set "ROOT=%~dp0.."
if not defined SERVE_PORT set "SERVE_PORT=8000"
if not defined SERVE_HOST set "SERVE_HOST=0.0.0.0"
set "PUBLIC="
if /i "%~1"=="--public" set "PUBLIC=1"
if not exist "%ROOT%\backend\.venv\Scripts\python.exe" (
  echo Backend environment missing. Run scripts\setup_windows.cmd first.
  exit /b 1
)
if not exist "%ROOT%\frontend\node_modules\vite\bin\vite.js" (
  echo Frontend dependencies missing. Run scripts\setup_windows.cmd first.
  exit /b 1
)
if defined PUBLIC (
  where cloudflared >nul 2>nul
  if errorlevel 1 (
    echo A public link needs the free cloudflared tool. Install it once, open a new terminal, then rerun:
    echo     winget install --id Cloudflare.cloudflared
    echo Or download it from https://github.com/cloudflare/cloudflared/releases
    exit /b 1
  )
)
pushd "%ROOT%\frontend"
call npm.cmd run build
if errorlevel 1 (
  popd
  exit /b 1
)
popd
echo.
echo Sketch2Shape is starting.
echo   On this computer:   http://127.0.0.1:%SERVE_PORT%
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do for /f "tokens=*" %%b in ("%%a") do echo   Same Wi-Fi/LAN:     http://%%b:%SERVE_PORT%
if defined PUBLIC goto public
echo If Windows asks, allow Python through the firewall on private networks.
echo For a link that works on any network, run: scripts\serve.cmd --public
echo.
pushd "%ROOT%\backend"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host "%SERVE_HOST%" --port "%SERVE_PORT%"
popd
exit /b

:public
start "Sketch2Shape server (close this window to stop)" /d "%ROOT%\backend" ".venv\Scripts\python.exe" -m uvicorn app.main:app --host "%SERVE_HOST%" --port "%SERVE_PORT%"
echo.
echo   Public link:        wait for the https://....trycloudflare.com address below and share it.
echo                       It works from any phone or laptop on any Wi-Fi or mobile data while this
echo                       window and the server window stay open. Press Ctrl+C here to stop sharing.
echo.
cloudflared tunnel --url "http://127.0.0.1:%SERVE_PORT%"
