"""Rest-pose placement check and parts sheet for v012 (no rig yet).

Usage: python assemble_v12.py

Reads layers/<Name>.png (placed by fit_parts.py) in ORDER, writes:
  check/rest-pose.png          composite on grey
  check/rest-vs-reference.png  reference | composite | 50 % blend | silhouette diff
  check/parts-sheet.png        every part cropped at fitted scale, labelled
  check/silhouette.json        outside / uncovered / IoU against the reference
"""

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
LAYERS = HERE / "layers"
OUT = HERE / "check"

# back -> front
ORDER = [
    "SkirtBack", "HairBack", "ShawlPanelR", "ShawlPanelL", "Pelvis", "ChiffonR",
    "FootL", "ThighL", "ShinL", "FrontPanel", "FootR", "ThighR", "ShinR", "ChiffonL", "WaistDrape",
    "UpperArmL", "ForearmL", "HandL", "SleeveL", "UpperArmR", "ForearmR", "SleeveR",
    "Neck", "Chest", "WaistCharm", "FrontLockL", "Head",
    "HandR_back", "Staff", "HandR_front",
]
# layer -> label in labelmap/labels.npy (the part that is visible there at rest)
LABEL_OF = {"ThighR": "LegR", "ShinR": "LegR", "ThighL": "LegL", "ShinL": "LegL", "FootR": "ShoeR",
            "FootL": "ShoeL", "UpperArmL": "GloveL", "ForearmL": "GloveL", "HandR_back": "HandR",
            "HandR_front": "HandR"}
BG = (95, 95, 110, 255)


def load(name):
    p = LAYERS / f"{name}.png"
    return Image.open(p).convert("RGBA") if p.exists() else None


def main():
    OUT.mkdir(exist_ok=True)
    ref = Image.open(HERE / "reference.png").convert("RGBA")
    comp = Image.new("RGBA", ref.size, (0, 0, 0, 0))
    present, missing = [], []
    for n in ORDER:
        im = load(n)
        if im is None:
            missing.append(n)
            continue
        comp.alpha_composite(im)
        present.append(n)

    grey = Image.new("RGBA", ref.size, BG)
    grey.alpha_composite(comp)
    grey.convert("RGB").save(OUT / "rest-pose.png")

    a = np.asarray(ref)[:, :, 3] > 128
    b = np.asarray(comp)[:, :, 3] > 128
    outside = 100 * np.count_nonzero(b & ~a) / np.count_nonzero(a)
    uncovered = 100 * np.count_nonzero(a & ~b) / np.count_nonzero(a)
    iou = np.count_nonzero(a & b) / np.count_nonzero(a | b)
    diff = np.zeros((*a.shape, 3), np.uint8)
    diff[a & b] = (170, 170, 170)
    diff[a & ~b] = (0, 220, 255)
    diff[b & ~a] = (255, 65, 65)

    refg = Image.new("RGBA", ref.size, BG); refg.alpha_composite(ref)
    blend = Image.blend(refg.convert("RGB"), grey.convert("RGB"), 0.5)
    panels = [refg.convert("RGB"), grey.convert("RGB"), blend, Image.fromarray(diff)]
    f = ImageFont.truetype("malgun.ttf", 26)
    sheet = Image.new("RGB", (1024 * 4 + 30, 1536 + 50), (30, 30, 30))
    labels = ["원본", "v012 부위 배치(정지 자세)", "겹쳐 보기 50%",
              f"실루엣: 밖 {outside:.1f}% / 빈곳 {uncovered:.1f}%"]
    for i, (p, t) in enumerate(zip(panels, labels)):
        sheet.paste(p, (i * 1034, 50))
        ImageDraw.Draw(sheet).text((i * 1034 + 10, 10), t, fill=(255, 255, 255), font=f)
    sheet.resize((sheet.width // 2, sheet.height // 2), Image.LANCZOS).save(OUT / "rest-vs-reference.png")

    parts_sheet(present)
    rep = {"outside_pct": round(outside, 2), "uncovered_pct": round(uncovered, 2),
           "iou": round(float(iou), 4), "present": present, "missing": missing}
    (OUT / "silhouette.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False))


def parts_sheet(names, width=2400, pad=24):
    """Parts cropped at fitted scale (same px scale for all), packed in rows."""
    f = ImageFont.truetype("arial.ttf", 18)
    crops = []
    for n in names:
        im = load(n)
        bb = im.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox()
        if bb:
            crops.append((n, im.crop(bb)))
    rows, row, x, h = [], [], pad, 0
    for n, c in crops:
        if x + c.width + pad > width and row:
            rows.append((row, h)); row, x, h = [], pad, 0
        row.append((n, c, x)); x += c.width + pad; h = max(h, c.height)
    if row:
        rows.append((row, h))
    H = sum(h + pad + 26 for _, h in rows) + pad
    out = Image.new("RGBA", (width, H), (60, 60, 70, 255))
    d = ImageDraw.Draw(out)
    y = pad
    for row, h in rows:
        for n, c, x in row:
            tile = Image.new("RGBA", c.size, BG)
            tile.alpha_composite(c)
            out.paste(tile, (x, y + 26))
            d.text((x, y), n, fill=(255, 225, 120), font=f)
        y += h + pad + 26
    out.convert("RGB").save(OUT / "parts-sheet.png")


if __name__ == "__main__":
    main()
