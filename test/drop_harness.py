# -*- coding: utf-8 -*-
"""同进程拖放链路验证: 自研 WM_DROPFILES 钩子 -> DragQueryFileW -> 入库。"""
import ctypes
import sys
import threading
import time
import tkinter as tk

sys.path.insert(0, r"D:\NoVoice")
import vocal_remover_gui as g

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                ctypes.c_void_p, ctypes.c_ssize_t]

WM_DROPFILES = 0x0233


def build_hdrop(paths):
    data = b"".join(p.encode("utf-16-le") + b"\x00\x00" for p in paths) + b"\x00\x00"
    total = 20 + len(data)
    h = kernel32.GlobalAlloc(0x0002, total)
    ptr = kernel32.GlobalLock(h)
    buf = (ctypes.c_char * total).from_address(ptr)
    ctypes.memset(buf, 0, total)
    ctypes.memmove(buf, bytes((ctypes.c_uint * 5)(20, 0, 0, 0, 1)), 20)
    ctypes.memmove(ctypes.byref(buf, 20), data, len(data))
    kernel32.GlobalUnlock(h)
    return h


def decode_cases():
    raws = [
        r"D:\NoVoice\test\A.mp4",
        b"D:\\NoVoice\\test\\A.mp4",
        bytearray(b"D:\\NoVoice\\test\\B.mp4"),
        memoryview(b"D:\\NoVoice\\test\\C.mp4"),
        ctypes.create_string_buffer(b"D:\\NoVoice\\test\\A.mp4"),
        ctypes.create_unicode_buffer(r"D:\NoVoice\test\B.mp4"),
    ]
    out = []
    for raw in raws:
        text = g._decode_drop_name(raw)
        if not text:
            raise SystemExit(f"decode failed: {type(raw)} {raw!r}")
        out.append(text)
    print("decode:", out)
    return out


def main():
    decode_cases()
    root = tk.Tk()
    root.withdraw()
    app = g.App(root)
    root.update_idletasks()
    app._install_drop_hook()

    payload = [r"D:\NoVoice\test\A.mp4", r"D:\NoVoice\test\B.mp4"]
    hwnd = g._hwnd_of(root)
    print("hwnd", hwnd, "winfo", root.winfo_id(), "frame", root.wm_frame())

    def drop():
        h = build_hdrop(payload)
        user32.PostMessageW(hwnd, WM_DROPFILES, h, 0)

    threading.Timer(0.3, drop).start()
    end = time.time() + 5
    while time.time() < end and not app.files:
        root.update()
        time.sleep(0.02)

    items = [str(p) for p in app.files]
    print("列表收到:", items)
    ok = items == payload
    print("拖放链路测试:", "通过" if ok else "失败")
    root.destroy()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
