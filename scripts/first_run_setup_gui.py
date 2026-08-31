# -*- coding: utf-8 -*-
import math
import os
import re
import shutil
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
ICON_CANDIDATES = [
    ROOT / "app.ico",
    ROOT / "icon.ico",
    ROOT / "NoVoice.exe",
]
MODEL_MIRRORS = [
    "https://hf-mirror.com/Politrees/UVR_resources/resolve/main/models/Demucs/Demucs_v4/{name}",
    "https://huggingface.co/Politrees/UVR_resources/resolve/main/models/Demucs/Demucs_v4/{name}",
    "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/{name}",
]
MODEL_FILES_STD = [
    "htdemucs.yaml",
    "955717e8-8726e21a.th",
]
MODEL_FILES_FT = [
    "htdemucs_ft.yaml",
    "04573f0d-f3cf25b2.th",
    "92cfc3b6-ef3bcb9c.th",
    "d12395a8-e57c48e6.th",
    "f7e0c4bc-ba3fe64a.th",
]
MODEL_FILES = MODEL_FILES_STD + MODEL_FILES_FT
LOCAL_MODEL_HINTS = [
    Path(r"D:\NoVoice\models"),
    Path.home() / ".cache" / "torch" / "hub" / "checkpoints",
]
PIPI = "https://pypi.tuna.tsinghua.edu.cn/simple"
TORCH_GPU = [
    "https://mirrors.aliyun.com/pytorch-wheels/cu126/torch-2.7.1%2Bcu126-cp312-cp312-win_amd64.whl",
    "https://mirror.sjtu.edu.cn/pytorch-wheels/cu126/torch-2.7.1%2Bcu126-cp312-cp312-win_amd64.whl",
    "https://download.pytorch.org/whl/cu126/torch-2.7.1%2Bcu126-cp312-cp312-win_amd64.whl",
]
TORCHAUDIO_GPU = [
    "https://mirrors.aliyun.com/pytorch-wheels/cu126/torchaudio-2.7.1%2Bcu126-cp312-cp312-win_amd64.whl",
    "https://mirror.sjtu.edu.cn/pytorch-wheels/cu126/torchaudio-2.7.1%2Bcu126-cp312-cp312-win_amd64.whl",
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
        self.root.geometry("500x268")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)
        for icon in ICON_CANDIDATES:
            if icon.exists():
                try:
                    self.root.iconbitmap(default=str(icon))
                    break
                except Exception:
                    continue

        self.step = tk.StringVar(value="准备开始")
        self.detail = tk.StringVar(value="首次启动会配置运行环境，只需这一次。")
        self.percent = tk.StringVar(value="0%")
        self.show_log = False
        self._progress = 0.0
        self._shown = 0.0
        self._pulse = 0.0
        self._active_step = -1
        self._busy_since = time.time()
        self._busy_floor = 0.0
        self._log_lines = []
        self._animating = True

        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True, padx=20, pady=16)

        head = tk.Frame(outer, bg=BG)
        head.pack(fill="x")
        tk.Label(head, text="NoVoice", fg=TEXT, bg=BG, font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
        tk.Label(head, text="正在准备运行环境", fg=MUTED, bg=BG, font=("Microsoft YaHei UI", 9)).pack(anchor="w", pady=(1, 10))

        self.steps_frame = tk.Frame(outer, bg=BG)
        self.steps_frame.pack(fill="x", pady=(0, 12))
        self.step_labels = []
        names = ["环境", "依赖", "模型", "工具"]
        for i, name in enumerate(names):
            lab = tk.Label(self.steps_frame, text=name, fg=MUTED, bg="#162033",
                           font=("Microsoft YaHei UI", 9), padx=12, pady=5)
            lab.pack(side="left", padx=(0 if i == 0 else 6, 0))
            self.step_labels.append(lab)

        card = tk.Frame(outer, bg="#162033", highlightbackground=LINE, highlightthickness=1)
        card.pack(fill="x")
        inner = tk.Frame(card, bg="#162033")
        inner.pack(fill="x", padx=14, pady=12)

        row = tk.Frame(inner, bg="#162033")
        row.pack(fill="x")
        tk.Label(row, textvariable=self.step, fg=TEXT, bg="#162033", font=("Microsoft YaHei UI", 10)).pack(side="left")
        tk.Label(row, textvariable=self.percent, fg=TEXT, bg="#162033", font=("Microsoft YaHei UI", 10)).pack(side="right")

        tk.Label(inner, textvariable=self.detail, fg=MUTED, bg="#162033", font=("Microsoft YaHei UI", 9),
                 wraplength=440, justify="left").pack(anchor="w", pady=(6, 10))

        self.canvas = tk.Canvas(inner, height=6, bg="#162033", highlightthickness=0, bd=0)
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
        h = 6
        self.canvas.create_rectangle(0, 0, w, h, fill="#0b1220", outline="")
        fill = int(w * max(0.0, min(1.0, self._shown / 100.0)))
        if fill > 0:
            self.canvas.create_rectangle(0, 0, fill, h, fill=ACCENT, outline="")
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
        self._draw_bar()
        self.root.after(16, self._tick)

    def _toggle_log(self):
        self.show_log = not self.show_log
        if self.show_log:
            self.toggle.configure(text="隐藏详情")
            self.log.pack(fill="both", expand=True, pady=(8, 0))
            self.root.geometry("500x400")
        else:
            self.toggle.configure(text="显示详情")
            self.log.pack_forget()
            self.root.geometry("500x268")

    def _paint_steps(self):
        idx = self._active_step
        for i, lab in enumerate(self.step_labels):
            if i < idx:
                lab.configure(fg="#86efac", bg="#123524")
            elif i == idx:
                lab.configure(fg="#eff6ff", bg="#1d4ed8")
            else:
                lab.configure(fg=MUTED, bg="#162033")

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

    def _hidden(self):
        kw = {}
        if os.name == "nt":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            kw["startupinfo"] = si
            kw["creationflags"] = 0x08000000
        return kw

    def which(self, name):
        from shutil import which
        return which(name)

    def pick_python(self):
        for ver in ("3.12", "3.11", "3.10"):
            try:
                r = subprocess.run(
                    ["py", f"-{ver}", "-c", "import sys; print(sys.executable)"],
                    capture_output=True, text=True, **self._hidden(),
                )
                exe = (r.stdout or "").strip()
                if r.returncode == 0 and exe:
                    return [exe]
            except Exception:
                pass
        return ["python"]

    def py_tag(self):
        r = subprocess.run(
            [str(VPY), "-c", "import sys; print(f'cp{sys.version_info.major}{sys.version_info.minor}')"],
            capture_output=True, text=True, **self._hidden(),
        )
        tag = (r.stdout or "").strip()
        return tag or "cp312"

    def _human(self, n):
        n = float(n)
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024 or unit == "GB":
                return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
            n /= 1024
        return f"{n:.1f} GB"

    def _friendly_err(self, err):
        msg = str(err)
        low = msg.lower()
        if "timed out" in low or "timeout" in low:
            return "下载超时，正在自动重试（已下载部分会续传）"
        if "403" in msg:
            return "源站拒绝访问 (403)，正在换源"
        if "404" in msg:
            return "文件不存在 (404)，正在换源"
        if "10054" in msg or "connection" in low or "reset" in low:
            return "网络中断，正在重试"
        return msg

    def _as_urls(self, url_or_urls):
        if isinstance(url_or_urls, (list, tuple)):
            return [u for u in url_or_urls if u]
        return [url_or_urls]

    def _curl_bin(self):
        windir = os.environ.get("SystemRoot", r"C:\Windows")
        for p in (Path(windir) / "System32" / "curl.exe", Path(r"C:\Windows\System32\curl.exe")):
            if p.exists():
                return str(p)
        return shutil.which("curl.exe") or shutil.which("curl")

    def _head_size(self, url):
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0 NoVoice-setup"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                return int(resp.headers.get("Content-Length") or 0), (resp.headers.get("Accept-Ranges") or "").lower() == "bytes", url
        except Exception:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 NoVoice-setup", "Range": "bytes=0-0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                cr = resp.headers.get("Content-Range") or ""
                if "/" in cr:
                    return int(cr.rsplit("/", 1)[-1]), True, url
                return int(resp.headers.get("Content-Length") or 0), resp.status == 206, url

    def _probe(self, urls):
        last = None
        for url in urls:
            try:
                return self._head_size(url)
            except Exception as e:
                last = e
                self.append(f"探测失败 {url}: {e}")
        if last:
            raise last
        raise RuntimeError("没有可用下载源")

    def _download(self, url_or_urls, dest, base, span, label=None, retries=5):
        CACHE.mkdir(parents=True, exist_ok=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        urls = self._as_urls(url_or_urls)
        tmp = dest.with_suffix(dest.suffix + ".part")
        name = label or dest.name
        last_err = None
        for attempt in range(1, retries + 1):
            try:
                total, ranged, _url = 0, False, urls[0]
                try:
                    total, ranged, _url = self._probe(urls)
                except Exception as e:
                    self.append(f"{name} 探测大小失败: {e}")
                workers = 32 if total >= 64 * 1024 * 1024 else 16 if total >= 8 * 1024 * 1024 else 4
                if ranged and total >= 4 * 1024 * 1024:
                    self._download_parts(urls, tmp, dest, base, span, name, total, workers=workers)
                else:
                    self._download_once(urls[0], tmp, dest, base, span, name)
                return dest
            except Exception as e:
                last_err = e
                self.append(f"{name} 第 {attempt}/{retries} 次失败: {e}")
                self.set_progress(base, detail=self._friendly_err(e), crawl=True)
                time.sleep(min(4, attempt))
        raise RuntimeError(self._friendly_err(last_err))

    def _download_parts(self, urls, tmp, dest, base, span, name, total, workers=32):
        workers = max(4, min(int(workers), 32))
        part_dir = tmp.parent / (tmp.name + ".parts")
        part_dir.mkdir(parents=True, exist_ok=True)
        size = total // workers
        ranges = []
        for i in range(workers):
            start = i * size
            end = total - 1 if i == workers - 1 else (i + 1) * size - 1
            ranges.append((i, start, end))
        got = [0] * workers
        lock = threading.Lock()
        started = time.time()
        errors = []
        last_report = [0.0]
        curl = self._curl_bin()
        engine = "curl" if curl else "py"

        def report():
            now = time.time()
            if now - last_report[0] < 0.15:
                return
            last_report[0] = now
            abs_got = sum(got)
            dt = max(now - started, 0.2)
            speed = abs_got / dt
            pct = base + span * min(1.0, abs_got / max(total, 1))
            self.set_progress(
                pct,
                detail=f"{name}  {self._human(abs_got)} / {self._human(total)}  ·  {self._human(speed)}/s  ·  {workers}x{engine}",
            )

        def curl_range(url, start, end, part, have):
            need = end - start + 1
            if have >= need:
                return
            tmp_part = part.with_suffix(".tmp")
            tmp_part.unlink(missing_ok=True)
            cmd = [
                curl, "-fsSL", "--http1.1", "--retry", "2", "--retry-delay", "1",
                "-A", "Mozilla/5.0 NoVoice-setup",
                "-H", f"Range: bytes={start + have}-{end}",
                "--connect-timeout", "8", "--max-time", "0",
                "-o", str(tmp_part), url,
            ]
            p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **self._hidden())
            while p.poll() is None:
                extra = tmp_part.stat().st_size if tmp_part.exists() else 0
                with lock:
                    got[int(part.stem)] = have + extra
                    report()
                time.sleep(0.15)
            if p.returncode != 0:
                tmp_part.unlink(missing_ok=True)
                raise RuntimeError(f"curl {p.returncode}")
            extra = tmp_part.stat().st_size if tmp_part.exists() else 0
            if extra <= 0:
                raise RuntimeError("curl 空分段")
            with open(part, "ab" if have else "wb") as dst, open(tmp_part, "rb") as src:
                shutil.copyfileobj(src, dst, 1024 * 1024)
            tmp_part.unlink(missing_ok=True)

        def py_range(url, start, end, part, have):
            headers = {
                "User-Agent": "Mozilla/5.0 NoVoice-setup",
                "Range": f"bytes={start + have}-{end}",
            }
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                if int(getattr(resp, "status", 206) or 206) >= 400:
                    raise RuntimeError(f"HTTP {resp.status}")
                mode = "ab" if have else "wb"
                wrote = 0
                with open(part, mode) as f:
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        wrote += len(chunk)
                        with lock:
                            got[int(part.stem)] = have + wrote
                            report()

        def worker(idx, start, end):
            part = part_dir / f"{idx:02d}.bin"
            have = part.stat().st_size if part.exists() else 0
            need = end - start + 1
            if have > need:
                part.unlink(missing_ok=True)
                have = 0
            if have == need:
                with lock:
                    got[idx] = have
                return
            last = None
            rotated = urls[idx % len(urls):] + urls[: idx % len(urls)]
            for url in rotated:
                try:
                    if curl:
                        curl_range(url, start, end, part, have)
                    else:
                        py_range(url, start, end, part, have)
                    final = part.stat().st_size if part.exists() else 0
                    if final != need:
                        raise RuntimeError(f"分段 {idx} 不完整 {final}/{need}")
                    with lock:
                        got[idx] = final
                    return
                except Exception as e:
                    last = e
                    have = part.stat().st_size if part.exists() else 0
                    if have > need:
                        part.unlink(missing_ok=True)
                        have = 0
            raise last or RuntimeError(f"分段 {idx} 失败")

        threads = []
        for item in ranges:
            t = threading.Thread(target=lambda it=item: self._safe_part(worker, it, errors), daemon=True)
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        if errors:
            raise errors[0]
        with open(tmp, "wb") as out:
            for i, start, end in ranges:
                part = part_dir / f"{i:02d}.bin"
                with open(part, "rb") as src:
                    shutil.copyfileobj(src, out, 1024 * 1024)
        for child in part_dir.glob("*"):
            child.unlink(missing_ok=True)
        part_dir.rmdir()
        if tmp.stat().st_size != total:
            raise RuntimeError(f"下载失败: {name}")
        tmp.replace(dest)

    def _safe_part(self, fn, item, errors):
        try:
            fn(*item)
        except Exception as e:
            errors.append(e)

    def _download_once(self, url, tmp, dest, base, span, name):
        existing = tmp.stat().st_size if tmp.exists() else 0
        headers = {"User-Agent": "Mozilla/5.0 NoVoice-setup"}
        if existing > 0:
            headers["Range"] = f"bytes={existing}-"
        req = urllib.request.Request(url, headers=headers)
        started = time.time()
        got_session = 0
        with urllib.request.urlopen(req, timeout=20) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            if status >= 400:
                raise RuntimeError(f"HTTP {status}")
            if status == 200 and existing > 0:
                existing = 0
                mode = "wb"
            else:
                mode = "ab" if existing > 0 else "wb"
            total = int(resp.headers.get("Content-Length") or 0)
            if status == 206:
                cr = resp.headers.get("Content-Range") or ""
                if "/" in cr:
                    try:
                        total = int(cr.rsplit("/", 1)[-1])
                    except ValueError:
                        total = existing + total
                else:
                    total = existing + total
            elif status == 200:
                existing = 0

            def report(abs_got):
                dt = max(time.time() - started, 0.2)
                speed = max(got_session, 1) / dt
                if total > 0:
                    pct = base + span * min(1.0, abs_got / total)
                    self.set_progress(
                        pct,
                        detail=f"{name}  {self._human(abs_got)} / {self._human(total)}  ·  {self._human(speed)}/s",
                    )
                else:
                    self.set_progress(
                        base + min(span * 0.9, span * 0.2),
                        detail=f"{name}  {self._human(abs_got)}  ·  {self._human(speed)}/s",
                        crawl=True,
                    )

            with open(tmp, mode) as f:
                while True:
                    chunk = resp.read(1024 * 512)
                    if not chunk:
                        break
                    f.write(chunk)
                    got_session += len(chunk)
                    report(existing + got_session)
        size = tmp.stat().st_size if tmp.exists() else 0
        if size < 10:
            raise RuntimeError(f"下载失败: {name}")
        tmp.replace(dest)

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
        p = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            env=merged,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            **self._hidden(),
        )
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
        name = urllib.request.unquote(urls[0].rsplit("/", 1)[-1])
        dest = CACHE / name
        if not dest.exists() or dest.stat().st_size < 1024 * 1024:
            self.set_progress(base, detail=f"正在榨带宽下载 {label}…", crawl=True)
            self._download(urls, dest, base, span * 0.85, label=label)
        else:
            self.append(f"{label} 缓存已存在")
        self.set_progress(base + span * 0.88, detail=f"正在安装 {label}…", crawl=True)
        self.run_cmd([str(VPY), "-m", "pip", "install", str(dest), "-i", PIPI], progress_base=base + span * 0.88)

    def ensure_deps(self):
        self.set_progress(18, "安装依赖", "正在检查 PyTorch 与 Demucs…", step=1, crawl=True)
        check = subprocess.run([str(VPY), "-c", "import demucs"], cwd=str(ROOT), capture_output=True, **self._hidden())
        if check.returncode == 0:
            self.append("demucs 已安装")
            self.set_progress(58)
            return
        has_nvidia = subprocess.run(["nvidia-smi"], capture_output=True, **self._hidden()).returncode == 0
        torch_ok = subprocess.run([str(VPY), "-c", "import torch"], cwd=str(ROOT), capture_output=True, **self._hidden()).returncode == 0
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

    def _wanted_models(self):
        wanted = list(MODEL_FILES_STD)
        if os.environ.get("NOVOICE_MODELS", "std").lower() in ("all", "ft", "full"):
            wanted.extend(MODEL_FILES_FT)
        return wanted

    def _reuse_local_model(self, name):
        dest = MODELS / name
        if dest.exists() and dest.stat().st_size > 10:
            return True
        for hint in LOCAL_MODEL_HINTS:
            src = hint / name
            if src.exists() and src.stat().st_size > 10:
                dest.write_bytes(src.read_bytes())
                self.append(f"复用本地模型 {src}")
                return True
        return dest.exists()

    def ensure_models(self):
        self.set_progress(60, "下载模型", "正在检查标准模型…", step=2, crawl=True)
        MODELS.mkdir(parents=True, exist_ok=True)
        missing = [f for f in self._wanted_models() if not self._reuse_local_model(f)]
        if not missing:
            self.append("标准模型已就绪")
            self.set_progress(86)
            return
        total = len(missing)
        for i, name in enumerate(missing):
            base = 60 + 26 * i / total
            span = 26 / total
            self.set_progress(base, detail=f"下载模型 {name}  ({i + 1}/{total})", crawl=True)
            urls = [tpl.format(name=name) for tpl in MODEL_MIRRORS]
            if not name.endswith(".th"):
                urls = urls[:2]
            self._download(urls, MODELS / name, base, span, label=name)
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
                subprocess.Popen([str(EXE)], cwd=str(ROOT), **self._hidden())
                self.root.after(700, self.root.destroy)
            else:
                self.root.after(0, lambda: messagebox.showerror("错误", "未找到 NoVoice.exe"))
        except Exception as e:
            msg = self._friendly_err(e)
            self.append(str(e))
            self.set_progress(self._progress, "配置失败", msg)
            self.root.after(0, lambda err=msg: messagebox.showerror("配置失败", err))

    def start(self):
        threading.Thread(target=self.work, daemon=True).start()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    if MARKER.exists() and EXE.exists():
        kw = {}
        if os.name == "nt":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            kw["startupinfo"] = si
            kw["creationflags"] = 0x08000000
        subprocess.Popen([str(EXE)], cwd=str(ROOT), **kw)
        sys.exit(0)
    SetupApp().run()
