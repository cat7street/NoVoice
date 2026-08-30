# -*- coding: utf-8 -*-
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scripts" / "installer-art"
OUT.mkdir(parents=True, exist_ok=True)


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def rounded_rect(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def make_sidebar(w=164, h=314):
    img = Image.new("RGB", (w, h), (17, 24, 39))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        c = lerp((30, 64, 175), (8, 145, 178), t)
        draw.line([(0, y), (w, y)], fill=c)

    # soft overlay panel
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle([12, 18, w - 12, h - 18], radius=18, fill=(15, 23, 42, 70))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # waveform
    cx, cy = w / 2, h * 0.42
    bars = 7
    bar_w = 8
    gap = 6
    heights = [0.35, 0.55, 0.78, 1.0, 0.7, 0.48, 0.32]
    total = bars * bar_w + (bars - 1) * gap
    x0 = cx - total / 2
    for i, hh in enumerate(heights):
        bh = 70 * hh
        x = x0 + i * (bar_w + gap)
        draw.rounded_rectangle([x, cy - bh / 2, x + bar_w, cy + bh / 2], radius=4, fill=(255, 255, 255))

    # slash
    draw.line([(42, 190), (122, 110)], fill=(15, 23, 42), width=8)
    draw.line([(42, 190), (122, 110)], fill=(255, 255, 255), width=2)

    # title
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 22)
        font2 = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 12)
    except Exception:
        font = ImageFont.load_default()
        font2 = font
    draw.text((w / 2, 230), "NoVoice", fill=(255, 255, 255), font=font, anchor="mm")
    draw.text((w / 2, 258), "Vocal Remover", fill=(219, 234, 254), font=font2, anchor="mm")
    return img


def make_header(w=150, h=57):
    img = Image.new("RGB", (w, h), (30, 64, 175))
    draw = ImageDraw.Draw(img)
    for x in range(w):
        t = x / max(1, w - 1)
        c = lerp((37, 99, 235), (6, 182, 212), t)
        draw.line([(x, 0), (x, h)], fill=c)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 16)
    except Exception:
        font = ImageFont.load_default()
    draw.text((14, h / 2), "NoVoice Setup", fill=(255, 255, 255), font=font, anchor="lm")
    return img


def main():
    make_sidebar().save(OUT / "wizard-sidebar.bmp", format="BMP")
    make_header().save(OUT / "wizard-header.bmp", format="BMP")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
