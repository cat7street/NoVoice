@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if exist "release\NoVoice\NoVoice.exe" (
  start "" "release\NoVoice\NoVoice.exe"
  exit /b 0
)

if exist "src-tauri\target\release\novoice-tauri.exe" (
  start "" "src-tauri\target\release\novoice-tauri.exe"
  exit /b 0
)

echo 还没有 Release 可执行文件，请先运行: powershell -ExecutionPolicy Bypass -File scripts\build-release.ps1
pause
