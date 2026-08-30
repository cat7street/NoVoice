# -*- coding: utf-8 -*-
import os
import sys
import subprocess
import threading
import queue
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except Exception as e:
    print("tkinter missing:", e)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent
VPY = ROOT / ".venv" / "Scripts" / "python.exe"
EXE = ROOT / "NoVoice.exe"
MARKER = ROOT / ".env_ready"
MODELS = ROOT / "models"
MODEL_BASE = "https://hf-mirror.com/Politrees/UVR_resources/resolve/main/models/Demucs/Demucs_v4"
MODEL_FILES = [
    "htdemucs.yaml",
    "htdemucs_ft.yaml",
    "955717e8-8726e21a.th",
    "04573f0d-f3cf25b2.th",
    "92cfc3b6-ef3bcb9c.th",
    "d12395a8-e57c48e6.th",
    "f7e0c4bc-ba3fe64a.th",
]


class SetupApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("NoVoice 首次配置")
        self.root.geometry("520x280")
        self.root.resizable(False, False)
        self.root.configure(bg="#111827")
        try:
            self.root.iconbitmap(default=str(ROOT / "NoVoice.exe"))
        except Exception:
            pass

        self.status = tk.StringVar(value="准备开始…")
        self.detail = tk.StringVar(value="首次启动需要安装 Python 依赖并下载模型，请稍候。")
        self.progress = tk.DoubleVar(value=0)

        title = tk.Label(self.root, text="NoVoice 环境配置", fg="#f9fafb", bg="#111827",
                         font=("Microsoft YaHei UI", 14, "bold"))
        title.pack(anchor="w", padx=20, pady=(18, 6))

        tk.Label(self.root, textvariable=self.status, fg="#93c5fd", bg="#111827",
                 font=("Microsoft YaHei UI", 11)).pack(anchor="w", padx=20)
        tk.Label(self.root, textvariable=self.detail, fg="#9ca3af", bg="#111827",
                 font=("Microsoft YaHei UI", 9), wraplength=480, justify="left").pack(anchor="w", padx=20, pady=(4, 12))

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Blue.Horizontal.TProgressbar", troughcolor="#1f2937", background="#3b82f6", thickness=16)
        self.bar = ttk.Progressbar(self.root, style="Blue.Horizontal.TProgressbar",
                                   maximum=100, variable=self.progress, mode="determinate", length=480)
        self.bar.pack(padx=20, pady=8)

        self.log = tk.Text(self.root, height=6, bg="#0b1220", fg="#d1d5db", insertbackground="#d1d5db",
                           relief="flat", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=20, pady=(4, 16))
        self.log.configure(state="disabled")

        self.root.after(200, self.start)

    def set_progress(self, value, status=None, detail=None):
        def _():
            self.progress.set(max(0, min(100, value)))
            if status:
                self.status.set(status)
            if detail:
                self.detail.set(detail)
        self.root.after(0, _)

    def append(self, text):
        def _():
            self.log.configure(state="normal")
            self.log.insert("end", text + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(0, _)

    def which(self, name):
        from shutil import which
        return which(name)

    def pick_python(self):
        for ver in ("3.12", "3.11", "3.10"):
            try:
                r = subprocess.run(["py", f"-{ver}", "-V"], capture_output=True, text=True)
                if r.returncode == 0:
                    return ["py", f"-{ver}"]
            except Exception:
                pass
        return ["python"]

    def run_cmd(self, args, env=None):
        self.append("> " + " ".join(map(str, args)))
        p = subprocess.Popen(args, cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace")
        assert p.stdout is not None
        for line in p.stdout:
            line = line.rstrip()
            if line:
                self.append(line)
        code = p.wait()
        if code != 0:
            raise RuntimeError(f"命令失败({code}): {' '.join(map(str, args))}")

    def ensure_venv(self):
        self.set_progress(5, "1/4 创建虚拟环境", "正在创建本地 Python 环境…")
        if VPY.exists():
            self.append("venv 已存在")
            return
        py = self.pick_python()
        self.run_cmd(py + ["-m", "venv", ".venv"])
        if not VPY.exists():
            raise RuntimeError("创建虚拟环境失败，请先安装 Python 3.10+")

    def ensure_deps(self):
        self.set_progress(20, "2/4 安装依赖", "正在检查 / 安装 PyTorch 与 Demucs…")
        check = subprocess.run([str(VPY), "-c", "import demucs"], cwd=str(ROOT), capture_output=True)
        if check.returncode == 0:
            self.append("demucs 已安装")
            self.set_progress(55)
            return
        has_nvidia = subprocess.run(["nvidia-smi"], capture_output=True).returncode == 0
        if has_nvidia:
            self.append("检测到 NVIDIA，安装 GPU 版 PyTorch")
            try:
                self.run_cmd([str(VPY), "-m", "pip", "install", "torch==2.7.1+cu126", "torchaudio==2.7.1+cu126",
                              "--find-links", "https://mirrors.aliyun.com/pytorch-wheels/cu126/",
                              "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"])
            except Exception:
                self.run_cmd([str(VPY), "-m", "pip", "install", "torch", "torchaudio",
                              "--index-url", "https://download.pytorch.org/whl/cu126"])
        else:
            self.append("未检测到 NVIDIA，安装 CPU 版 PyTorch")
            self.run_cmd([str(VPY), "-m", "pip", "install", "torch", "torchaudio",
                          "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"])
        self.set_progress(40, detail="正在安装 demucs / soundfile…")
        try:
            self.run_cmd([str(VPY), "-m", "pip", "install", "demucs", "soundfile",
                          "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"])
        except Exception:
            self.run_cmd([str(VPY), "-m", "pip", "install", "demucs", "soundfile"])
        self.set_progress(55)

    def ensure_models(self):
        self.set_progress(60, "3/4 下载模型", "正在检查 AI 模型文件…")
        MODELS.mkdir(parents=True, exist_ok=True)
        missing = [f for f in MODEL_FILES if not (MODELS / f).exists()]
        if not missing:
            self.append("模型已齐全")
            self.set_progress(85)
            return
        total = len(missing)
        for i, name in enumerate(missing, 1):
            self.set_progress(60 + 20 * i / total, detail=f"下载模型 {name} ({i}/{total})")
            url = f"{MODEL_BASE}/{name}"
            out = MODELS / name
            self.run_cmd(["curl", "-sL", "--retry", "3", "-o", str(out), url])
            if not out.exists() or out.stat().st_size < 10:
                raise RuntimeError(f"模型下载失败: {name}")
        self.set_progress(85)

    def ensure_ffmpeg(self):
        self.set_progress(90, "4/4 检查 FFmpeg", "正在检查 FFmpeg…")
        if self.which("ffmpeg"):
            self.append("FFmpeg 已在 PATH")
            return
        local = ROOT / "runtime" / "ffmpeg" / "ffmpeg.exe"
        if local.exists():
            os.environ["PATH"] = str(local.parent) + os.pathsep + os.environ.get("PATH", "")
            self.append("使用本地 runtime/ffmpeg")
            return
        raise RuntimeError("未找到 FFmpeg。请执行: winget install Gyan.FFmpeg")

    def work(self):
        try:
            self.ensure_venv()
            self.ensure_deps()
            self.ensure_models()
            self.ensure_ffmpeg()
            MARKER.write_text("ready\n", encoding="utf-8")
            self.set_progress(100, "配置完成", "即将启动 NoVoice…")
            self.append("done")
            if EXE.exists():
                subprocess.Popen([str(EXE)], cwd=str(ROOT))
                self.root.after(600, self.root.destroy)
            else:
                self.root.after(0, lambda: messagebox.showerror("错误", "未找到 NoVoice.exe"))
        except Exception as e:
            self.append(str(e))
            self.set_progress(self.progress.get(), "配置失败", str(e))
            self.root.after(0, lambda: messagebox.showerror("配置失败", str(e)))

    def start(self):
        threading.Thread(target=self.work, daemon=True).start()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    # if already configured, just launch
    if MARKER.exists() and EXE.exists():
        subprocess.Popen([str(EXE)], cwd=str(ROOT))
        sys.exit(0)
    SetupApp().run()
