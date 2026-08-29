# -*- coding: utf-8 -*-
"""视频去人声工具 - 图形界面（Tkinter）。

双击「启动工具.bat」即可运行；支持把视频文件拖拽到窗口里。
"""
from __future__ import annotations

import ctypes
import os
import queue
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import tkinter as tk
from tkinter.scrolledtext import ScrolledText

import vocal_remover as vr

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".m4v", ".avi", ".webm", ".flv",
              ".ts", ".m2ts", ".wmv", ".mpg", ".mpeg", ".3gp"}

WM_DROPFILES = 0x0233
GWL_WNDPROC = -4
MAX_PATH_W = 32768  # 长路径, 超过旧 MAX_PATH=260


def _hwnd_of(widget: tk.Misc) -> int:
    """Tk 在 Windows 上有外框 HWND 和客户区 HWND, 拖放必须钩外框。"""
    frame = widget.wm_frame()
    if isinstance(frame, str) and frame:
        try:
            return int(frame, 16)
        except ValueError:
            pass
    return int(widget.winfo_id())


def _decode_drop_name(raw) -> str | None:
    """把 windnd / ctypes / Explorer 可能给出的路径值收成 str。"""
    if raw is None:
        return None
    if isinstance(raw, Path):
        return str(raw)
    if isinstance(raw, memoryview):
        raw = raw.tobytes()
    if isinstance(raw, bytearray):
        raw = bytes(raw)
    if not isinstance(raw, (bytes, str)):
        value = getattr(raw, "value", raw)
        if value is raw:
            try:
                value = bytes(raw)
            except Exception:
                value = str(raw)
        raw = value
    if isinstance(raw, memoryview):
        raw = raw.tobytes()
    if isinstance(raw, bytearray):
        raw = bytes(raw)
    if isinstance(raw, bytes):
        if raw.endswith(b"\x00"):
            raw = raw.rstrip(b"\x00")
        if not raw:
            return None
        # UTF-16LE 路径(带 BOM 或偶数长且含 0 字节)优先; 否则按系统代码页。
        if raw.startswith(b"\xff\xfe"):
            try:
                return raw.decode("utf-16-le").rstrip("\x00")
            except UnicodeDecodeError:
                pass
        if b"\x00" in raw:
            try:
                return raw.decode("utf-16-le").rstrip("\x00")
            except UnicodeDecodeError:
                pass
        try:
            return os.fsdecode(raw)
        except UnicodeDecodeError:
            try:
                return raw.decode("gbk")
            except UnicodeDecodeError:
                return raw.decode("utf-8", errors="replace")
    text = str(raw).strip()
    return text or None


def hook_dropfiles(widget: tk.Misc, callback) -> object | None:
    """在 Windows 上挂钩 WM_DROPFILES。失败则返回 None, 界面仍可用「添加视频」。

    不用第三方 windnd: 它默认走 ANSI DragQueryFile, 回调给 bytes;
    Python 3.12 的 Path(bytes) 会 TypeError, 异常发生在 ctypes 窗口过程里,
    会被忽略后让窗口过程失效, 看起来像「拖一下程序就挂了」。
    """
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_void_p, ctypes.c_uint,
                                 ctypes.c_void_p, ctypes.c_void_p)
    GetWindowLong = user32.GetWindowLongPtrW
    SetWindowLong = user32.SetWindowLongPtrW
    GetWindowLong.restype = ctypes.c_void_p
    GetWindowLong.argtypes = [ctypes.c_void_p, ctypes.c_int]
    SetWindowLong.restype = ctypes.c_void_p
    SetWindowLong.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    CallWindowProc = user32.CallWindowProcW
    CallWindowProc.restype = LRESULT
    CallWindowProc.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
                               ctypes.c_void_p, ctypes.c_void_p]
    DragQueryFileW = shell32.DragQueryFileW
    DragQueryFileW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                               ctypes.c_void_p, ctypes.c_uint]
    DragQueryFileW.restype = ctypes.c_uint
    DragFinish = shell32.DragFinish
    DragFinish.argtypes = [ctypes.c_void_p]
    DragAcceptFiles = shell32.DragAcceptFiles
    DragAcceptFiles.argtypes = [ctypes.c_void_p, ctypes.c_bool]

    hwnd = _hwnd_of(widget)
    old_proc = GetWindowLong(hwnd, GWL_WNDPROC)
    if not old_proc:
        return None

    def py_wndproc(hwnd_, msg, wp, lp):
        if msg == WM_DROPFILES:
            names = []
            try:
                count = DragQueryFileW(wp, 0xFFFFFFFF, None, 0)
                buf = ctypes.create_unicode_buffer(MAX_PATH_W)
                for i in range(count):
                    n = DragQueryFileW(wp, i, buf, MAX_PATH_W)
                    if n:
                        names.append(buf.value)
            except Exception:
                names = []
            try:
                DragFinish(wp)
            except Exception:
                pass
            try:
                if names:
                    callback(names)
            except Exception:
                traceback.print_exc()
            return 0
        return CallWindowProc(old_proc, hwnd_, msg, wp, lp)

    new_proc = WNDPROC(py_wndproc)
    DragAcceptFiles(hwnd, True)
    SetWindowLong(hwnd, GWL_WNDPROC, ctypes.cast(new_proc, ctypes.c_void_p).value)
    # 必须把 new_proc 挂在 widget 上, 否则 ctypes 回调被 GC 后下一次拖放会崩。
    widget._novoice_drop_hook = (new_proc, old_proc, hwnd)
    return widget._novoice_drop_hook

MODEL_MAP = {
    "标准（速度快）": "htdemucs",
    "高质量（更慢更干净）": "htdemucs_ft",
}
TRACK_MAP = {
    "全部音轨都去人声": "all",
    "仅第一条音轨（其余原样保留）": "first",
}


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.files: list[Path] = []
        self.q: "queue.Queue[tuple]" = queue.Queue()
        self.running = False
        self.cancel_flag = False
        self.last_output: Path | None = None

        root.title("视频去人声工具 · 画面无损")
        root.geometry("760x640")
        root.option_add("*Font", ("Microsoft YaHei UI", 10))

        self._build_ui()
        self.root.after(100, self._poll)
        # 等窗口真正映射后再挂钩, 此时 wm_frame() 才是外框 HWND。
        self.root.after_idle(self._install_drop_hook)

    def _install_drop_hook(self):
        try:
            self.root.update_idletasks()
            hook_dropfiles(self.root, self._drop_files)
        except Exception:
            traceback.print_exc()

    # ---------- 界面 ----------
    def _build_ui(self):
        pad = {"padx": 12, "pady": 6}

        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="支持批量；把视频直接拖进窗口也可以。输出文件自动加「_无人声」后缀，放在原目录。").pack(side="left")

        mid = ttk.Frame(self.root)
        mid.pack(fill="both", expand=True, **pad)
        self.listbox = tk.Listbox(mid, selectmode=tk.EXTENDED, activestyle="dotbox")
        self.listbox.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(mid, command=self.listbox.yview)
        sb.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=sb.set)

        btns = ttk.Frame(self.root)
        btns.pack(fill="x", **pad)
        self.btn_add = ttk.Button(btns, text="添加视频", command=self._add_files)
        self.btn_remove = ttk.Button(btns, text="移除选中", command=self._remove_selected)
        self.btn_clear = ttk.Button(btns, text="清空列表", command=self._clear)
        self.btn_add.pack(side="left", padx=(0, 6))
        self.btn_remove.pack(side="left", padx=6)
        self.btn_clear.pack(side="left", padx=6)
        self.btn_open = ttk.Button(btns, text="打开输出位置", command=self._open_output)
        self.btn_open.pack(side="right")

        opts = ttk.LabelFrame(self.root, text="选项")
        opts.pack(fill="x", **pad)
        ttk.Label(opts, text="分离质量:").grid(row=0, column=0, padx=(10, 4), pady=8, sticky="w")
        self.var_model = tk.StringVar(value=list(MODEL_MAP)[0])
        cb1 = ttk.Combobox(opts, textvariable=self.var_model, state="readonly",
                           values=list(MODEL_MAP), width=24)
        cb1.grid(row=0, column=1, padx=4)
        ttk.Label(opts, text="音轨处理:").grid(row=0, column=2, padx=(16, 4), sticky="w")
        self.var_tracks = tk.StringVar(value=list(TRACK_MAP)[0])
        cb2 = ttk.Combobox(opts, textvariable=self.var_tracks, state="readonly",
                           values=list(TRACK_MAP), width=26)
        cb2.grid(row=0, column=3, padx=4)
        ttk.Label(opts, foreground="#666",
                  text="画面、字幕、章节、元数据均原样保留（零重编码）；仅音轨经 AI 去人声。"
        ).grid(row=1, column=0, columnspan=4, padx=10, pady=(0, 8), sticky="w")

        run = ttk.Frame(self.root)
        run.pack(fill="x", **pad)
        self.btn_start = ttk.Button(run, text="开始处理", command=self._start)
        self.btn_start.pack(side="left")
        self.btn_cancel = ttk.Button(run, text="停止", command=self._cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=6)
        self.status = ttk.Label(run, text="就绪", foreground="#444")
        self.status.pack(side="right")

        self.bar = ttk.Progressbar(self.root, mode="determinate", maximum=100)
        self.bar.pack(fill="x", padx=12)

        self.log = ScrolledText(self.root, height=10, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        self.log.tag_configure("ok", foreground="#0a7d32")
        self.log.tag_configure("err", foreground="#c62828")
        self.log.tag_configure("dim", foreground="#777")

    # ---------- 日志与进度 ----------
    def _log(self, msg: str, tag: str | None = None):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n", tag or ())
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_busy(self, busy: bool):
        self.running = busy
        state = "disabled" if busy else "normal"
        for b in (self.btn_add, self.btn_remove, self.btn_clear, self.btn_start):
            b.configure(state=state)
        self.btn_cancel.configure(state="normal" if busy else "disabled")

    def _poll(self):
        try:
            while True:
                kind, *rest = self.q.get_nowait()
                if kind == "log":
                    self._log(*rest)
                elif kind == "drop":
                    self._accept(*rest)
                elif kind == "progress":
                    pct, msg = rest
                    self.bar["value"] = pct * 100
                    self.status.configure(text=msg)
                elif kind == "done":
                    self._set_busy(False)
                    self.bar["value"] = 0
                    self.status.configure(text="完成")
                    n_ok, n_fail, last_out = rest
                    if last_out:
                        self.last_output = Path(last_out)
                    if n_fail == 0:
                        messagebox.showinfo("完成", f"全部处理完成（{n_ok} 个文件）")
                    else:
                        messagebox.showwarning("完成（部分失败）",
                                               f"成功 {n_ok} 个，失败 {n_fail} 个，详见日志。")
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    # ---------- 文件列表 ----------
    def _drop_files(self, file_list):
        # 窗口过程内只做纯 Python 解码, Tk 控件操作经队列转回主循环
        names = []
        for raw in file_list or ():
            text = _decode_drop_name(raw)
            if not text:
                continue
            names.append(Path(text))
        if names:
            self.q.put(("drop", names))

    def _add_files(self):
        types = [("视频文件", " ".join("*" + e for e in sorted(VIDEO_EXTS))),
                 ("所有文件", "*.*")]
        names = filedialog.askopenfilenames(title="选择视频文件", filetypes=types)
        self._accept([Path(n) for n in names])

    def _accept(self, paths):
        added = 0
        for raw in paths:
            text = _decode_drop_name(raw)
            if not text:
                continue
            p = Path(text)
            if p in self.files:
                continue
            if p.suffix.lower() not in VIDEO_EXTS:
                self._log(f"跳过（不是常见视频格式）: {p.name}", "dim")
                continue
            self.files.append(p)
            self.listbox.insert("end", str(p))
            added += 1
        if added and not self.running:
            self.status.configure(text=f"已选 {len(self.files)} 个文件")

    def _remove_selected(self):
        for i in sorted(self.listbox.curselection(), reverse=True):
            self.listbox.delete(i)
            self.files.pop(i)

    def _clear(self):
        self.listbox.delete(0, "end")
        self.files.clear()

    def _open_output(self):
        target = self.last_output
        if target is None:
            target = self.files[0].parent if self.files else Path.cwd()
        if target.is_file():
            subprocess.Popen(["explorer", "/select,", str(target)])
        elif target.is_dir():
            subprocess.Popen(["explorer", str(target)])
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            subprocess.Popen(["explorer", str(target.parent)])

    # ---------- 处理 ----------
    def _cancel(self):
        self.cancel_flag = True
        self.status.configure(text="正在停止（当前任务结束后停下）…")
        self._log("已请求停止…", "dim")

    def _start(self):
        if not self.files:
            messagebox.showinfo("提示", "请先添加视频文件。")
            return
        try:
            vr.find_tools()
        except vr.VocalRemoverError as e:
            messagebox.showerror("缺少 FFmpeg", str(e))
            return
        files = list(self.files)
        opts = vr.Options(model=MODEL_MAP[self.var_model.get()],
                          tracks=TRACK_MAP[self.var_tracks.get()])
        self.cancel_flag = False
        self._set_busy(True)
        self.bar["value"] = 0
        self._log(f"开始处理 {len(files)} 个文件（模型 {opts.model}）", "dim")
        threading.Thread(target=self._worker, args=(files, opts), daemon=True).start()

    def _worker(self, files: list[Path], opts: vr.Options):
        n_ok = n_fail = 0
        last_out = None
        for i, f in enumerate(files):
            if self.cancel_flag:
                break
            self.q.put(("log", f"[{i + 1}/{len(files)}] {f.name}"))

            def cb(stage, pct, msg, _i=i, _n=len(files)):
                if self.cancel_flag:
                    return False
                overall = (_i + (pct or 0.0)) / _n
                self.q.put(("progress", overall, f"({ _i + 1}/{_n}) {msg}"))
                return True

            try:
                out = vr.remove_vocals(f, None, opts, cb)
                last_out = out
                n_ok += 1
                self.q.put(("log", f"  完成 -> {out}", "ok"))
            except vr.CancelledError:
                self.q.put(("log", "  已停止", "err"))
                break
            except Exception as e:
                n_fail += 1
                self.q.put(("log", f"  失败: {e}", "err"))
                traceback.print_exc()
        self.q.put(("done", n_ok, n_fail, last_out))


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
