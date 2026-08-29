$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "[1/3] Build frontend + Tauri release..."
$env:CI = "true"
pnpm install --config.confirmModulesPurge=false
pnpm tauri build

$exe = Join-Path (Get-Location) "src-tauri\target\release\novoice-tauri.exe"
if (-not (Test-Path $exe)) { throw "Release exe not found: $exe" }

$out = Join-Path (Get-Location) "release\NoVoice"
New-Item -ItemType Directory -Force -Path $out | Out-Null
Copy-Item $exe (Join-Path $out "NoVoice.exe") -Force

# portable runtime stubs/docs
@"
NoVoice Release
作者: cat7street
开源: https://github.com/cat7street/NoVoice

使用前请确保本机已安装 FFmpeg 并加入 PATH。
双击 NoVoice.exe 即可，不会弹出黑色终端窗口。
"@ | Set-Content -Encoding UTF8 (Join-Path $out "使用说明.txt")

Write-Host "[2/3] Release folder:" $out
Get-ChildItem $out | Format-Table Name,Length
Write-Host "[3/3] Done"
