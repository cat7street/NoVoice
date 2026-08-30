# -*- coding: utf-8 -*-
import math
import os
import re
import sys
import subprocess
import threading
import time
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
CACHE = ROOT / ".cache"
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
PIPI = "https://pypi.tuna.tsinghua.edu.cn/simple"
TORCH_GPU = [
    "https://mirrors.aliyun.com/pytorch-wheels/cu126/torch-2.7.1%2Bcu126-cp312-cp312-win_amd64.whl",
    "https://download.pytorch.org/whl/cu126/torch-2.7.1%2Bcu126-cp312-cp312-win_amd64.whl",
]
TORCHAUDIO_GPU = [
    "https://mirrors.aliyun.com/pytorch-wheels/cu126/torchaudio-2.7.1%2Bcu126-cp312-cp312-win_amd64.whl",
    "https://download.pytorch.org/whl/cu126/torchaudio-2.7.1%2Bcu126-cp312-cp312-win_amd64.whl",
]

BG = "#111827"
PANEL = "#1f2937"
TEXT = "#e5e7eb"
MUTED = "#9ca3af"
LINE = "#374151"
ACCENT = "#3b82f6"
PIP_SIZE = re.compile(r"(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)\s*(kB|MB|GB|KiB|MiB|GiB)", re.I)
PIP_PCT = re.compile(r"(\d{1,3})%")


class SetupApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("NoVoice")
        self.root.geometry("560x320")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)
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
        self._busy_since = time.time()
        self._busy_floor = 0.0
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
            lab = tk.Label(self.steps_frame, text=f"{i + 1}  {name}", fg=MUTED, bg=PANEL,
                           font=("Microsoft YaHei UI", 9), padx=10, pady=6)
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

        self.log = tk.Text(outer, height=7, bg="#0b1220", fg="#9ca3af", relief="flat", bd=0,
                           font=("Consolas", 8), wrap="word")
        self.log.configure(state="disabled")

        self.root.after(16, self._tick)
        self.root.after(180, self.start)

    def _round_rect(self, x1, y1, x2, y2, r, color):
        r = min(r, max(0, (x2 - x1) / 2), max(0, (y2 - y1) / 2))
        if x2 - x1 <= 0 or y2 - y1 <= 0:
            return
        self.canvas.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, fill=color, outline=color)
        self.canvas.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, fill=color, outline=color)
        self.canvas.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, fill=color, outline=color)
        self.canvas.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, fill=color, outline=color)
        self.canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=color, outline=color)
        self.canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=color, outline=color)

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
            if fill > 24:
                shine = int((self._shimmer % 1.0) * (fill + 36) - 18)
                self.canvas.create_rectangle(max(2, shine), 2, min(fill - 2, shine + 26), h - 2, fill="#93c5fd", outline="")
        self.percent.set(f"{int(self._shown)}%")

    def _tick(self):
        if not self._animating:
            return
        # crawl a little while waiting so it never looks frozen
        elapsed = time.time() - self._busy_since
        crawl = self._busy_floor + min(6.0, elapsed * 0.12)
        target = max(self._progress, crawl if self._progress < 99 else self._progress)
        shown = self._shown
        delta = target - shown
        if abs(delta) < 0.05:
            shown = target
        else:
            shown += delta * 0.16
        self._shown = max(0.0, min(99.4 if self._progress < 100 else 100.0, shown))
        self._shimmer = (self._shimmer + 0.02) % 1.0
        self._pulse = (self._pulse + 0.05) % (math.pi * 2)
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
        pulse = 0.5 + 0.5 * math.sin(self._pulse)
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

    def set_progress(self, value, status=None, detail=None, step=None, crawl=False):
        def _():
            self._progress = max(0.0, min(100.0, float(value)))
            if crawl:
                self._busy_since = time.time()
                self._busy_floor = self._progress
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

    def py_tag(self):
        r = subprocess.run([str(VPY), "-c", "import sys; print(f'cp{sys.version_info.major}{sys.version_info.minor}')"],
                           capture_output=True, text=True)
        tag = (r.stdout or "").strip()
        return tag or "cp312"

    def _human(self, n):
        n = float(n)
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024 or unit == "GB":
                return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
            n /= 1024
        return f"{n:.1f} GB"

    def _download(self, url, dest, base, span, label=None):
        CACHE.mkdir(parents=True, exist_ok=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        name = label or dest.name
        started = time.time()

        def hook(block, block_size, total):
            got = block * block_size
            dt = max(time.time() - started, 0.2)
            speed = got / dt
            if total > 0:
                pct = base + span * min(1.0, got / total)
                self.set_progress(pct, detail=f"{name}  {self._human(got)} / {self._human(total)}  ·  {self._human(speed)}/s")
            else:
                self.set_progress(base + min(span * 0.9, span * 0.15 + elapsed_ratio(got)),
                                  detail=f"{name}  {self._human(got)}  ·  {self._human(speed)}/s", crawl=True)

        def elapsed_ratio(got):
            return min(0.8, math.log10(max(got, 1)) / 10)

        req = urllib.request.Request(url, headers={"User-Agent": "NoVoice-setup"})
        try:
            urllib.request.urlretrieve(url, tmp, hook)
        except Exception:
            with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as f:
                total = int(resp.headers.get("Content-Length") or 0)
                got = 0
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    hook(got, 1, total)
        if not tmp.exists() or tmp.stat().st_size < 10:
            raise RuntimeError(f"下载失败: {name}")
        tmp.replace(dest)
        return dest

    def _parse_pip_progress(self, line, base):
        m = PIP_SIZE.search(line)
        if m:
            cur, total, unit = m.group(1), m.group(2), m.group(3).upper()
            mul = {"KB": 1, "KIB": 1, "MB": 1024, "MIB": 1024, "GB": 1024 * 1024, "GIB": 1024 * 1024}.get(unit, 1)
            cur_k, total_k = float(cur) * mul, max(float(total) * mul, 1)
            self.set_progress(base + 28 * (cur_k / total_k), detail=f"正在下载  {cur} / {total} {unit}")
            return
        m = PIP_PCT.search(line)
        if m:
            self.set_progress(base + 28 * int(m.group(1)) / 100.0)

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
        if len(cmd) >= 3 and cmd[1] == "-m" and cmd[2] == "pip" and "--progress-bar" not in cmd:
            cmd.extend(["--progress-bar", "on"])
        self.append("> " + " ".join(map(str, cmd)))
        p = subprocess.Popen(cmd, cwd=str(ROOT), env=merged, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
        assert p.stdout is not None
        buf = b""
        while True:
            chunk = p.stdout.read(256)
            if not chunk:
                break
            buf += chunk
            while True:
                n, r = buf.find(b"\n"), buf.find(b"\r")
                if n < 0 and r < 0:
                    break
                cut = n if r < 0 else r if n < 0 else min(n, r)
                piece = buf[:cut].decode("utf-8", "replace")
                buf = buf[cut + 1 :]
                self._emit_line(piece, progress_base)
        if buf:
            self._emit_line(buf.decode("utf-8", "replace"), progress_base)
        code = p.wait()
        if code != 0:
            raise RuntimeError(f"命令失败 ({code})")

    def ensure_venv(self):
        self.set_progress(4, "创建虚拟环境", "正在创建本地 Python 环境…", step=0, crawl=True)
        if VPY.exists():
            self.append("venv 已存在")
            self.set_progress(16)
            return
        py = self.pick_python()
        self.run_cmd(py + ["-m", "venv", ".venv"])
        if not VPY.exists():
            raise RuntimeError("创建虚拟环境失败，请先安装 Python 3.10+")
        self.set_progress(16)

    def _install_wheel(self, label, urls, base, span):
        last_err = None
        for url in urls:
            try:
                name = urllib.request.unquote(url.rsplit("/", 1)[-1])
                dest = CACHE / name
                if not dest.exists() or dest.stat().st_size < 1024 * 1024:
                    self.set_progress(base, detail=f"正在下载 {label}…", crawl=True)
                    self._download(url, dest, base, span * 0.85, label=label)
                else:
                    self.append(f"{label} 缓存已存在")
                self.set_progress(base + span * 0.88, detail=f"正在安装 {label}…", crawl=True)
                self.run_cmd([str(VPY), "-m", "pip", "install", str(dest), "-i", PIPI], progress_base=base + span * 0.88)
                return
            except Exception as e:
                last_err = e
                self.append(f"{label} 失败，换源: {e}")
        if last_err:
            raise last_err

    def ensure_deps(self):
        self.set_progress(18, "安装依赖", "正在检查 PyTorch 与 Demucs…", step=1, crawl=True)
        check = subprocess.run([str(VPY), "-c", "import demucs"], cwd=str(ROOT), capture_output=True)
        if check.returncode == 0:
            self.append("demucs 已安装")
            self.set_progress(58)
            return
        has_nvidia = subprocess.run(["nvidia-smi"], capture_output=True).returncode == 0
        torch_ok = subprocess.run([str(VPY), "-c", "import torch"], cwd=str(ROOT), capture_output=True).returncode == 0
        if not torch_ok:
            if has_nvidia:
                self.append("检测到 NVIDIA，下载 GPU 版 PyTorch")
                self._install_wheel("PyTorch GPU", [u.replace("cp312", self.py_tag()) for u in TORCH_GPU], 20, 22)
                self._install_wheel("torchaudio GPU", [u.replace("cp312", self.py_tag()) for u in TORCHAUDIO_GPU], 42, 8)
            else:
                self.append("未检测到 NVIDIA，安装 CPU 版 PyTorch")
                self.set_progress(20, detail="正在安装 CPU 版 PyTorch…", crawl=True)
                self.run_cmd([str(VPY), "-m", "pip", "install", "torch", "torchaudio", "-i", PIPI], progress_base=20)
        self.set_progress(50, detail="正在安装 demucs / soundfile…", crawl=True)
        try:
            self.run_cmd([str(VPY), "-m", "pip", "install", "demucs", "soundfile", "-i", PIPI], progress_base=50)
        except Exception:
            self.run_cmd([str(VPY), "-m", "pip", "install", "demucs", "soundfile"], progress_base=50)
        self.set_progress(58)

    def ensure_models(self):
        self.set_progress(60, "下载模型", "正在检查模型文件…", step=2, crawl=True)
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
            self.set_progress(base, detail=f"下载模型 {name}  ({i + 1}/{total})", crawl=True)
            self._download(f"{MODEL_BASE}/{name}", MODELS / name, base, span, label=name)
        self.set_progress(86)

    def ensure_ffmpeg(self):
        self.set_progress(90, "检查工具", "正在检查 FFmpeg…", step=3, crawl=True)
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
