# -*- coding: utf-8 -*-
from pathlib import Path
import struct
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src-tauri" / "icons"
OUT.mkdir(parents=True, exist_ok=True)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def make_base(size=1024):
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(grad)
    margin = int(size * 0.06)
    radius = int(size * 0.22)
    for y in range(margin, size - margin):
        t = (y - margin) / max(1, (size - 2 * margin))
        c = lerp((37, 99, 235), (6, 182, 212), t)
        gdraw.line([(margin, y), (size - margin, y)], fill=c + (255,))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [margin, margin, size - margin, size - margin], radius=radius, fill=255
    )
    canvas.paste(grad, (0, 0), mask)
    draw = ImageDraw.Draw(canvas)

    bars = 7
    cx = size / 2
    cy = size / 2
    bar_w = size * 0.045
    gap = size * 0.035
    heights = [0.34, 0.56, 0.78, 1.0, 0.72, 0.48, 0.30]
    total = bars * bar_w + (bars - 1) * gap
    start_x = cx - total / 2
    for i, h in enumerate(heights):
        x0 = start_x + i * (bar_w + gap)
        x1 = x0 + bar_w
        bh = size * 0.38 * h
        y0 = cy - bh / 2
        y1 = cy + bh / 2
        draw.rounded_rectangle([x0, y0, x1, y1], radius=bar_w / 2, fill=(255, 255, 255, 240))

    slash_w = max(8, int(size * 0.04))
    draw.line([(size * 0.30, size * 0.70), (size * 0.70, size * 0.30)], fill=(15, 23, 42, 210), width=slash_w)
    draw.line([(size * 0.30, size * 0.70), (size * 0.70, size * 0.30)], fill=(255, 255, 255, 110), width=max(2, slash_w // 3))
    return canvas


def save_png(img, path, size):
    img.resize((size, size), Image.Resampling.LANCZOS).save(path, format="PNG")


def png_bytes(img, size):
    from io import BytesIO
    buf = BytesIO()
    img.resize((size, size), Image.Resampling.LANCZOS).save(buf, format="PNG")
    return buf.getvalue()


def write_ico(path, img, sizes):
    # PNG-compressed ICO (Vista+)
    entries = []
    for s in sizes:
        data = png_bytes(img, s)
        entries.append((s, data))
    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    dir_entries = b""
    payloads = b""
    for s, data in entries:
        w = 0 if s >= 256 else s
        h = 0 if s >= 256 else s
        dir_entries += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        payloads += data
    path.write_bytes(header + dir_entries + payloads)


def main():
    base = make_base(1024)
    save_png(base, OUT / "icon.png", 512)
    save_png(base, OUT / "32x32.png", 32)
    save_png(base, OUT / "128x128.png", 128)
    save_png(base, OUT / "128x128@2x.png", 256)
    for s, name in [
        (30, "Square30x30Logo.png"),
        (44, "Square44x44Logo.png"),
        (71, "Square71x71Logo.png"),
        (89, "Square89x89Logo.png"),
        (107, "Square107x107Logo.png"),
        (142, "Square142x142Logo.png"),
        (150, "Square150x150Logo.png"),
        (284, "Square284x284Logo.png"),
        (310, "Square310x310Logo.png"),
        (50, "StoreLogo.png"),
    ]:
        save_png(base, OUT / name, s)

    write_ico(OUT / "icon.ico", base, [16, 24, 32, 48, 64, 128, 256])
    # also export a preview for docs
    save_png(base, ROOT / "docs-icon-preview.png", 256)
    print("ico", (OUT / "icon.ico").stat().st_size)
    print("png", (OUT / "icon.png").stat().st_size)


if __name__ == "__main__":
    main()
