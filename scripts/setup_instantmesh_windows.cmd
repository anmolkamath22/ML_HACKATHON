@echo off
rem One-time setup of the GPU part (InstantMesh + ControlNet) on Windows with an NVIDIA GPU.
rem Installs into third_party\ inside this project and points backend\.env at it.
rem Needs: NVIDIA driver, Python 3.10, Git, Visual Studio C++ Build Tools and the CUDA Toolkit
rem (the last two compile InstantMesh's nvdiffrast renderer on first use). About 10 GB of downloads.
setlocal EnableDelayedExpansion
set "ROOT=%~dp0.."
set "TP=%ROOT%\third_party"
set "REPO=%TP%\InstantMesh"
set "VENV=%TP%\instantmesh-venv"
set "PY=%VENV%\Scripts\python.exe"

echo [1/7] Checking the NVIDIA GPU...
where nvidia-smi >nul 2>nul
if errorlevel 1 (
  echo No NVIDIA driver found. Generate 3D needs an NVIDIA GPU with a current driver: https://www.nvidia.com/Download/index.aspx
  exit /b 1
)
set "GPU=" & set "MAJOR=0"
for /f "tokens=1,2 delims=," %%a in ('nvidia-smi --query-gpu^=name^,compute_cap --format^=csv^,noheader') do (
  set "GPU=%%a"
  for /f "tokens=1 delims=. " %%m in ("%%b") do set "MAJOR=%%m"
)
echo       Found: !GPU! (compute capability major version !MAJOR!)
rem RTX 50-series GPUs (compute 12.x) need PyTorch built with CUDA 12.8; others use the
rem versions from the official InstantMesh README.
if !MAJOR! GEQ 12 (
  set "TORCH=torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cu128"
  set "XFORMERS="
) else (
  set "TORCH=torch==2.1.0 torchvision==0.16.0 torchaudio==2.1.0 --index-url https://download.pytorch.org/whl/cu121"
  set "XFORMERS=xformers==0.0.22.post7"
)

echo [2/7] Checking Python 3.10 and Git...
py -3.10 --version >nul 2>nul
if errorlevel 1 (
  echo Python 3.10 is required for InstantMesh. Install it, then rerun:  winget install --id Python.Python.3.10
  exit /b 1
)
where git >nul 2>nul
if errorlevel 1 (
  echo Git is required. Install it, then rerun:  winget install --id Git.Git
  exit /b 1
)

echo [3/7] Checking the C++ build tools and CUDA Toolkit...
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
set "HAS_VC="
if exist "%VSWHERE%" for /f "usebackq delims=" %%v in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "HAS_VC=1"
where nvcc >nul 2>nul
if errorlevel 1 if not defined CUDA_PATH set "NO_CUDA=1"
if not defined HAS_VC (
  echo Missing: Visual Studio C++ Build Tools. Install the "Desktop development with C++" workload:
  echo     winget install --id Microsoft.VisualStudio.2022.BuildTools --override "--add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --passive"
)
if defined NO_CUDA (
  echo Missing: NVIDIA CUDA Toolkit ^(12.1 for most GPUs, 12.8 for RTX 50^): https://developer.nvidia.com/cuda-toolkit-archive
)
if not defined HAS_VC if not defined SKIP_BUILD_TOOLS_CHECK (
  echo Install the missing tools, open a new terminal and rerun. To continue anyway: set SKIP_BUILD_TOOLS_CHECK=1
  exit /b 1
)
if defined NO_CUDA if not defined SKIP_BUILD_TOOLS_CHECK (
  echo Install the missing tools, open a new terminal and rerun. To continue anyway: set SKIP_BUILD_TOOLS_CHECK=1
  exit /b 1
)

echo [4/7] Getting the official InstantMesh code...
if not exist "%REPO%\run.py" (
  git clone --depth 1 https://github.com/TencentARC/InstantMesh.git "%REPO%"
  if errorlevel 1 exit /b 1
) else (
  echo       Already present: %REPO%
)

echo [5/7] Creating the Python 3.10 environment...
if not exist "%PY%" (
  py -3.10 -m venv "%VENV%"
  if errorlevel 1 exit /b 1
)
"%PY%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1

echo [6/7] Installing PyTorch, InstantMesh and ControlNet packages (large download)...
"%PY%" -m pip install !TORCH!
if errorlevel 1 exit /b 1
if defined XFORMERS (
  "%PY%" -m pip install !XFORMERS! --index-url https://download.pytorch.org/whl/cu121
  if errorlevel 1 echo       xformers could not be installed; continuing without it ^(slower, still works^).
)
"%PY%" -m pip install -r "%REPO%\requirements.txt"
if errorlevel 1 exit /b 1
"%PY%" -m pip install accelerate
if errorlevel 1 exit /b 1

echo [7/7] Configuring the backend and checking the GPU from the new environment...
"%PY%" "%ROOT%\scripts\configure_env.py" "INSTANTMESH_REPO=%REPO%" "INSTANTMESH_PYTHON=%PY%"
"%PY%" "%ROOT%\backend\inference_scripts\gpu_probe.py"
echo       Compiling the nvdiffrast renderer once (takes a few minutes the first time)...
"%PY%" -c "import torch, nvdiffrast.torch as dr; dr.RasterizeCudaContext(); print('nvdiffrast OK')"
if errorlevel 1 (
  echo nvdiffrast could not be compiled. Check the C++ Build Tools and CUDA Toolkit above, then rerun this script.
  exit /b 1
)
echo.
echo Done. Start the app with scripts\serve.cmd ^(same Wi-Fi^) or scripts\serve.cmd --public ^(any network^).
echo The first generation downloads the model weights ^(about 10 GB^) from Hugging Face.
