# -*- coding: utf-8 -*-
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ICON = ROOT / "src-tauri" / "icons" / "icon.png"
OUT = ROOT / "scripts" / "installer-art"
OUT.mkdir(parents=True, exist_ok=True)


def place_icon(canvas_size, icon_size, bg=(17, 24, 39)):
    canvas = Image.new("RGB", canvas_size, bg)
    icon = Image.open(ICON).convert("RGBA")
    icon = icon.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
    x = (canvas_size[0] - icon_size) // 2
    y = (canvas_size[1] - icon_size) // 2
    canvas.paste(icon, (x, y), icon)
    return canvas


def main():
    # NSIS MUI welcome bitmap: 164x314
    place_icon((164, 314), 120).save(OUT / "wizard-sidebar.bmp", format="BMP")
    # NSIS MUI header bitmap: 150x57
    place_icon((150, 57), 40, bg=(15, 23, 42)).save(OUT / "wizard-header.bmp", format="BMP")
    print("wrote from", ICON)


if __name__ == "__main__":
    main()
