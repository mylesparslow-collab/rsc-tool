"""Draws the app icon (icon.png, 1024 px) and RSC.icns on a Mac. Run: python packaging/make_icon.py OUTDIR"""
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
tile = Image.new("RGBA", (824, 824))
top, bottom = (43, 90, 67), (27, 63, 45)   # tokens.css --accent and --accent-strong
tp = tile.load()
for y in range(824):
    t = y / 823
    c = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (255,)
    for x in range(824):
        tp[x, y] = c
mask = Image.new("L", (824, 824), 0)
ImageDraw.Draw(mask).rounded_rectangle((0, 0, 823, 823), radius=185, fill=255)
img.paste(tile, (100, 100), mask)
d = ImageDraw.Draw(img)
font = None
for f in ("/System/Library/Fonts/Supplemental/Georgia Bold.ttf", "/System/Library/Fonts/NewYork.ttf", "/System/Library/Fonts/Helvetica.ttc"):
    try:
        font = ImageFont.truetype(f, 270); break
    except OSError:
        pass
font = font or ImageFont.load_default(size=270)
d.text((512, 470), "RSC", fill="white", font=font, anchor="mm")
d.rounded_rectangle((322, 640, 702, 676), radius=18, fill=(160, 121, 47))   # the brass bar
img.save(out / "icon.png")
if sys.platform == "darwin":
    iset = out / "RSC.iconset"; iset.mkdir(exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        img.resize((size, size), Image.LANCZOS).save(iset / f"icon_{size}x{size}.png")
        img.resize((size * 2, size * 2), Image.LANCZOS).save(iset / f"icon_{size}x{size}@2x.png")
    subprocess.run(["iconutil", "-c", "icns", str(iset), "-o", str(out / "RSC.icns")], check=True)
