"""Continue each part's VISIBLE art into its hidden band with LaMa, so what motion reveals looks
like the part itself (review 2026-09-29: blue/white blotches appeared between the legs where the
generated hidden paint did not match the visible sheer chiffon / panel).

Run with the LaMa venv:
  LAMA_MODEL=D:/ai-tools/models/big-lama.pt D:/ai-tools/venv/Scripts/python.exe lama_hidden.py [PART ...]

Per layer: context = reference pixels where the part is visible at rest + its current paint
elsewhere; hole = hidden pixels within BAND px of the visible region. Beyond the band the
existing paint stays, blended over MIX px. SkirtBack (never visible) becomes a plate of what the
reference shows in front of it, with legs, shoes and staff removed by LaMa, so small cloth swings
reveal matching colours.
"""
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(os.environ.get("ANIM2D_SKILL", Path(__file__).resolve().parents[2])) / "scripts"))
from lama_fill import lama_fill  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from assemble_v12 import LABEL_OF  # noqa: E402

LAB = np.load(HERE / "labelmap" / "owner.npy")
NAMES = json.loads((HERE / "labelmap" / "labels.json").read_text(encoding="utf-8"))["names"]
REF = np.asarray(Image.open(HERE / "reference.png").convert("RGBA"))
BAND, MIX = 70, 16
FULL = {"Chest": 10000, "Neck": 10000}      # whole hidden region re-painted from the visible part
BAND_OF = {"HairBack": 40}
EXTEND_UNDER_OLD = {"HairBack": {"under": ["SleeveR", "ShawlPanelR", "ForearmR", "Chest"],
                             "box": [640, 300, 800, 640], "px": 140, "mirror": True}}
EXTEND_UNDER = {}          # the hair behind the staff arm now comes from the clean plate (plate_fill.py)
TRIM_OUTWARD = {"Chest": "right", "WaistDrape": "right"}
ACROSS_STAFF = {"ChiffonR", "ShawlPanelR", "FrontPanel"}
OFF_COLOUR = {"HairBack": lambda h: (h[..., 2] > 0.55) & (h[..., 1] < 0.45) & (h[..., 0] < 0.2),
              "ChiffonR": lambda h: h[..., 1] < 0.22, "ChiffonL": lambda h: h[..., 1] < 0.22}
PARTS = ["FrontPanel", "ChiffonR", "ChiffonL", "ShawlPanelL", "ShawlPanelR", "HairBack", "WaistDrape",
         "SleeveL", "SleeveR", "Neck", "Chest", "FrontLockL"]
NOT_CLOTH = ["LegR", "LegL", "ShoeR", "ShoeL", "Staff", "HandL", "GloveL", "WaistCharm"]


def label(n):
    l = LABEL_OF.get(n, n)
    return LAB == NAMES.index(l) if l in NAMES else np.zeros(LAB.shape, bool)


def _runs(xs):
    out, start = [], xs[0]
    for a, b in zip(xs, xs[1:]):
        if b != a + 1:
            out.append((start, a)); start = b
    out.append((start, xs[-1]))
    return out


def continue_part(n):
    p = HERE / "layers" / f"{n}.png"
    img = np.asarray(Image.open(p).convert("RGBA")).copy()
    a = img[..., 3] > 128
    vis = label(n) & a
    # close the layer across the staff where the staff separated it (the pommel left a gap at the hem)
    if n in ACROSS_STAFF:
        from assemble_v12 import ORDER
        front = np.zeros(LAB.shape, bool)
        for m in ORDER[ORDER.index(n) + 1:]:
            l = LABEL_OF.get(m, m)
            if l in NAMES:
                front |= LAB == NAMES.index(l)
        closed = cv2.morphologyEx(a.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((1, 141), np.uint8)) > 0
        add = closed & front & ~a
        img[add, 3] = 255
        a = a | add
        # under the staff the part only exists where it bridges across it (no stalks above/below)
        staff = LAB == NAMES.index("Staff")
        bridge = cv2.morphologyEx(vis.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((1, 141), np.uint8)) > 0
        cut = a & staff & ~bridge
        img[cut, 3] = 0
        a = a & ~cut
    if n in EXTEND_UNDER:
        # continue the part behind parts that swing away from it (back hair behind the staff
        # arm's sleeve: a dark gap opened beside the bust, review round 1)
        under = np.zeros(LAB.shape, bool)
        for m in EXTEND_UNDER[n]["under"]:
            under |= LAB == NAMES.index(m)
        x0, y0, x1, y1 = EXTEND_UNDER[n]["box"]
        box = np.zeros(LAB.shape, bool); box[y0:y1, x0:x1] = True
        near = cv2.distanceTransform((~vis).astype(np.uint8), cv2.DIST_L2, 5) <= EXTEND_UNDER[n]["px"]
        add = under & box & near & ~a
        img[add, 3] = 255
        a = a | add
    dist = cv2.distanceTransform((~vis).astype(np.uint8), cv2.DIST_L2, 5)
    band_px = FULL.get(n, BAND_OF.get(n, BAND))
    if n in EXTEND_UNDER:
        band_px = max(band_px, EXTEND_UNDER[n]["px"] + 10)
    hole = a & ~vis & (dist <= band_px)
    if n in OFF_COLOUR:                      # generated paint that is not this part's colour (copied shawl in the hair)
        hsv = cv2.cvtColor(img[..., :3], cv2.COLOR_RGB2HSV_FULL).astype(float) / 255
        ok = OFF_COLOUR[n](hsv)
        off = a & ~vis & ~ok
        off = cv2.dilate(off.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
        hole |= off & a & ~vis
    if n in TRIM_OUTWARD:
        # hidden paint must not bulge sideways past the visible part (a skin blob grew beside the
        # bust and showed when the staff arm lifted)
        side = TRIM_OUTWARD[n]
        rows = np.where(vis.any(1))[0]
        for y in rows:
            xs = np.nonzero(vis[y])[0]
            if side == "right":
                a[y, xs.max() + 4:] = False
        img[~a, 3] = 0
        hole &= a
    ctx = img[..., :3].copy()
    ctx[vis] = REF[..., :3][vis]
    # outside the layer is unknown too (else LaMa pulls the dark background into the part)
    ring = (cv2.dilate(a.astype(np.uint8), np.ones((41, 41), np.uint8)) > 0) & ~a
    filled = lama_fill(ctx, hole | ring, grow=0)
    w = np.clip((band_px - dist) / MIX, 0, 1)[..., None]        # 1 inside the band, fades out past it
    band = a & ~vis & (dist <= band_px + MIX)
    out = img.copy()
    out[..., :3][band] = (filled[band] * w[band] + img[..., :3][band] * (1 - w[band])).astype(np.uint8)
    if n in EXTEND_UNDER and EXTEND_UNDER[n].get("mirror"):
        # large extensions: LaMa blurs them; mirror the part's real texture on the same row instead
        ext = a & ~vis & (dist <= band_px) & (np.arange(LAB.shape[1])[None, :] >= EXTEND_UNDER[n]["box"][0])
        ext &= np.arange(LAB.shape[0])[:, None] >= EXTEND_UNDER[n]["box"][1]
        ext &= np.arange(LAB.shape[0])[:, None] < EXTEND_UNDER[n]["box"][3]
        tex = cv2.erode(vis.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        src = REF[..., :3]
        # copy whole 2-D patches of the real hair shifted sideways (keeps the strand direction;
        # per-row mirroring left horizontal streaks)
        todo = ext.copy()
        ys, xs = np.nonzero(todo)
        for dx in EXTEND_UNDER[n].get("shifts", [60, 90, 120, -60, -90]):
            sx = np.clip(xs + dx, 0, LAB.shape[1] - 1)
            ok = todo[ys, xs] & tex[ys, sx]
            out[ys[ok], xs[ok], :3] = src[ys[ok], sx[ok]]
            todo[ys[ok], xs[ok]] = False
        sm = cv2.GaussianBlur(out[..., :3], (0, 0), 0.8)
        out[..., :3][ext] = sm[ext]
    if n in ACROSS_STAFF:
        # the strip where the staff crossed: interpolate the part's own colours from both sides of
        # each row (LaMa filled it grey from the staff's outline)
        staff = (LAB == NAMES.index("Staff")) & a & ~vis
        core = cv2.erode(vis.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
        for y in np.nonzero(staff.any(1))[0]:
            xs = np.nonzero(staff[y])[0]
            for x0, x1 in _runs(xs):
                L = np.nonzero(core[y, max(x0 - 40, 0):x0])[0]
                R = np.nonzero(core[y, x1 + 1:x1 + 41])[0]
                if len(L) and len(R):
                    cl = REF[y, max(x0 - 40, 0) + L[-1], :3].astype(float)
                    cr = REF[y, x1 + 1 + R[0], :3].astype(float)
                    t = np.linspace(0, 1, x1 - x0 + 1)[:, None]
                    out[y, x0:x1 + 1, :3] = (cl * (1 - t) + cr * t).astype(np.uint8)
                elif len(L) or len(R):
                    c = REF[y, (max(x0 - 40, 0) + L[-1]) if len(L) else (x1 + 1 + R[0]), :3]
                    out[y, x0:x1 + 1, :3] = c
    Image.fromarray(out).save(p)
    print(f"{n:12s} visible {vis.sum():6d}  band filled {hole.sum():6d}")


def skirt_plate():
    p = HERE / "layers" / "SkirtBack.png"
    img = np.asarray(Image.open(p).convert("RGBA")).copy()
    a = img[..., 3] > 128
    cloth = REF[..., 3] > 128
    for n in NOT_CLOTH:
        cloth &= LAB != NAMES.index(n)
    below_waist = np.arange(LAB.shape[0])[:, None] > 600
    hole = a & ~cloth
    ctx = REF[..., :3].copy()
    ctx[~(REF[..., 3] > 128)] = (20, 22, 36)
    filled = lama_fill(ctx, hole & below_waist, grow=4, keep=a)
    plate = cv2.GaussianBlur(np.where(cloth[..., None], REF[..., :3], filled), (0, 0), 2.5)   # soft: never a sharp duplicate
    out = img.copy()
    sel = a & below_waist
    out[..., :3][sel] = plate[sel]
    # the underskirt only lives inside the dress (behind chiffon, front panel and legs), never
    # under the shawl panels: there a moving panel revealed a copy of the hem
    inner = np.zeros(LAB.shape, bool)
    for n in ["ChiffonL", "ChiffonR", "FrontPanel", "LegR", "LegL", "ShoeR", "ShoeL"]:
        inner |= LAB == NAMES.index(n)
    inner = cv2.dilate(inner.astype(np.uint8), np.ones((31, 31), np.uint8)) > 0
    inner &= ~(cv2.erode(((LAB == NAMES.index("ShawlPanelL")) | (LAB == NAMES.index("ShawlPanelR"))).astype(np.uint8),
                         np.ones((9, 9), np.uint8)) > 0)
    out[..., 3][~inner] = 0
    # stay 12 px inside the silhouette: the underskirt must never slide out below the hems
    inside = cv2.erode((REF[..., 3] > 128).astype(np.uint8), np.ones((25, 25), np.uint8)) > 0
    out[..., 3][~inside] = 0
    Image.fromarray(out).save(p)
    print(f"SkirtBack    plate {sel.sum():6d}  legs/staff refilled {int((hole & below_waist).sum()):6d}")


if __name__ == "__main__":
    todo = sys.argv[1:] or PARTS + ["SkirtBack"]
    for n in todo:
        skirt_plate() if n == "SkirtBack" else continue_part(n)
