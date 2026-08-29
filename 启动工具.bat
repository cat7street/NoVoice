@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where pnpm >nul 2>&1
if errorlevel 1 (
  echo 未找到 pnpm，请先安装 Node.js 后再执行: npm i -g pnpm
  pause
  exit /b 1
)

if not exist "node_modules" (
  echo 正在安装前端依赖...
  set CI=true
  pnpm install --config.confirmModulesPurge=false
)

echo 启动 Tauri（会自动拉起前端，请等待窗口出现）...
pnpm tauri dev
if errorlevel 1 (
  echo.
  echo 启动失败，请把上面的错误信息反馈给开发者。
  pause
)
