# -*- coding: utf-8 -*-
import ctypes
import inspect
import os
import sys
import windnd
from pathlib import Path

print("python", sys.version)
print("windnd file", windnd.__file__)
print("DragQueryFile", ctypes.windll.shell32.DragQueryFile)
print("DragQueryFileW", ctypes.windll.shell32.DragQueryFileW)

b = ctypes.create_unicode_buffer(260)
b.value = "hello"
print("unicode_buffer.value", type(b.value), repr(b.value))

c = ctypes.c_buffer(260)
print("c_buffer.value", type(c.value), repr(c.value[:20]))

print("--- hook source ---")
print(inspect.getsource(windnd.hook_dropfiles))
