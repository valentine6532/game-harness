"""Rest-pose review: the processed rig layers (as Unity gets them) composited in draw order, next
to the reference, for every body region. Writes check/review2/<nn-region>.png and colour stats.

Usage: python review_regions.py [OUTDIR]
"""
import sys, json
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont
import rig_v12 as rig

out = sys.argv[1] if len(sys.argv) > 1 else "check/review2"
import os; os.makedirs(out, exist_ok=True)
L = rig.load_layers()
comp = Image.new("RGBA", (1024, 1536), (11, 12, 26, 255))
for n in rig.ORDER:
    comp.alpha_composite(Image.fromarray(L[n], "RGBA"))
comp.convert("RGB").save(f"{out}/rest-full.png")
ref = Image.new("RGBA", (1024, 1536), (11, 12, 26, 255)); ref.alpha_composite(Image.open("reference.png").convert("RGBA"))
R = {"01-head": (380, 0, 700, 300), "02-neck-chest": (430, 220, 720, 480), "03-leftarm": (90, 300, 500, 860),
     "04-rightarm": (560, 230, 900, 640), "05-waist": (420, 500, 740, 820), "06-left-shawl-top": (60, 560, 480, 1000),
     "07-left-shawl-bottom": (0, 950, 520, 1520), "08-right-shawl": (680, 480, 1000, 1400), "09-centre-skirt": (380, 760, 720, 1300),
     "10-legs-feet": (400, 1150, 760, 1520), "11-staff-top": (700, 0, 900, 420), "12-hem": (0, 1250, 1024, 1536), "13-hair-left": (150, 150, 480, 850)}
f = ImageFont.truetype("malgun.ttf", 22)
ra = cv2.cvtColor(cv2.GaussianBlur(np.asarray(ref.convert("RGB")), (0, 0), 2), cv2.COLOR_RGB2LAB).astype(float)
ca = cv2.cvtColor(cv2.GaussianBlur(np.asarray(comp.convert("RGB")), (0, 0), 2), cv2.COLOR_RGB2LAB).astype(float)
d = np.linalg.norm(ra - ca, axis=2)
A = np.asarray(Image.open("reference.png").convert("RGBA"))[..., 3] > 128
stats = {}
for k, box in R.items():
    x0, y0, x1, y1 = box
    m = A[y0:y1, x0:x1]
    stats[k] = {"median_lab_diff": round(float(np.median(d[y0:y1, x0:x1][m])), 1),
                "share_over_25": round(float((d[y0:y1, x0:x1][m] > 25).mean()), 3)}
    a = ref.crop(box).convert("RGB"); b = comp.crop(box).convert("RGB")
    sc = min(1.0, 700 / a.width)
    if a.height < 500: sc = min(2.0, 500 / a.height)
    a = a.resize((int(a.width * sc), int(a.height * sc))); b = b.resize(a.size)
    o = Image.new("RGB", (a.width * 2 + 10, a.height + 34), (30, 30, 30)); dr = ImageDraw.Draw(o)
    o.paste(a, (0, 34)); o.paste(b, (a.width + 10, 34)); dr.text((6, 4), "원본 " + k, fill="white", font=f); dr.text((a.width + 16, 4), "v012 수정", fill="white", font=f)
    o.save(f"{out}/{k}.png")
m = A
stats["_all"] = {"median_lab_diff": round(float(np.median(d[m])), 1), "share_over_25": round(float((d[m] > 25).mean()), 3)}
json.dump(stats, open(f"{out}/stats.json", "w"), indent=1)
for k, v in stats.items(): print(k, v)
