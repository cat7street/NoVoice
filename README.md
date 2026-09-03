# NoVoice · 视频去人声工具

作者：**cat7street**  
开源地址：https://github.com/cat7street/NoVoice

去掉视频里的人声（对白 / 演唱），**画面、字幕、章节、元数据不受影响**。  
枪声、脚步、环境音和环绕声道尽量从原轨保留，而不是用 AI 重建伴奏。  
三种模式：标准 / 高质量 / 超高质量（叠标准补游戏短喊）。  
桌面端基于 **Tauri 2 + React + Rust**，人声估计复用 Demucs。

## 给别人用（推荐）

发小安装包 `release\NoVoice-Setup.exe`（约 **2.8MB**，微信能发）。

对方：
1. 双击安装到任意目录（默认 `%LOCALAPPDATA%\NoVoice`）
2. 桌面快捷方式指向 `bootstrap-and-run.bat`
3. **首次运行**会自动：建 venv → 装 PyTorch/Demucs → 下模型 → 启动 GUI
4. 之后双击快捷方式秒开

也可用：`配置环境并启动.bat`（开发目录首次配环境）。

## 开发

```bash
pnpm install
pnpm tauri dev
```

构建瘦 Release：

```bash
powershell -ExecutionPolicy Bypass -File scripts\build-release.ps1
```

构建小安装包：

```bash
# 需先有 release\NoVoice\NoVoice.exe
& "$env:LOCALAPPDATA\tauri\NSIS\makensis.exe" scripts\NoVoice-Setup.nsi
```

## 注意

- 完整 5GB+ 包不要用 NSIS（会 mmapping 失败）；完整分发用 7z 分卷或网盘。
- `models/*.th` 不入库；首次由 bootstrap 自动下载。

## License

MIT
