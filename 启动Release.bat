@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if exist "配置环境并启动.bat" (
  call "配置环境并启动.bat"
  exit /b %ERRORLEVEL%
)

if exist "release\NoVoice\NoVoice.exe" (
  start "" "release\NoVoice\NoVoice.exe"
  exit /b 0
)

if exist "src-tauri\target\release\novoice-tauri.exe" (
  start "" "src-tauri\target\release\novoice-tauri.exe"
  exit /b 0
)

echo No release exe. Run: powershell -ExecutionPolicy Bypass -File scripts\build-release.ps1
pause
