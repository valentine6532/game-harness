"""Grow each limb piece a few px into the area a front part covers at rest.

Usage: python pad_limbs.py
Cloth in front of a limb sways a few px even in idle; without padding the gap between the cloth
edge and the limb showed the cloth behind the limb as a pale strip (review round 1, back calf).
The pad only goes where a part in front covers it at rest, so the rest pose is unchanged; its
colour is the limb's own edge continued (Telea inpaint).
"""
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from assemble_v12 import ORDER, LABEL_OF

HERE = Path(__file__).resolve().parent
LAB = np.load(HERE / "labelmap" / "owner.npy")
NAMES = json.loads((HERE / "labelmap" / "labels.json").read_text(encoding="utf-8"))["names"]
LIMBS = ["ThighL", "ShinL", "FootL", "ThighR", "ShinR", "FootR", "ForearmL", "ForearmR", "HandL"]
PAD = 6
SHEER = {"ChiffonL"}

for n in LIMBS:
    p = HERE / "layers" / f"{n}.png"
    img = np.asarray(Image.open(p).convert("RGBA")).copy()
    a = img[..., 3] > 128
    front = np.zeros(a.shape, bool)
    for m in ORDER[ORDER.index(n) + 1:]:
        l = LABEL_OF.get(m, m)
        if l in NAMES and l not in SHEER:     # under sheer cloth the pad would show through
            front |= LAB == NAMES.index(l)
    grow = (cv2.dilate(a.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * PAD + 1, 2 * PAD + 1))) > 0) & ~a & front
    if not grow.any():
        continue
    ys, xs = np.nonzero(grow | a)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    sub = np.ascontiguousarray(img[y0:y1, x0:x1, :3])
    img[y0:y1, x0:x1, :3] = cv2.inpaint(sub, (~a[y0:y1, x0:x1]).astype(np.uint8), 4, cv2.INPAINT_TELEA)
    img[grow, 3] = 255
    Image.fromarray(img).save(p)
    print(f"{n:9s} padded {int(grow.sum())} px")
