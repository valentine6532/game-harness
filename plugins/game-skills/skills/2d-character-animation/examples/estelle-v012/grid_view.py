"""Gridded zoom of a generated sheet for picking joint centres: python grid_view.py SHEET x0 y0 x1 y1 OUT [step]"""
import sys
from PIL import Image, ImageDraw, ImageFont
sheet, x0, y0, x1, y1, out = sys.argv[1], *map(int, sys.argv[2:6]), sys.argv[6]
step = int(sys.argv[7]) if len(sys.argv) > 7 else 25
im = Image.open(f"gen/{sheet}.png").convert("RGBA")
bg = Image.new("RGBA", im.size, (95, 95, 110, 255)); bg.alpha_composite(im)
c = bg.crop((x0, y0, x1, y1))
k = max(1, min(1000 // (x1 - x0), 1000 // (y1 - y0)))
k = max(k, 1)
c = c.resize(((x1 - x0) * k, (y1 - y0) * k), Image.NEAREST if k > 2 else Image.LANCZOS)
d = ImageDraw.Draw(c); f = ImageFont.truetype("arial.ttf", 12)
for x in range((x0 // step + 1) * step, x1, step):
    X = (x - x0) * k; d.line([(X, 0), (X, c.height)], fill=(255, 60, 60) if x % (step * 4) == 0 else (255, 170, 170), width=1)
    if x % (step * 2) == 0: d.text((X + 2, 2), str(x), fill=(255, 255, 0), font=f)
for y in range((y0 // step + 1) * step, y1, step):
    Y = (y - y0) * k; d.line([(0, Y), (c.width, Y)], fill=(60, 60, 255) if y % (step * 4) == 0 else (170, 170, 255), width=1)
    if y % (step * 2) == 0: d.text((2, Y + 2), str(y), fill=(0, 255, 255), font=f)
c.convert("RGB").save(out)
