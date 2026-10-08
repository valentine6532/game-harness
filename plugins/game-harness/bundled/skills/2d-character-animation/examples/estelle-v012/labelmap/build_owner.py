"""owner.npy: labels.npy with every label boundary's anti-aliased 2 px handed to the part in FRONT.

The reference's edge pixels between two parts mix both colours. If the part behind keeps them, a
thin line of the front part's colour stays on it and shows when the front part moves away (a dark
staff line on the right shawl, 2026-09-29). The front part owns them instead; for the part behind
they count as hidden.
"""
import json, sys
from pathlib import Path
import cv2, numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from assemble_v12 import ORDER, LABEL_OF  # noqa: E402
RING = 2
WIDE_RING = {"Staff"}
SHEER = {"ChiffonL"}
LAB = np.load(HERE / "labels.npy")
NAMES = json.loads((HERE / "labels.json").read_text(encoding="utf-8"))["names"]
rank = {}
for i, n in enumerate(ORDER):
    l = LABEL_OF.get(n, n)
    if l in NAMES:
        rank[l] = max(rank.get(l, -1), i)
owner = LAB.copy()
rk = np.full(len(NAMES) + 1, -1); 
for l, r in rank.items(): rk[NAMES.index(l)] = r
REF = np.asarray(__import__("PIL.Image", fromlist=["Image"]).open(HERE.parent / "reference.png").convert("RGB"))
HSV = cv2.cvtColor(REF, cv2.COLOR_RGB2HSV_FULL).astype(float) / 255
DARK = HSV[..., 2] < 0.55
# 1) legs and shoes seen through the sheer chiffon: warm (skin / gold heel) pixels inside a cloth
#    label that touch a leg or shoe belong to that leg or shoe; the chiffon gets a hole there
#    (otherwise a copy of the heel slid along with the chiffon)
limbs = [NAMES.index(n) for n in ("LegR", "LegL", "ShoeR", "ShoeL")]
cloth = np.isin(owner, [NAMES.index(n) for n in ("ChiffonL", "ChiffonR", "FrontPanel")])
warm = ((HSV[..., 0] < 0.17) | (HSV[..., 0] > 0.95)) & (HSV[..., 1] > 0.16) & (HSV[..., 2] > 0.35)
limb = np.isin(owner, limbs)
cand = cloth & warm & (cv2.distanceTransform((~limb).astype(np.uint8), cv2.DIST_L2, 5) < 22)
n, cc = cv2.connectedComponents(cand.astype(np.uint8), connectivity=8)
touch = np.unique(cc[cand & (cv2.dilate(limb.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)])
take = cand & np.isin(cc, touch[touch > 0])
_, idx = cv2.distanceTransformWithLabels((~limb).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
ys, xs = np.nonzero(limb); m = np.zeros(idx.max() + 1, np.int16); m[idx[ys, xs]] = owner[ys, xs]
owner[take] = m[idx[take]]
print("sheer-covered limb px -> limbs", int(take.sum()))
# 2) edge ring to the front part (2 px; 4 px where the pixel is a dark outline stroke)
for l in sorted(rank, key=rank.get):
    i = NAMES.index(l)
    me = (owner == i).astype(np.uint8)
    grow = cv2.dilate(me, np.ones((2 * RING + 1, 2 * RING + 1), np.uint8)) > 0
    grow |= (cv2.dilate(me, np.ones((9, 9), np.uint8)) > 0) & DARK
    if l in WIDE_RING:                   # thin shiny props: their bright rim is theirs too
        grow |= cv2.dilate(me, np.ones((9, 9), np.uint8)) > 0
    ring = grow & (owner >= 0) & (owner != i) & (rk[owner] < rank[l])
    if l in SHEER:
        # through sheer cloth the limb behind keeps its own outline (it moves with the limb)
        ring &= ~np.isin(owner, limbs)
    owner[ring] = i
# thin chiffon strips visible between the staff and the right shawl panel float as torn wisps when
# the dress moves; they read as the panel's lining, so the panel owns them
g = json.loads((HERE.parent / "guide" / "guide.json").read_text(encoding="utf-8"))["joints"]
(tx, ty), (bx, by) = g["staffTop"], g["staffBottom"]
ys, xs = np.mgrid[0:owner.shape[0], 0:owner.shape[1]]
axis = tx + (bx - tx) * (ys - ty) / (by - ty)
wisp = (owner == NAMES.index("ChiffonR")) & (xs > axis + 6) & (ys < 1370)
owner[wisp] = NAMES.index("ShawlPanelR")
print("chiffon wisps -> ShawlPanelR", int(wisp.sum()))
# the chiffon hem that wraps around the staff foot is cloth, not staff (review round 1: a white
# petal flew with the staff)
wht = (HSV[..., 1] < 0.16) & (HSV[..., 2] > 0.62)
petal = (owner == NAMES.index("Staff")) & wht & (ys > 1330)
petal = cv2.morphologyEx(petal.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
owner[petal] = NAMES.index("ChiffonR")
print("staff-foot chiffon -> ChiffonR", int(petal.sum()))
# specks created by the rules above take the majority label around them
for i in range(len(NAMES)):
    k, cc, st, _ = cv2.connectedComponentsWithStats((owner == i).astype(np.uint8), connectivity=8)
    for c in range(1, k):
        if st[c, 4] < 20:
            sel = cc == c
            ring = (cv2.dilate(sel.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & ~sel & (owner >= 0) & (owner != i)
            if ring.any():
                owner[sel] = np.bincount(owner[ring]).argmax()
np.save(HERE / "owner.npy", owner)
print("reassigned px", int((owner != LAB).sum()))
