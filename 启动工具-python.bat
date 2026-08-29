@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "VPY=.venv\Scripts\python.exe"

rem 优先使用 Python 3.10~3.12（依赖兼容性最好）
set "PY=python"
py -3.12 -V >nul 2>&1 && set "PY=py -3.12"
py -3.11 -V >nul 2>&1 && set "PY=py -3.11"
py -3.10 -V >nul 2>&1 && set "PY=py -3.10"

if not exist "%VPY%" (
  echo [1/4] 正在创建虚拟环境（用 %PY%）...
  %PY% -m venv .venv
  if not exist "%VPY%" (
    echo 创建虚拟环境失败：请先安装 Python 3.10 以上版本。https://www.python.org/downloads/
    pause
    exit /b 1
  )
)

echo [2/4] 检查 Python 依赖（首次安装需要几分钟，请耐心等待）...
"%VPY%" -c "import demucs" >nul 2>&1
if errorlevel 1 (
  nvidia-smi >nul 2>&1
  if not errorlevel 1 (
    echo   检测到 NVIDIA 显卡，安装 GPU 版 PyTorch（下载较大）...
    "%VPY%" -m pip install "torch==2.7.1+cu126" "torchaudio==2.7.1+cu126" --find-links https://mirrors.aliyun.com/pytorch-wheels/cu126/ -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 "%VPY%" -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu126
  )
  "%VPY%" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
  if errorlevel 1 (
    echo   镜像源安装失败，改用官方源重试...
    "%VPY%" -m pip install -r requirements.txt
  )
)

echo [3/4] 检查 AI 分离模型（本地 models 目录，缺失时自动下载）...
if not exist "models" mkdir "models"
set "MBASE=https://hf-mirror.com/Politrees/UVR_resources/resolve/main/models/Demucs/Demucs_v4"
for %%F in (htdemucs.yaml htdemucs_ft.yaml 955717e8-8726e21a.th 04573f0d-f3cf25b2.th 92cfc3b6-ef3bcb9c.th d12395a8-e57c48e6.th f7e0c4bc-ba3fe64a.th) do (
  if not exist "models\%%F" (
    echo   下载 %%F ...
    curl -sL --retry 3 -o "models\%%F" "%MBASE%/%%F"
  )
)

echo [4/4] 启动图形界面...
"%VPY%" vocal_remover_gui.py
if errorlevel 1 (
  echo.
  echo 程序异常退出，请把上面的错误信息反馈给开发者。
  pause
)
