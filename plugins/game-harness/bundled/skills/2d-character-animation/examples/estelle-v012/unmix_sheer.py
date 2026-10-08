"""Un-bake the legs from the sheer chiffon.

Usage: python unmix_sheer.py

Where ChiffonL is visible at rest over a leg or shoe, the reference pixel is chiffon over leg:
O = a*C + (1-a)*L. Keeping O in the chiffon layer bakes a copy of the leg into the chiffon, and
the copy slides over the real leg in motion (a double calf outline and heel, 2026-09-29). Here L
is the leg layers' own paint behind (at rest), C the local chiffon colour, and the chiffon keeps
colour C with alpha a, so the composite at rest stays O and the leg shows through in motion.
"""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from assemble_v12 import ORDER

HERE = Path(__file__).resolve().parent
LEGS = ["FootL", "ThighL", "ShinL", "FootR", "ThighR", "ShinR"]
SHEER = "ChiffonL"
A_MIN = 0.12
C_TOL = 22.0


def load(n):
    return np.asarray(Image.open(HERE / "layers" / f"{n}.png").convert("RGBA")).astype(np.float32)


def main():
    ch = load(SHEER)
    a = ch[..., 3] > 128
    # what lies directly behind the chiffon at rest, and whether it is a leg
    behind = np.zeros(ch.shape[:2] + (3,), np.float32)
    is_leg = np.zeros(ch.shape[:2], bool)
    for n in ORDER[:ORDER.index(SHEER)]:
        p = HERE / "layers" / f"{n}.png"
        if not p.exists():
            continue
        L = load(n)
        m = L[..., 3] > 128
        behind[m] = L[..., :3][m]
        is_leg[m] = n in LEGS
    region = a & is_leg
    # local chiffon colour: the chiffon where nothing leg-like is behind it, spread by blurring
    pure = a & ~is_leg
    w = cv2.GaussianBlur(pure.astype(np.float32), (0, 0), 25)
    C = np.stack([cv2.GaussianBlur(ch[..., c] * pure, (0, 0), 25) for c in range(3)], -1) / np.maximum(w, 1e-4)[..., None]
    C = np.maximum(C, 200.0)                            # chiffon is light; never let a dark local mean in
    O, L = ch[..., :3], behind
    d = C - L
    alpha = ((O - L) * d).sum(-1) / np.maximum((d * d).sum(-1), 1.0)
    # a smooth sheerness map, then the chiffon colour that reproduces the reference exactly at rest
    wr = cv2.GaussianBlur(region.astype(np.float32), (0, 0), 6)
    alpha = cv2.GaussianBlur(np.where(region, alpha, 0).astype(np.float32), (0, 0), 6) / np.maximum(wr, 1e-4)
    alpha = np.clip(alpha, 0.35, 0.95)
    C0 = C.copy()
    C = np.clip((O - (1 - alpha[..., None]) * L) / alpha[..., None], 0, 255)
    # at the limb's outline the exact solution becomes an extreme colour that shows as a bright or
    # dark strip as soon as the cloth moves (review round 1): keep the chiffon colour near its local
    # mean and let alpha absorb the rest
    # only near the limb outline (elsewhere the exact solution is well behaved)
    edge = np.zeros(is_leg.shape, bool)
    for n in LEGS:
        p = HERE / "layers" / f"{n}.png"
        if p.exists():
            la = (load(n)[..., 3] > 128).astype(np.uint8)
            edge |= (cv2.dilate(la, np.ones((11, 11), np.uint8)) > 0) & ~(cv2.erode(la, np.ones((11, 11), np.uint8)) > 0)
    Cc = np.clip(C, C0 - C_TOL, C0 + C_TOL)
    d = Cc - L
    a2 = np.clip(((O - L) * d).sum(-1) / np.maximum((d * d).sum(-1), 1.0), 0.2, 1.0)
    C = np.where(edge[..., None], Cc, C)
    alpha = np.where(edge, a2, alpha)
    out = ch.copy()
    out[..., :3][region] = C[region]
    out[..., 3][region] = alpha[region] * 255
    Image.fromarray(out.clip(0, 255).astype(np.uint8)).save(HERE / "layers" / f"{SHEER}.png")
    comp = alpha[region, None] * C[region] + (1 - alpha[region, None]) * L[region]
    err = np.abs(comp - O[region]).sum(-1)
    print(f"{SHEER}: unmixed {region.sum()} px over legs, mean alpha {alpha[region].mean():.2f}, rest error median {np.median(err):.1f}")


if __name__ == "__main__":
    main()
