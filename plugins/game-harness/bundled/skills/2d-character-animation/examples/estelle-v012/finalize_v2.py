"""Finish a generated in-place part: reference art where the part is visible at rest, generated
paint (tone-matched) where it is hidden, blended over BLEND px.

Usage: python finalize_v2.py SHEET PART[=LAYER][:LABEL] ...
  e.g. python finalize_v2.py v2-S6 Chest       python finalize_v2.py v2-L1 GloveL=GloveLfull

Codex paints the right part in the right place, but details inside large regions drift (corset line,
choker pendant, knee). Automatic registration fails (too few matching features), so the visible
region takes the approved art and the generated paint supplies only what is hidden. The
silhouette edge keeps the reference's anti-aliased alpha.
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
BLEND = 10.0
SIGMA = 9.0
OUTDIR = __import__("os").environ.get("FIN_OUT", "layers")
REFA = np.asarray(Image.open(HERE / "reference.png").convert("RGBA")).astype(np.float32)
REF = REFA[..., :3]
LAB = np.load(HERE / "labelmap" / "owner.npy")
NAMES = json.loads((HERE / "labelmap" / "labels.json").read_text(encoding="utf-8"))["names"]


def finalize(sheet, part, layer=None, label=None):
    layer, label = layer or part, label or part
    if sheet == "--kept":        # an existing layer: its own alpha is the template
        img = np.asarray(Image.open(HERE / "layers" / f"{part}.png").convert("RGBA")).astype(np.float32)
        tmpl = img[..., 3] > 128
    else:
        img = np.asarray(Image.open(HERE / "layers_t" / sheet / f"{part}.png").convert("RGBA")).astype(np.float32)
        tmpl = np.asarray(Image.open(HERE / "template" / f"{sheet}-{part}.png")) > 128
    vis = LAB == NAMES.index(label)          # owner map: includes the edge ring this part owns
    tmpl = tmpl | vis
    # 1) low-frequency tone match of the generated paint to the reference (visible region)
    w = cv2.GaussianBlur(vis.astype(np.float32), (0, 0), SIGMA)
    gen = img[..., :3].copy()
    for c in range(3):
        d = cv2.GaussianBlur((REF[..., c] - gen[..., c]) * vis, (0, 0), SIGMA) / np.maximum(w, 1e-3)
        gen[..., c] += d * (w > 0.02)
    gen = np.clip(gen, 0, 255)
    # 2) reference inside the visible region, blend into the generated paint outside it
    dist = cv2.distanceTransform((~vis).astype(np.uint8), cv2.DIST_L2, 5)
    k = np.clip(1 - dist / BLEND, 0, 1)[..., None]
    out = np.zeros_like(img)
    out[..., :3] = REF * k + gen * (1 - k)
    out[..., 3] = np.where(tmpl, 255, 0)
    # 3) silhouette edge: where the part meets the background at rest, take the reference alpha
    bg = REFA[..., 3] <= 128
    edge = (cv2.dilate(vis.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & bg
    out[edge, :3] = REF[edge]
    out[edge, 3] = REFA[edge, 3]
    Image.fromarray(out.astype(np.uint8)).save(HERE / OUTDIR / f"{layer}.png")
    print(f"{layer:12s} visible {vis.sum():6d}  hidden {int((tmpl & ~vis).sum()):6d}")


if __name__ == "__main__":
    sheet = sys.argv[1]
    for a in sys.argv[2:]:
        label = a.split(":")[1] if ":" in a else None
        a = a.split(":")[0]
        part, layer = (a.split("=") + [None])[:2]
        finalize(sheet, part, layer, label)
