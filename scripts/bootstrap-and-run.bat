@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "VPY=.venv\Scripts\python.exe"
set "EXE=NoVoice.exe"

set "PY=python"
py -3.12 -V >nul 2>&1 && set "PY=py -3.12"
py -3.11 -V >nul 2>&1 && set "PY=py -3.11"
py -3.10 -V >nul 2>&1 && set "PY=py -3.10"

if not exist "%VPY%" (
  echo [1/4] Creating venv with %PY%...
  %PY% -m venv .venv
  if not exist "%VPY%" (
    echo Failed to create venv. Install Python 3.10+ first.
    echo https://www.python.org/downloads/
    pause
    exit /b 1
  )
)

echo [2/4] Checking Python deps (first run may take a few minutes)...
"%VPY%" -c "import demucs" >nul 2>&1
if errorlevel 1 (
  nvidia-smi >nul 2>&1
  if not errorlevel 1 (
    echo   NVIDIA GPU detected, installing GPU PyTorch...
    "%VPY%" -m pip install "torch==2.7.1+cu126" "torchaudio==2.7.1+cu126" --find-links https://mirrors.aliyun.com/pytorch-wheels/cu126/ -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 "%VPY%" -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu126
  ) else (
    echo   No NVIDIA GPU, installing CPU PyTorch...
    "%VPY%" -m pip install torch torchaudio -i https://pypi.tuna.tsinghua.edu.cn/simple
  )
  "%VPY%" -m pip install demucs soundfile -i https://pypi.tuna.tsinghua.edu.cn/simple
  if errorlevel 1 (
    echo   Mirror failed, retrying official PyPI...
    "%VPY%" -m pip install demucs soundfile
  )
)

echo [3/4] Checking AI models in models\ ...
if not exist "models" mkdir "models"
set "MBASE=https://hf-mirror.com/Politrees/UVR_resources/resolve/main/models/Demucs/Demucs_v4"
for %%F in (htdemucs.yaml htdemucs_ft.yaml 955717e8-8726e21a.th 04573f0d-f3cf25b2.th 92cfc3b6-ef3bcb9c.th d12395a8-e57c48e6.th f7e0c4bc-ba3fe64a.th) do (
  if not exist "models\%%F" (
    echo   Downloading %%F ...
    curl -sL --retry 3 -o "models\%%F" "%MBASE%/%%F"
  )
)

echo [4/4] Checking FFmpeg...
where ffmpeg >nul 2>&1
if errorlevel 1 (
  if exist "runtime\ffmpeg\ffmpeg.exe" (
    set "PATH=%~dp0runtime\ffmpeg;%PATH%"
  ) else (
    echo FFmpeg not found. Install with: winget install Gyan.FFmpeg
    echo Or put ffmpeg.exe + ffprobe.exe into runtime\ffmpeg\
    pause
    exit /b 1
  )
)

if exist "NoVoice.exe" (
  echo Starting GUI...
  start "" "NoVoice.exe"
  exit /b 0
)

echo NoVoice.exe not found in install directory.
pause
