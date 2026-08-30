# -*- coding: utf-8 -*-
import os
import re
import sys
import subprocess
import threading
import urllib.request
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import messagebox
except Exception as e:
    print("tkinter missing:", e)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent
VPY = ROOT / ".venv" / "Scripts" / "python.exe"
EXE = ROOT / "NoVoice.exe"
MARKER = ROOT / ".env_ready"
MODELS = ROOT / "models"
ICON = ROOT / "NoVoice.exe"
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

BG = "#111827"
PANEL = "#1f2937"
TEXT = "#e5e7eb"
MUTED = "#9ca3af"
LINE = "#374151"
ACCENT = "#3b82f6"
OK = "#22c55e"
PIP_SIZE = re.compile(r"(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)\s*(kB|MB|GB|KiB|MiB|GiB)", re.I)
PIP_PCT = re.compile(r"(\d{1,3})%")


class SetupApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("NoVoice")
        self.root.geometry("560x320")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)
        self.root.minsize(560, 320)
        try:
            self.root.iconbitmap(default=str(ICON))
        except Exception:
            pass

        self.step = tk.StringVar(value="准备开始")
        self.detail = tk.StringVar(value="首次启动会配置运行环境，只需这一次。")
        self.percent = tk.StringVar(value="0%")
        self.show_log = False
        self._progress = 0.0
        self._shown = 0.0
        self._shimmer = 0.0
        self._pulse = 0.0
        self._active_step = -1
        self._log_lines = []
        self._animating = True

        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True, padx=18, pady=16)

        head = tk.Frame(outer, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="NoVoice", fg=TEXT, bg=BG, font=("Microsoft YaHei UI", 16, "bold")).pack(anchor="w")
        tk.Label(head, text="正在准备运行环境", fg=MUTED, bg=BG, font=("Microsoft YaHei UI", 10)).pack(anchor="w", pady=(2, 12))

        self.steps_frame = tk.Frame(outer, bg=BG)
        self.steps_frame.pack(fill="x", pady=(0, 14))
        self.step_labels = []
        names = ["创建环境", "安装依赖", "下载模型", "检查工具"]
        for i, name in enumerate(names):
            lab = tk.Label(
                self.steps_frame,
                text=f"{i + 1}  {name}",
                fg=MUTED,
                bg=PANEL,
                font=("Microsoft YaHei UI", 9),
                padx=10,
                pady=6,
            )
            lab.pack(side="left", padx=(0 if i == 0 else 6, 0))
            self.step_labels.append(lab)

        card = tk.Frame(outer, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        card.pack(fill="x")
        inner = tk.Frame(card, bg=PANEL)
        inner.pack(fill="x", padx=14, pady=12)

        row = tk.Frame(inner, bg=PANEL)
        row.pack(fill="x")
        tk.Label(row, textvariable=self.step, fg=TEXT, bg=PANEL, font=("Microsoft YaHei UI", 11)).pack(side="left")
        tk.Label(row, textvariable=self.percent, fg=ACCENT, bg=PANEL, font=("Microsoft YaHei UI", 11)).pack(side="right")

        tk.Label(inner, textvariable=self.detail, fg=MUTED, bg=PANEL, font=("Microsoft YaHei UI", 9),
                 wraplength=500, justify="left").pack(anchor="w", pady=(4, 10))

        self.canvas = tk.Canvas(inner, height=10, bg=PANEL, highlightthickness=0, bd=0)
        self.canvas.pack(fill="x")
        self.canvas.bind("<Configure>", lambda _e: self._draw_bar())

        self.toggle = tk.Label(outer, text="显示详情", fg=MUTED, bg=BG, font=("Microsoft YaHei UI", 9), cursor="hand2")
        self.toggle.pack(anchor="w", pady=(10, 0))
        self.toggle.bind("<Button-1>", lambda _e: self._toggle_log())

        self.log = tk.Text(
            outer,
            height=7,
            bg="#0b1220",
            fg="#9ca3af",
            relief="flat",
            bd=0,
            font=("Consolas", 8),
            wrap="word",
        )
        self.log.configure(state="disabled")

        self.root.after(16, self._tick)
        self.root.after(180, self.start)

    def _draw_bar(self):
        self.canvas.delete("all")
        w = max(self.canvas.winfo_width(), 1)
        h = 10
        r = 5
        self.canvas.create_rectangle(0, 0, w, h, fill=PANEL, outline="")
        self._round_rect(0, 0, w, h, r, "#0f172a")
        fill = int(w * max(0.0, min(1.0, self._shown / 100.0)))
        if fill > 1:
            self._round_rect(0, 0, fill, h, r, ACCENT)
            if fill > 18:
                shine = int((self._shimmer % 1.0) * (fill + 40) - 20)
                self.canvas.create_rectangle(max(2, shine), 2, min(fill - 2, shine + 28), h - 2, fill="#93c5fd", outline="")
        self.percent.set(f"{int(self._shown)}%")

    def _round_rect(self, x1, y1, x2, y2, r, color):
        r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
        if x2 - x1 <= 0 or y2 - y1 <= 0:
            return
        self.canvas.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, fill=color, outline=color)
        self.canvas.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, fill=color, outline=color)
        self.canvas.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, fill=color, outline=color)
        self.canvas.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, fill=color, outline=color)
        self.canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=color, outline=color)
        self.canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=color, outline=color)

    def _tick(self):
        if not self._animating:
            return
        target = self._progress
        shown = self._shown
        delta = target - shown
        if abs(delta) < 0.08:
            shown = target
        else:
            shown += delta * 0.12
            if abs(delta) > 0.4:
                shown += 0.08 if delta > 0 else -0.08
        self._shown = max(0.0, min(100.0, shown))
        self._shimmer = (self._shimmer + 0.018) % 1.0
        self._pulse = (self._pulse + 0.045) % 6.283185307179586
        if self._active_step >= 0:
            self._paint_steps()
        self._draw_bar()
        self.root.after(16, self._tick)

    def _toggle_log(self):
        self.show_log = not self.show_log
        if self.show_log:
            self.toggle.configure(text="隐藏详情")
            self.log.pack(fill="both", expand=True, pady=(8, 0))
            self.root.geometry("560x460")
        else:
            self.toggle.configure(text="显示详情")
            self.log.pack_forget()
            self.root.geometry("560x320")

    def _paint_steps(self):
        idx = self._active_step
        pulse = 0.5 + 0.5 * __import__("math").sin(self._pulse)
        for i, lab in enumerate(self.step_labels):
            if i < idx:
                lab.configure(fg="#86efac", bg="#14532d")
            elif i == idx:
                lab.configure(fg="#eff6ff", bg="#1d4ed8" if pulse > 0.35 else "#1e40af")
            else:
                lab.configure(fg=MUTED, bg=PANEL)

    def _set_step(self, idx):
        self._active_step = idx
        self._paint_steps()

    def set_progress(self, value, status=None, detail=None, step=None):
        def _():
            self._progress = max(0.0, min(100.0, float(value)))
            if status:
                self.step.set(status)
            if detail:
                self.detail.set(detail)
            if step is not None:
                self._set_step(step)
        self.root.after(0, _)

    def append(self, text):
        line = (text or "").strip()
        if not line:
            return
        def _():
            self._log_lines.append(line)
            self.log.configure(state="normal")
            self.log.insert("end", line + "\n")
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

    def _human(self, n):
        n = float(n)
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024 or unit == "GB":
                return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
            n /= 1024
        return f"{n:.1f} GB"

    def _parse_pip_progress(self, line, base):
        m = PIP_SIZE.search(line)
        if m:
            cur, total, unit = m.group(1), m.group(2), m.group(3).upper()
            mul = {"KB": 1, "KIB": 1, "MB": 1024, "MIB": 1024, "GB": 1024 * 1024, "GIB": 1024 * 1024}.get(unit, 1)
            cur_k, total_k = float(cur) * mul, max(float(total) * mul, 1)
            pct = base + 30 * (cur_k / total_k)
            self.set_progress(pct, detail=f"正在下载  {cur} / {total} {unit}")
            return
        m = PIP_PCT.search(line)
        if m:
            self.set_progress(base + 30 * int(m.group(1)) / 100.0)

    def _emit_line(self, line, progress_base=None):
        line = (line or "").strip()
        if not line:
            return
        self.append(line)
        if progress_base is not None:
            self._parse_pip_progress(line, progress_base)

    def run_cmd(self, args, env=None, progress_base=None):
        cmd = list(args)
        merged = dict(os.environ)
        if env:
            merged.update(env)
        merged["PYTHONUNBUFFERED"] = "1"
        merged["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        if len(cmd) >= 3 and cmd[1] == "-m" and cmd[2] == "pip":
            if "--progress-bar" not in cmd:
                cmd.extend(["--progress-bar", "on"])
        self.append("> " + " ".join(map(str, cmd)))
        p = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            env=merged,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )
        assert p.stdout is not None
        buf = b""
        while True:
            chunk = p.stdout.read(256)
            if not chunk:
                break
            buf += chunk
            while True:
                n = buf.find(b"\n")
                r = buf.find(b"\r")
                if n < 0 and r < 0:
                    break
                if n < 0:
                    cut = r
                elif r < 0:
                    cut = n
                else:
                    cut = min(n, r)
                piece = buf[:cut].decode("utf-8", "replace")
                buf = buf[cut + 1 :]
                self._emit_line(piece, progress_base)
        if buf:
            self._emit_line(buf.decode("utf-8", "replace"), progress_base)
        code = p.wait()
        if code != 0:
            raise RuntimeError(f"命令失败 ({code})")

    def ensure_venv(self):
        self.set_progress(4, "创建虚拟环境", "正在创建本地 Python 环境…", step=0)
        if VPY.exists():
            self.append("venv 已存在")
            self.set_progress(18)
            return
        py = self.pick_python()
        self.run_cmd(py + ["-m", "venv", ".venv"])
        if not VPY.exists():
            raise RuntimeError("创建虚拟环境失败，请先安装 Python 3.10+")
        self.set_progress(18)

    def ensure_deps(self):
        self.set_progress(20, "安装依赖", "正在检查 PyTorch 与 Demucs…", step=1)
        check = subprocess.run([str(VPY), "-c", "import demucs"], cwd=str(ROOT), capture_output=True)
        if check.returncode == 0:
            self.append("demucs 已安装")
            self.set_progress(58)
            return
        has_nvidia = subprocess.run(["nvidia-smi"], capture_output=True).returncode == 0
        if has_nvidia:
            self.append("检测到 NVIDIA，安装 GPU 版 PyTorch")
            self.set_progress(22, detail="正在下载 GPU 版 PyTorch，体积较大…")
            try:
                self.run_cmd(
                    [str(VPY), "-m", "pip", "install", "torch==2.7.1+cu126", "torchaudio==2.7.1+cu126",
                     "--find-links", "https://mirrors.aliyun.com/pytorch-wheels/cu126/",
                     "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"],
                    progress_base=22,
                )
            except Exception:
                self.run_cmd(
                    [str(VPY), "-m", "pip", "install", "torch", "torchaudio",
                     "--index-url", "https://download.pytorch.org/whl/cu126"],
                    progress_base=22,
                )
        else:
            self.append("未检测到 NVIDIA，安装 CPU 版 PyTorch")
            self.set_progress(22, detail="正在下载 CPU 版 PyTorch…")
            self.run_cmd(
                [str(VPY), "-m", "pip", "install", "torch", "torchaudio",
                 "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"],
                progress_base=22,
            )
        self.set_progress(48, detail="正在安装 demucs / soundfile…")
        try:
            self.run_cmd(
                [str(VPY), "-m", "pip", "install", "demucs", "soundfile",
                 "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"],
                progress_base=48,
            )
        except Exception:
            self.run_cmd([str(VPY), "-m", "pip", "install", "demucs", "soundfile"], progress_base=48)
        self.set_progress(58)

    def _download(self, url, dest, base, span):
        tmp = dest.with_suffix(dest.suffix + ".part")

        def hook(block, block_size, total):
            got = block * block_size
            if total > 0:
                pct = base + span * min(1.0, got / total)
                self.set_progress(pct, detail=f"正在下载 {dest.name}  ·  {self._human(got)} / {self._human(total)}")
            else:
                self.set_progress(base + span * 0.5, detail=f"正在下载 {dest.name}  ·  {self._human(got)}")

        urllib.request.urlretrieve(url, tmp, hook)
        if not tmp.exists() or tmp.stat().st_size < 10:
            raise RuntimeError(f"模型下载失败: {dest.name}")
        tmp.replace(dest)

    def ensure_models(self):
        self.set_progress(60, "下载模型", "正在检查模型文件…", step=2)
        MODELS.mkdir(parents=True, exist_ok=True)
        missing = [f for f in MODEL_FILES if not (MODELS / f).exists()]
        if not missing:
            self.append("模型已齐全")
            self.set_progress(86)
            return
        total = len(missing)
        for i, name in enumerate(missing):
            base = 60 + 26 * i / total
            span = 26 / total
            self.set_progress(base, detail=f"下载模型 {name}  ({i + 1}/{total})")
            self._download(f"{MODEL_BASE}/{name}", MODELS / name, base, span)
        self.set_progress(86)

    def ensure_ffmpeg(self):
        self.set_progress(90, "检查工具", "正在检查 FFmpeg…", step=3)
        if self.which("ffmpeg"):
            self.append("FFmpeg 已在 PATH")
            return
        local = ROOT / "runtime" / "ffmpeg" / "ffmpeg.exe"
        if local.exists():
            os.environ["PATH"] = str(local.parent) + os.pathsep + os.environ.get("PATH", "")
            self.append("使用本地 runtime/ffmpeg")
            return
        raise RuntimeError("未找到 FFmpeg。请先执行：winget install Gyan.FFmpeg")

    def work(self):
        try:
            self.ensure_venv()
            self.ensure_deps()
            self.ensure_models()
            self.ensure_ffmpeg()
            MARKER.write_text("ready\n", encoding="utf-8")
            self.set_progress(100, "配置完成", "即将启动 NoVoice…", step=4)
            if EXE.exists():
                subprocess.Popen([str(EXE)], cwd=str(ROOT))
                self.root.after(700, self.root.destroy)
            else:
                self.root.after(0, lambda: messagebox.showerror("错误", "未找到 NoVoice.exe"))
        except Exception as e:
            self.append(str(e))
            self.set_progress(self._progress, "配置失败", str(e))
            self.root.after(0, lambda err=str(e): messagebox.showerror("配置失败", err))

    def start(self):
        threading.Thread(target=self.work, daemon=True).start()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    if MARKER.exists() and EXE.exists():
        subprocess.Popen([str(EXE)], cwd=str(ROOT))
        sys.exit(0)
    SetupApp().run()
