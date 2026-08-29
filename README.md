# NoVoice · 视频去人声工具

作者：**cat7street**  
开源地址：https://github.com/cat7street/NoVoice

去掉视频里的人声（对白 / 演唱），**画面、字幕、章节、元数据不受影响**。  
桌面端基于 **Tauri 2 + React + Rust**，分离引擎复用 Demucs。

## 使用（推荐）

1. 安装 [FFmpeg](https://ffmpeg.org/) 并加入 PATH  
2. 双击 Release 包里的 `NoVoice.exe`（无黑色终端窗口）  
3. 拖入视频 → 开始处理 → 内置播放器查看结果

> Release 包会附带运行所需的 Python/Demucs 环境与模型目录说明。开发调试仍可用 `启动工具.bat`。

## 开发

```bash
pnpm install
pnpm tauri dev
```

构建 Release：

```bash
pnpm tauri build
```

产物通常在：

- `src-tauri/target/release/novoice-tauri.exe`
- `src-tauri/target/release/bundle/`

## 功能

- 拖放 / 批量处理
- 标准 / 高质量模型
- 全部音轨或仅第一条
- 后台处理，界面不卡死
- 内置播放器，完成后可直接播放
- 打开输出目录

## License

MIT
