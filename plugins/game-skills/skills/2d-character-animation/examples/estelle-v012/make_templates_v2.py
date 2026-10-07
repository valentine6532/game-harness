"""Templates v2: every part's template = where it is VISIBLE in the reference (labelmap/labels.npy)
plus a hidden continuation only under the parts drawn in FRONT of it (ORDER_V2).

Usage: python make_templates_v2.py

The v1 templates were grown from generated shapes and colour regions, so sleeves, drape and
chiffon covered areas that belong to other parts (review 2026-09-29). Here the visible outline of
each part comes from the per-part map of the reference; nothing is painted where another part
shows at rest.

Writes template/v2-<sheet>.png / .json (sheets never contain overlapping masks) and
template/v2-preview.png.
"""

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
W, H = 1024, 1536
LAB = np.load(HERE / "labelmap" / "labels.npy")
NAMES = json.loads((HERE / "labelmap" / "labels.json").read_text(encoding="utf-8"))["names"]
A = np.asarray(Image.open(HERE / "reference.png").convert("RGBA"))[..., 3] > 128

# back -> front. Label names that are not parts themselves (LegR, LegL, ShoeR, ShoeL, GloveL, HandL,
# ForearmR, HandR, Staff, Head) are covered by kept parts; they still count as "in front".
ORDER_V2 = [
    "SkirtBack", "HairBack", "ShawlPanelR", "ShawlPanelL", "ChiffonR",
    "ShoeL", "LegL", "FrontPanel", "ShoeR", "LegR", "ChiffonL", "WaistDrape",
    "GloveL", "HandL", "SleeveL", "ForearmR", "SleeveR", "Neck", "Chest", "WaistCharm", "FrontLockL", "Head",
    "HandR", "Staff",
]
ONLY = __import__("sys").argv[1:]          # regenerate a subset: python make_templates_v2.py ChiffonR ShawlPanelR
REGENERATE = ["HairBack", "ShawlPanelR", "ShawlPanelL", "ChiffonR", "FrontPanel", "ChiffonL",
              "WaistDrape", "SleeveL", "Neck", "Chest", "WaistCharm", "FrontLockL", "SleeveR"]
EXTEND = {"LegR": 60, "LegL": 70, "ShoeR": 30, "ShoeL": 30, "GloveL": 45, "ForearmR": 45, "HairBack": 90, "FrontPanel": 80, "ChiffonR": 60, "ChiffonL": 45, "ShawlPanelL": 50,
          "ShawlPanelR": 50, "Chest": 45, "Neck": 35, "WaistDrape": 30, "SleeveL": 25, "SleeveR": 25,
          "FrontLockL": 20, "WaistCharm": 6}
THIN, THIN_R = ("Staff",), 22
NO_EXTEND_UNDER = {"HairBack": ("GloveL", "HandL", "Staff", "HandR", "ForearmR", "WaistDrape", "WaistCharm")}
ZONE_MAX_Y = {"HairBack": 900, "Neck": 360, "Chest": 700, "SleeveL": 700, "SleeveR": 650,
              "WaistDrape": 800, "FrontLockL": 600}


def disk(r):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def fill_holes(m):
    ff = m.astype(np.uint8).copy()
    cv2.floodFill(ff, np.zeros((H + 2, W + 2), np.uint8), (0, 0), 1)
    return m | (ff == 0)


def visible(name):
    return LAB == NAMES.index(name)


def template(name):
    vis = visible(name)
    front = np.zeros((H, W), bool)
    thin = np.zeros((H, W), bool)
    for n in ORDER_V2[ORDER_V2.index(name) + 1:]:
        if n in NAMES and n not in NO_EXTEND_UNDER.get(name, ()):
            (thin if n in THIN else front)[:] |= visible(n)
    grow = cv2.dilate(vis.astype(np.uint8), disk(EXTEND[name])) > 0
    # under a thin prop (the staff) a part only continues across the prop from both sides,
    # never along it
    across = cv2.dilate(vis.astype(np.uint8), disk(THIN_R)) > 0
    t = vis | (grow & front) | (across & thin)
    front |= thin
    t = cv2.morphologyEx(t.astype(np.uint8), cv2.MORPH_CLOSE, disk(4)) > 0
    t = fill_holes(t) & (vis | front)          # never over background or parts behind it
    if name in ZONE_MAX_Y:
        t[ZONE_MAX_Y[name]:] &= vis[ZONE_MAX_Y[name]:]
    return t, vis


def main():
    out = HERE / "template"
    T = {}
    regen = ONLY or REGENERATE
    for n in regen:
        T[n], vis = template(n)
        print(f"{n:12s} visible {vis.sum():6d}  template {T[n].sum():6d}")
    # greedy sheets: masks (grown 8 px) never overlap within a sheet
    sheets = []
    for n in sorted(regen, key=lambda k: -T[k].sum()):
        g = cv2.dilate(T[n].astype(np.uint8), disk(8)) > 0
        for s in sheets:
            if not (g & s["used"]).any():
                s["parts"].append(n); s["used"] |= g; break
        else:
            sheets.append({"parts": [n], "used": g.copy()})
    for i, s in enumerate(sheets, 1):
        sheet = f"v2-S{i}" if not ONLY else f"v2-R{i}"
        im = np.zeros((H, W, 4), np.uint8)
        info = {"scale": 1.0, "inplace": True, "parts": {}}
        for n in s["parts"]:
            im[T[n]] = (200, 200, 200, 255)
            Image.fromarray((T[n] * 255).astype(np.uint8)).save(out / f"{sheet}-{n}.png")
            ys, xs = np.nonzero(T[n])
            info["parts"][n] = {"mask": f"{sheet}-{n}.png", "bbox": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
                                "px": int(T[n].sum())}
        Image.fromarray(im).save(out / f"{sheet}.png")
        (out / f"{sheet}.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
        print(sheet, s["parts"])
    ref = np.asarray(Image.open(HERE / "reference.png").convert("RGB"))
    prev = (ref * 0.45 + 255 * 0.55).astype(np.uint8)
    rng = np.random.RandomState(5)
    for n in regen:
        c = tuple(int(v) for v in rng.randint(0, 200, 3))
        cs, _ = cv2.findContours(T[n].astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(prev, cs, -1, c, 2)
        ys, xs = np.nonzero(T[n])
        cv2.putText(prev, n, (int(np.median(xs)) - 30, int(np.median(ys))), cv2.FONT_HERSHEY_SIMPLEX, 0.55, c, 2)
    Image.fromarray(prev).save(out / "v2-preview.png")


if __name__ == "__main__":
    main()
