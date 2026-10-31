@echo off
setlocal
set "ROOT=%~dp0.."
if not exist "%ROOT%\backend\.venv\Scripts\python.exe" (
  py -3 -m venv "%ROOT%\backend\.venv"
  if errorlevel 1 exit /b 1
)
"%ROOT%\backend\.venv\Scripts\python.exe" -m pip install -r "%ROOT%\backend\requirements.txt"
if errorlevel 1 exit /b 1
if not exist "%ROOT%\backend\.env" copy "%ROOT%\backend\.env.example" "%ROOT%\backend\.env" >nul
pushd "%ROOT%\frontend"
call npm.cmd install
set "RESULT=%ERRORLEVEL%"
popd
if not "%RESULT%"=="0" exit /b %RESULT%
echo Setup complete. Use run_backend.cmd and run_frontend.cmd in separate terminals.
