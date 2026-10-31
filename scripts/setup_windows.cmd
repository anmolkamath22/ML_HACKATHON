@echo off
setlocal
set "ROOT=%~dp0.."
echo Setting up Sketch2Shape AI for Windows...
rem Prefer the py launcher: winget/python.org installs often leave "python" off PATH or
rem pointing at the Microsoft Store placeholder.
set "PYEXE="
py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PYEXE=py -3"
if not defined PYEXE (
  python -c "import sys" >nul 2>nul
  if not errorlevel 1 set "PYEXE=python"
)
if not defined PYEXE (
  echo Python 3.10+ was not found. Install it with:  winget install --id Python.Python.3.10
  exit /b 1
)
%PYEXE% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
  echo Python 3.10 or newer is required.
  exit /b 1
)
where npm.cmd >nul 2>nul
if errorlevel 1 (
  echo npm was not found. Install Node.js 20+ and restart this terminal.
  exit /b 1
)
node -e "const v=process.versions.node.split('.').map(Number); process.exit(v[0]>=20?0:1)"
if errorlevel 1 (
  echo Node.js 20 or newer is required.
  exit /b 1
)
if not exist "%ROOT%\backend\.venv\Scripts\python.exe" (
  %PYEXE% -m venv "%ROOT%\backend\.venv"
  if errorlevel 1 exit /b 1
)
"%ROOT%\backend\.venv\Scripts\python.exe" -m pip install -r "%ROOT%\backend\requirements.txt"
if errorlevel 1 exit /b 1
if not exist "%ROOT%\backend\.env" copy "%ROOT%\backend\.env.example" "%ROOT%\backend\.env" >nul
pushd "%ROOT%\frontend"
call npm.cmd ci --cache "%ROOT%\frontend\.npm-cache" --no-audit --no-fund
set "RESULT=%ERRORLEVEL%"
popd
if not "%RESULT%"=="0" (
  echo.
  echo Frontend setup failed. Read the first npm error above; Python setup completed.
  echo npm ci replaces node_modules from the lockfile on every setup run.
  echo If the error names esbuild.exe as an invalid application, check Windows architecture
  echo and security software, then rerun setup and inspect the npm debug log if it persists.
  exit /b %RESULT%
)
echo Setup complete.
echo Next on a computer with an NVIDIA GPU: scripts\setup_instantmesh_windows.cmd, then scripts\warmup_models.cmd
echo Start the app: scripts\serve.cmd  (or scripts\serve.cmd --public for a link that works on any network)
