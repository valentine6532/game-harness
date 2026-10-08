"""Which layer shows at a pixel of a posed frame (and which rest-pose pixel of it).

Usage: python layer_at.py CLIP FRAME x,y [x,y ...]      (frame coordinates, reference px)
       python layer_at.py CLIP FRAME --map OUT.png [x0 y0 x1 y1]   (layer-coloured map + legend)
Draws every part with a flat unique colour through pose_render's own deformation, so the answer
matches what the review sheets show.
"""
import sys
import numpy as np
from PIL import Image, ImageDraw
import pose_render as pr  # the asset folder copy or this skill's scripts/review/pose_render.py

r = pr.Rig()
clip, frame = int(sys.argv[1]), sys.argv[2]
t = pr.parse_time(r, clip, frame)
names = [p["name"] for p in r.parts]
rng = np.random.RandomState(3)
cols = {n: (rng.randint(40, 255, 3)).astype(np.uint8) for n in names}
orig = dict(r.img)
for n in names:
    im = orig[n].copy()
    solid = np.zeros_like(im); solid[..., :3] = cols[n]; solid[..., 3] = np.where(im[..., 3] > 127, 255, 0)
    r.img[n] = solid
box = (0, 0, 1024, 1536)
if "--map" in sys.argv:
    i = sys.argv.index("--map"); out = sys.argv[i + 1]
    if len(sys.argv) > i + 2:
        box = tuple(int(v) for v in sys.argv[i + 2:i + 6])
img = np.asarray(pr.render(r, clip, t, box=box, scale=1.0, bg=(0, 0, 0), flash=False)).astype(int)
lut = {tuple(c.tolist()): n for n, c in cols.items()}
if "--map" in sys.argv:
    im = Image.fromarray(img.astype(np.uint8)); d = ImageDraw.Draw(im)
    seen = {}
    for y in range(0, img.shape[0], 6):
        for x in range(0, img.shape[1], 6):
            n = lut.get(tuple(img[y, x]))
            if n and n not in seen: seen[n] = (x, y)
    for n, (x, y) in seen.items():
        d.text((x, y), n, fill=(255, 255, 255))
    im.save(out); print("map", out, sorted(seen))
else:
    for a in sys.argv[3:]:
        x, y = (int(v) for v in a.split(","))
        c = tuple(img[y, x]); print((x, y), lut.get(c, "background" if c == (0, 0, 0) else f"mix {c}"))
