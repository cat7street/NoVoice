$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "==> Use existing release exe (build beforehand if missing)"
$exeSrc = Join-Path (Get-Location) "src-tauri\target\release\novoice-tauri.exe"
if (-not (Test-Path $exeSrc)) {
  Write-Host "exe missing, building..."
  $env:CI = "true"
  pnpm install --config.confirmModulesPurge=false
  cargo build --manifest-path src-tauri/Cargo.toml --release
}
if (-not (Test-Path $exeSrc)) { throw "missing $exeSrc" }

$out = Join-Path (Get-Location) "release\NoVoice-Full"
if (Test-Path $out) { Remove-Item $out -Recurse -Force }
New-Item -ItemType Directory -Force -Path $out | Out-Null

Write-Host "==> Copy exe"
Copy-Item $exeSrc (Join-Path $out "NoVoice.exe") -Force

Write-Host "==> Copy models"
Copy-Item -Recurse "models" (Join-Path $out "models") -Force

Write-Host "==> Copy ffmpeg"
$ffdir = Join-Path $out "runtime\ffmpeg"
New-Item -ItemType Directory -Force -Path $ffdir | Out-Null
$ffmpegBin = Split-Path (Get-Command ffmpeg).Source -Parent
Copy-Item (Join-Path $ffmpegBin "ffmpeg.exe") $ffdir -Force
Copy-Item (Join-Path $ffmpegBin "ffprobe.exe") $ffdir -Force

Write-Host "==> Copy python runtime (.venv)"
$pyOut = Join-Path $out "runtime\python"
New-Item -ItemType Directory -Force -Path $pyOut | Out-Null
# copy whole venv tree into runtime/python, preserving Scripts/Lib/etc
robocopy ".venv" $pyOut /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy venv failed: $LASTEXITCODE" }

# App accepts runtime/python/python.exe or Scripts/python.exe via fallbacks.
if (-not (Test-Path (Join-Path $pyOut "python.exe")) -and (Test-Path (Join-Path $pyOut "Scripts\python.exe"))) {
  Copy-Item (Join-Path $pyOut "Scripts\python.exe") (Join-Path $pyOut "python.exe") -Force
  if (Test-Path (Join-Path $pyOut "Scripts\pythonw.exe")) {
    Copy-Item (Join-Path $pyOut "Scripts\pythonw.exe") (Join-Path $pyOut "pythonw.exe") -Force
  }
}

@'
NoVoice 完整包
作者: cat7street
开源: https://github.com/cat7street/NoVoice

使用方法
1. 解压后双击 NoVoice.exe（无黑色终端）
2. 拖入视频，点开始处理
3. 处理完成后可直接在内置播放器查看

目录说明
- NoVoice.exe
- models/          Demucs 模型
- runtime/ffmpeg/  内置 ffmpeg/ffprobe
- runtime/python/  内置 Python + Demucs

注意
- 完整包体积较大（约数 GB）
- 首次分离可能会稍慢（加载模型）
'@ | Set-Content -Encoding UTF8 (Join-Path $out "使用说明.txt")

Write-Host "==> Package folder ready:" $out
Get-ChildItem $out | Format-Table Name,Mode
Write-Host "Done"
