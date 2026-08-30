# -*- coding: utf-8 -*-
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scripts" / "installer-art"
OUT.mkdir(parents=True, exist_ok=True)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def make_sidebar(w=164, h=314):
    # clean dark gradient, no text, no slash
    img = Image.new("RGB", (w, h), (17, 24, 39))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        c = lerp((17, 24, 39), (30, 64, 175), t * 0.85)
        draw.line([(0, y), (w, y)], fill=c)

    # soft card
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    cd = ImageDraw.Draw(card)
    cd.rounded_rectangle([14, 56, w - 14, h - 56], radius=22, fill=(15, 23, 42, 120))
    img = Image.alpha_composite(img.convert("RGBA"), card).convert("RGB")
    draw = ImageDraw.Draw(img)

    # waveform only
    cx, cy = w / 2, h / 2
    bars = 7
    bar_w = 9
    gap = 7
    heights = [0.32, 0.52, 0.76, 1.0, 0.68, 0.46, 0.28]
    total = bars * bar_w + (bars - 1) * gap
    x0 = cx - total / 2
    for i, hh in enumerate(heights):
        bh = 96 * hh
        x = x0 + i * (bar_w + gap)
        draw.rounded_rectangle(
            [x, cy - bh / 2, x + bar_w, cy + bh / 2],
            radius=4,
            fill=(255, 255, 255),
        )
    return img


def make_header(w=150, h=57):
    img = Image.new("RGB", (w, h), (30, 64, 175))
    draw = ImageDraw.Draw(img)
    for x in range(w):
        t = x / max(1, w - 1)
        c = lerp((30, 64, 175), (8, 145, 178), t)
        draw.line([(x, 0), (x, h)], fill=c)
    # tiny waveform mark, no text
    bars = 5
    bar_w = 4
    gap = 3
    heights = [0.4, 0.7, 1.0, 0.65, 0.35]
    total = bars * bar_w + (bars - 1) * gap
    x0 = 18
    cy = h / 2
    for i, hh in enumerate(heights):
        bh = 22 * hh
        x = x0 + i * (bar_w + gap)
        draw.rounded_rectangle([x, cy - bh / 2, x + bar_w, cy + bh / 2], radius=2, fill=(255, 255, 255))
    return img


def main():
    make_sidebar().save(OUT / "wizard-sidebar.bmp", format="BMP")
    make_header().save(OUT / "wizard-header.bmp", format="BMP")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
