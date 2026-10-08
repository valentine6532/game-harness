"""Replace hidden paint that copies the part in front of it.

Usage: python fix_hidden.py

Codex was told to continue each part behind the parts in front of it, but in places it painted
what image 2 shows there (the back leg holds a copy of the front leg and chiffon, the chest holds
copies of the sleeves). Those copies appear as ghosts when the front part moves.

- Limbs: the hidden area is replaced by the proportion-template limb of the same bone
  (layers_v1_backup, complete skin/glove/shoe paint), tone-matched to the visible reference part.
- Other parts: hidden pixels whose colour matches the reference there (a copy of the front part)
  are refilled from the part's own paint around them (Telea inpaint).
Visible pixels (reference art) are never changed.
"""

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from assemble_v12 import LABEL_OF, ORDER

HERE = Path(__file__).resolve().parent
LAB = np.load(HERE / "labelmap" / "owner.npy")
NAMES = json.loads((HERE / "labelmap" / "labels.json").read_text(encoding="utf-8"))["names"]
REF = np.asarray(Image.open(HERE / "reference.png").convert("RGB"))
REF_LAB = cv2.cvtColor(cv2.GaussianBlur(REF, (0, 0), 1.5), cv2.COLOR_RGB2LAB).astype(float)
LIMB_SOURCE = {n: n for n in ("ThighR", "ShinR", "ThighL", "ShinL", "UpperArmL", "ForearmL", "ForearmR", "FootR", "FootL")}
COPY_DIFF = 14.0
REFILL_ALL_HIDDEN = {"Chest"}      # its hidden paint copies the sleeves and hair: refill from skin / corset
SKIP = {"Staff", "HandL", "HandR_back", "HandR_front", "WaistCharm", "SkirtBack", "Pelvis", "UpperArmR"}


def vis_of(n):
    l = LABEL_OF.get(n, n)
    return LAB == NAMES.index(l) if l in NAMES else np.zeros(LAB.shape, bool)


def tone_to(src, img, vis, sigma=9.0):
    """Shift src's low frequencies to img's visible paint near the visible boundary."""
    w = cv2.GaussianBlur(vis.astype(np.float32), (0, 0), sigma)
    out = src.astype(np.float32).copy()
    for c in range(3):
        d = cv2.GaussianBlur((img[..., c].astype(np.float32) - out[..., c]) * vis, (0, 0), sigma) / np.maximum(w, 1e-3)
        out[..., c] += d * np.clip(w * 4, 0, 1)
    return np.clip(out, 0, 255)


def inpaint_region(img, mask):
    a = img[..., 3] > 128
    ys, xs = np.nonzero(a)
    x0, y0, x1, y1 = max(xs.min() - 8, 0), max(ys.min() - 8, 0), xs.max() + 9, ys.max() + 9
    sub = np.ascontiguousarray(img[y0:y1, x0:x1, :3])
    m = (mask | ~a)[y0:y1, x0:x1].astype(np.uint8)
    img[y0:y1, x0:x1, :3] = cv2.inpaint(sub, m, 6, cv2.INPAINT_TELEA)
    return img


def main():
    for n in ORDER:
        if n in SKIP:
            continue
        p = HERE / "layers" / f"{n}.png"
        img = np.asarray(Image.open(p).convert("RGBA")).copy()
        a = img[..., 3] > 128
        vis = vis_of(n) & a
        hidden = a & ~cv2.dilate(vis.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
        if n in LIMB_SOURCE:
            src = np.asarray(Image.open(HERE / "layers_v1_backup" / f"{LIMB_SOURCE[n]}.png").convert("RGBA"))
            sa = src[..., 3] > 128
            toned = tone_to(src[..., :3], img, vis)
            use = hidden & sa
            img[use, :3] = toned[use].astype(np.uint8)
            copy = hidden & ~sa
            img[copy, 3] = 0                                   # outside the limb shape: generated paint is unreliable, drop it
            print(f"{n:12s} hidden {hidden.sum():6d}  from template limb {use.sum():6d}  dropped copies {copy.sum():6d}")
        else:
            gl = cv2.cvtColor(cv2.GaussianBlur(np.ascontiguousarray(img[..., :3]), (0, 0), 1.5), cv2.COLOR_RGB2LAB).astype(float)
            copy = hidden & (np.linalg.norm(gl - REF_LAB, axis=2) < COPY_DIFF)
            if n in REFILL_ALL_HIDDEN:
                copy = hidden.copy()
            copy = cv2.morphologyEx(copy.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
            if copy.sum() > 50:
                img = inpaint_region(img, cv2.dilate(copy.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool) & hidden)
            print(f"{n:12s} hidden {hidden.sum():6d}  copied->refilled {copy.sum():6d}")
        Image.fromarray(img).save(p)


if __name__ == "__main__":
    main()
