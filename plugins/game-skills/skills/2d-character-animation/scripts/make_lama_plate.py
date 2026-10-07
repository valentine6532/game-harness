"""LaMa clean plate: the reference with chosen parts removed, continued by LaMa from the surrounding
reference pixels, so it is pixel-identical to the reference outside the removed area.

Usage: LAMA_MODEL=... <venv python> make_lama_plate.py
Run from a copy in the asset folder (next to labelmap/): set ANIM2D_SKILL to the skill folder.
Writes plate/plate-lama.png. Removed: the left arm (glove, hand) and the staff below y 600.
v013: the Codex plate below the waist is a repaint (details differ, median 14) and row interpolation
across the staff smeared the shawl and chiffon (review rounds 5-6); the left arm's own sway showed
grey/brown hidden paint on the shawl behind it (round 6).
"""
import json, os, sys
from pathlib import Path
import cv2, numpy as np
from PIL import Image
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(os.environ.get("ANIM2D_SKILL", HERE.parent)) / "scripts"))
from lama_fill import lama_fill  # noqa: E402
LAB = np.load(HERE / "labelmap" / "owner.npy")
NAMES = json.loads((HERE / "labelmap" / "labels.json").read_text(encoding="utf-8"))["names"]
REF = np.asarray(Image.open(HERE / "reference.png").convert("RGBA"))
A = REF[..., 3] > 128
ys = np.arange(LAB.shape[0])[:, None].repeat(LAB.shape[1], 1)
rgb = REF[..., :3].copy(); rgb[~A] = (20, 22, 36)
out = REF.copy()
removed = np.zeros(LAB.shape, bool)
for parts, ymin, close in ((["GloveL", "HandL"], 0, 91), (["Staff"], 0, 41)):   # the arm is ~60 px wide
    m = np.isin(LAB, [NAMES.index(n) for n in parts]) & (ys >= ymin)
    m = cv2.dilate(m.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    filled = lama_fill(rgb, m, grow=0)
    fig = cv2.morphologyEx((A & ~m).astype(np.uint8), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close, close))) > 0
    # inside the figure: the closing, or wherever LaMa did not continue the background colour (a thin
    # hem the prop lay on is missed by the closing; round 7). Background-coloured fill stays clear.
    bgish = np.linalg.norm(filled.astype(float) - (20, 22, 36), axis=-1) < 40
    inside = m & (fig | ~bgish)
    out[inside, :3] = filled[inside]; out[inside, 3] = 255
    out[m & ~fig, 3] = 0
    rgb[inside] = filled[inside]
    removed |= m
    print(parts, "removed", int(m.sum()), "filled inside the figure", int(inside.sum()))
Image.fromarray(out).save(HERE / "plate" / "plate-lama.png")
Image.fromarray((removed * 255).astype(np.uint8)).save(HERE / "plate" / "plate-lama-mask.png")
