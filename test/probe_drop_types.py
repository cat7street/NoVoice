# -*- coding: utf-8 -*-
"""Reproduce windnd drop payload types and Tk HWND hooking."""
import ctypes
import os
import sys
import time
import tkinter as tk
from pathlib import Path

sys.path.insert(0, r"D:\NoVoice")
import windnd
import vocal_remover_gui as g

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_ssize_t]

WM_DROPFILES = 0x0233


def build_hdrop(paths, wide=True):
    if wide:
        data = b"".join(p.encode("utf-16-le") + b"\x00\x00" for p in paths) + b"\x00\x00"
        fwide = 1
    else:
        data = b"".join(p.encode("mbcs", "replace") + b"\x00" for p in paths) + b"\x00"
        fwide = 0
    total = 20 + len(data)
    h = kernel32.GlobalAlloc(0x0002, total)
    ptr = kernel32.GlobalLock(h)
    buf = (ctypes.c_char * total).from_address(ptr)
    ctypes.memset(buf, 0, total)
    ctypes.memmove(buf, bytes((ctypes.c_uint * 5)(20, 0, 0, 0, fwide)), 20)
    ctypes.memmove(ctypes.byref(buf, 20), data, len(data))
    kernel32.GlobalUnlock(h)
    return h


def dump_list(tag, files):
    print(tag, "n=", len(files))
    for i, x in enumerate(files):
        print(f"  [{i}] type={type(x).__name__} repr={x!r}")


class Q:
    def __init__(self):
        self.items = []

    def put(self, x):
        self.items.append(x)
        print("queued", [(type(p).__name__, str(p)) for p in x[1]])


class Dummy:
    def __init__(self):
        self.q = Q()


def test_pathlib_bytes():
    print("=== pathlib Path(bytes) ===")
    raw = b"D:\\NoVoice\\test\\A.mp4"
    try:
        print(Path(raw))
    except Exception as e:
        print("Path(bytes) FAIL", e)
    print("os.fsdecode", os.fsdecode(raw))


def test_gui_drop():
    print("=== App._drop_files payloads ===")
    d = Dummy()
    cases = {
        "bytes": [b"D:\\NoVoice\\test\\A.mp4"],
        "str": [r"D:\NoVoice\test\A.mp4"],
        "bytearray": [bytearray(b"D:\\NoVoice\\test\\A.mp4")],
        "memoryview": [memoryview(b"D:\\NoVoice\\test\\A.mp4")],
        "c_char_Array": [ctypes.create_string_buffer(b"D:\\x.mp4")],
        "c_wchar_Array": [ctypes.create_unicode_buffer("D:\\x.mp4")],
    }
    for name, payload in cases.items():
        d = Dummy()
        try:
            g.App._drop_files(d, payload)
            print(name, "OK")
        except Exception as e:
            print(name, "FAIL", type(e).__name__, e)


def test_direct_windnd(force_unicode):
    print(f"=== direct windnd hook force_unicode={force_unicode} ===")
    got = []

    def cb(files):
        dump_list("callback", files)
        got.append(list(files))

    root = tk.Tk()
    root.title("probe-windnd")
    root.geometry("400x200")
    root.update_idletasks()
    print("winfo_id", root.winfo_id(), "wm_frame", root.wm_frame())
    windnd.hook_dropfiles(root, func=cb, force_unicode=force_unicode)
    payload = [r"D:\NoVoice\test\A.mp4"]
    h = build_hdrop(payload, wide=True)
    hwnds = [root.winfo_id()]
    frame = root.wm_frame()
    try:
        hwnds.append(int(frame, 16) if isinstance(frame, str) else int(frame))
    except Exception as e:
        print("wm_frame parse", e, frame)
    print("send to hwnds", hwnds)
    for hwnd in hwnds:
        user32.PostMessageW(hwnd, WM_DROPFILES, h, 0)
    end = time.time() + 2
    while time.time() < end and not got:
        root.update()
        time.sleep(0.02)
    print("got", bool(got), got)
    root.destroy()


if __name__ == "__main__":
    test_pathlib_bytes()
    test_gui_drop()
    test_direct_windnd(True)
    test_direct_windnd(False)
