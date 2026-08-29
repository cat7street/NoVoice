# -*- coding: utf-8 -*-
"""向 GUI 窗口发送 WM_DROPFILES, 模拟真实拖放。"""
import ctypes
import ctypes.wintypes as wt
import sys

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WM_DROPFILES = 0x0233

kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalFree.restype = ctypes.c_void_p
kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t]


def build_hdrop(paths):
    data = b""
    for p in paths:
        data += p.encode("utf-16-le") + b"\x00\x00"
    data += b"\x00\x00"
    total = 20 + len(data)
    h = kernel32.GlobalAlloc(0x0002, total)
    ptr = kernel32.GlobalLock(h)
    buf = (ctypes.c_char * total).from_address(ptr)
    ctypes.memset(buf, 0, total)
    struct = (ctypes.c_uint * 5)(20, 0, 0, 0, 1)
    ctypes.memmove(buf, bytes(struct), 20)
    ctypes.memmove(ctypes.byref(buf, 20), data, len(data))
    kernel32.GlobalUnlock(h)
    return h


def child_windows(root):
    result = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        result.append(hwnd)
        return True

    user32.EnumChildWindows(root, cb, 0)
    return result


def main():
    title = "视频去人声工具 · 画面无损"
    frame = user32.FindWindowW(None, title)
    if not frame:
        print("未找到窗口:", title)
        return 1
    targets = [frame] + child_windows(frame)
    print(f"窗口句柄: frame={frame}, 子窗口 {len(targets) - 1} 个")
    payload = sys.argv[1] if len(sys.argv) > 1 else r"D:\NoVoice\test\A.mp4"
    h = build_hdrop([payload])
    for hwnd in targets:
        user32.SendMessageW(hwnd, WM_DROPFILES, h, 0)
    kernel32.GlobalFree(h)
    print("已发送 WM_DROPFILES:", payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
