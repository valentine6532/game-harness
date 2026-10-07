"""Split in-place limb pieces at the guide joints with an overlap band, merge hidden upper arms.

Usage: python split_limbs.py
Reads layers_fin/LegR, LegL, GloveL, ShoeR, ShoeL, ForearmR (finalize_v2 output) and writes
layers/ThighR, ShinR, ThighL, ShinL, UpperArmL, ForearmL, FootR, FootL, ForearmR.
Each half keeps OV px of the continuous paint past the joint, so the piece in front can fade
over the one behind without any painted end-cap outline. The upper arm above the in-place glove
top (hidden under the sleeve) comes from the proportion-template upper arm (layers_v1_backup).
"""
import json
from pathlib import Path
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
J = json.loads((HERE / "guide" / "guide.json").read_text(encoding="utf-8"))["joints"]
OV = 40.0


def load(p):
    return np.asarray(Image.open(p).convert("RGBA")).copy()


def side(img, joint, toward, keep_toward):
    p = np.array(J[joint], float); d = np.array(J[toward], float) - p; d /= np.linalg.norm(d)
    ys, xs = np.mgrid[0:img.shape[0], 0:img.shape[1]]
    t = (xs - p[0]) * d[0] + (ys - p[1]) * d[1]
    out = img.copy()
    out[(t < -OV) if keep_toward else (t > OV), 3] = 0
    return out


def save(img, name):
    Image.fromarray(img).save(HERE / "layers" / f"{name}.png")
    print(name, int((img[..., 3] > 128).sum()))


F = HERE / "layers_fin"
for s, k, a in (("R", "kneeR", "ankleR"), ("L", "kneeL", "ankleL")):
    leg = load(F / f"Leg{s}.png")
    save(side(leg, k, a, False), f"Thigh{s}")
    save(side(leg, k, a, True), f"Shin{s}")
    save(load(F / f"Shoe{s}.png"), f"Foot{s}")
glove = load(F / "GloveL.png")
upper = side(glove, "elbowL", "shoulderL", True)
t2a = load(HERE / "layers_v1_backup" / "UpperArmL.png")
m = upper[..., 3] < 128                     # proportion-template skin arm only where the glove piece is empty
upper[m] = t2a[m]
save(upper, "UpperArmL")
save(side(glove, "elbowL", "wristL", True), "ForearmL")
save(load(F / "ForearmR.png"), "ForearmR")
