@echo off
rem Download every model and run one real test generation on the GPU (after setup_instantmesh_windows.cmd).
setlocal
set "ROOT=%~dp0.."
set "PY="
if exist "%ROOT%\backend\.env" for /f "tokens=1,* delims==" %%a in ('findstr /b /c:"INSTANTMESH_PYTHON=" "%ROOT%\backend\.env"') do set "PY=%%b"
if not defined PY set "PY=%ROOT%\third_party\instantmesh-venv\Scripts\python.exe"
if not exist "%PY%" (
  echo The InstantMesh Python environment was not found. Run scripts\setup_instantmesh_windows.cmd first.
  exit /b 1
)
"%PY%" "%ROOT%\scripts\warmup_models.py"
