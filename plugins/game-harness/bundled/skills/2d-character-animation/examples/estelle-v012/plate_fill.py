"""Fill what a moving arm and prop reveal from a clean plate of the reference.

Usage: python plate_fill.py plate/plate-a.png

The plate is the reference repainted by the generator with the staff, the staff arm (forearm, fist)
and the shawl on that upper arm removed; everything behind them is painted crisply. LaMa and
row interpolation could only guess there (blurred hair, streaked robe edge, blotches under the
arm: review rounds 1-2).

Removed region R = parts that move away (REMOVED labels, grown 6 px). Each plate pixel in R is
given to the part behind whose local reference colour it matches best (among parts present
within 60 px), then that part's layer takes the plate pixel and becomes opaque there.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from assemble_v12 import ORDER, LABEL_OF

HERE = Path(__file__).resolve().parent
REMOVED = ["Staff", "HandR", "ForearmR", "SleeveR"]
NEVER = ["Head", "LegR", "LegL", "ShoeR", "ShoeL", "HandL", "GloveL", "WaistCharm"]   # not continued from the plate
SIGMA, REACH = 20.0, 60

LAB = np.load(HERE / "labelmap" / "owner.npy")
NAMES = json.loads((HERE / "labelmap" / "labels.json").read_text(encoding="utf-8"))["names"]
REF = np.asarray(Image.open(HERE / "reference.png").convert("RGBA"))


def main(plate_path):
    plate = np.asarray(Image.open(plate_path).convert("RGBA"))
    if plate.shape != REF.shape:
        plate = np.asarray(Image.fromarray(plate).resize((REF.shape[1], REF.shape[0]), Image.LANCZOS))
    rem = np.isin(LAB, [NAMES.index(n) for n in REMOVED])
    R = (cv2.dilate(rem.astype(np.uint8), np.ones((13, 13), np.uint8)) > 0) & (plate[..., 3] > 128)
    ref_lab = cv2.cvtColor(REF[..., :3], cv2.COLOR_RGB2LAB).astype(np.float32)
    pl_lab = cv2.cvtColor(np.ascontiguousarray(plate[..., :3]), cv2.COLOR_RGB2LAB).astype(np.float32)
    cand = [i for i, n in enumerate(NAMES) if n not in REMOVED and n not in NEVER]
    best = np.full(LAB.shape, -1, np.int16)
    bestd = np.full(LAB.shape, np.inf, np.float32)
    for k in cand:
        m = ((LAB == k) & ~R).astype(np.float32)
        if m.sum() < 50:
            continue
        w = cv2.GaussianBlur(m, (0, 0), SIGMA)
        near = cv2.distanceTransform((m == 0).astype(np.uint8), cv2.DIST_L2, 5) <= REACH
        mean = np.stack([cv2.GaussianBlur(ref_lab[..., c] * m, (0, 0), SIGMA) for c in range(3)], -1) / np.maximum(w, 1e-4)[..., None]
        d = np.linalg.norm(pl_lab - mean, axis=-1) + 0.15 * cv2.distanceTransform((m == 0).astype(np.uint8), cv2.DIST_L2, 5)
        upd = R & near & (d < bestd)
        best[upd] = k
        bestd[upd] = d[upd]
    # mode filter inside R so labels form clean regions
    lab = best.copy()
    for _ in range(2):
        votes = np.zeros((len(NAMES),) + LAB.shape, np.float32)
        for k in np.unique(lab[lab >= 0]):
            votes[k] = cv2.blur((lab == k).astype(np.float32), (9, 9))
        v = votes.argmax(0)
        lab = np.where(R & (lab >= 0), v, lab).astype(np.int16)
    np.save(HERE / "plate" / "plate_labels.npy", lab)
    owners = {}
    for n in ORDER:
        owners.setdefault(LABEL_OF.get(n, n), []).append(n)
    for k in np.unique(lab[R & (lab >= 0)]):
        name = NAMES[k]
        for layer in owners.get(name, []):
            p = HERE / "layers" / f"{layer}.png"
            if not p.exists():
                continue
            img = np.asarray(Image.open(p).convert("RGBA")).copy()
            sel = R & (lab == k)
            img[sel, :3] = plate[sel, :3]
            img[sel, 3] = 255
            Image.fromarray(img).save(p)
            print(f"{layer:12s} from plate {int(sel.sum())} px")
            break
    # review image: plate labels in R over the plate
    rng = np.random.RandomState(4)
    cols = (rng.rand(len(NAMES), 3) * 200 + 55).astype(np.uint8)
    vis = plate[..., :3].copy()
    m = R & (lab >= 0)
    vis[m] = (vis[m] * 0.4 + cols[lab[m]] * 0.6).astype(np.uint8)
    Image.fromarray(vis).save(HERE / "plate" / "plate-labels-review.png")


if __name__ == "__main__":
    main(sys.argv[1])
