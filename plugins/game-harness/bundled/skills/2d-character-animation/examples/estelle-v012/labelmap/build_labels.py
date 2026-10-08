"""Quantise the Codex part map to the palette -> labels.npy (-1 = background) + review image."""
import json
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
HERE = Path(__file__).resolve().parent
PALETTE = {
    "Head": (255, 0, 0), "HairBack": (255, 140, 0), "FrontLockL": (255, 255, 0), "Neck": (255, 105, 180),
    "Chest": (144, 238, 144), "SleeveL": (0, 100, 0), "SleeveR": (0, 128, 128), "ShawlPanelL": (0, 0, 128),
    "ShawlPanelR": (128, 0, 128), "GloveL": (0, 255, 255), "HandL": (135, 206, 250), "ForearmR": (255, 0, 255),
    "HandR": (139, 69, 19), "Staff": (255, 215, 0), "WaistDrape": (0, 191, 255), "FrontPanel": (0, 0, 255),
    "ChiffonL": (200, 200, 200), "ChiffonR": (120, 120, 120), "WaistCharm": (128, 128, 0),
    "LegR": (250, 128, 114), "LegL": (210, 180, 140), "ShoeR": (20, 20, 20), "ShoeL": (70, 70, 70),
}
NAMES = list(PALETTE)


def build():
    lm = np.asarray(Image.open(HERE / "codex-labelmap.png").convert("RGBA")).astype(int)
    ref = np.asarray(Image.open(HERE.parent / "reference.png").convert("RGBA"))
    A = ref[..., 3] > 128
    pal = np.array(list(PALETTE.values()))
    d = ((lm[..., None, :3] - pal[None, None]) ** 2).sum(-1)
    lab = d.argmin(-1).astype(np.int16)
    close = d.min(-1) < 40 ** 2
    lab[~close] = -1
    # anti-aliased / off-palette pixels inside the character: nearest confident label
    unk = A & (lab < 0)
    if unk.any():
        known = (lab >= 0).astype(np.uint8)
        _, idx = cv2.distanceTransformWithLabels(1 - known, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
        ys, xs = np.nonzero(known)
        m = np.zeros(idx.max() + 1, np.int16); m[idx[ys, xs]] = lab[ys, xs]
        lab[unk] = m[idx[unk]]
    lab[~A] = -1
    # drop specks: components < 40 px take the surrounding majority label
    for i in range(len(NAMES)):
        n, cc, st, _ = cv2.connectedComponentsWithStats((lab == i).astype(np.uint8), connectivity=8)
        for c in range(1, n):
            if st[c, 4] < 40:
                sel = cc == c
                ring = (cv2.dilate(sel.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & ~sel & (lab >= 0)
                if ring.any():
                    lab[sel] = np.bincount(lab[ring]).argmax()
    fix(lab)
    np.save(HERE / "labels.npy", lab)
    return lab


def reassign(lab, sel, exclude):
    """Give pixels in `sel` the nearest label that is not in `exclude`."""
    ok = (lab >= 0) & ~np.isin(lab, exclude) & ~sel
    _, idx = cv2.distanceTransformWithLabels((~ok).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.nonzero(ok)
    m = np.zeros(idx.max() + 1, np.int16); m[idx[ys, xs]] = lab[ys, xs]
    lab[sel] = m[idx[sel]]


def fix(lab):
    I = {n: i for i, n in enumerate(NAMES)}
    ys = np.arange(lab.shape[0])[:, None]; xs = np.arange(lab.shape[1])[None, :]
    # gold leg chains read as orange -> not hair below the hips
    reassign(lab, (lab == I["HairBack"]) & (ys > 860), [I["HairBack"]])
    # the navy halter straps on the chest read as teal -> chest
    lab[(lab == I["SleeveR"]) & (xs < 655)] = I["Chest"]
    # stray islands: keep a label's pieces that are >= 5 % of its largest piece (and >= 300 px);
    # smaller ones take the majority label around them
    for _ in range(2):
        for i in range(len(NAMES)):
            n, cc, st, _ = cv2.connectedComponentsWithStats((lab == i).astype(np.uint8), connectivity=8)
            if n <= 2:
                continue
            big = st[1:, 4].max()
            for c in range(1, n):
                if st[c, 4] < max(300, 0.05 * big):
                    sel = cc == c
                    ring = (cv2.dilate(sel.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & ~sel & (lab >= 0) & (lab != i)
                    if ring.any():
                        lab[sel] = np.bincount(lab[ring]).argmax()


def review(lab):
    ref = np.asarray(Image.open(HERE.parent / "reference.png").convert("RGBA"))
    img = (ref[..., :3] * 0.5).astype(np.uint8)
    rng = np.random.RandomState(7)
    cols = (rng.rand(len(NAMES), 3) * 190 + 65).astype(np.uint8)
    for i in range(len(NAMES)):
        img[lab == i] = (img[lab == i] * 0.35 + cols[i] * 0.65).astype(np.uint8)
    edge = np.zeros(lab.shape, bool)
    edge[:, 1:] |= lab[:, 1:] != lab[:, :-1]; edge[1:] |= lab[1:] != lab[:-1]
    img[edge] = 0
    im = Image.fromarray(img); dr = ImageDraw.Draw(im); f = ImageFont.truetype("arial.ttf", 17)
    stats = {}
    for i, n in enumerate(NAMES):
        ys, xs = np.nonzero(lab == i)
        stats[n] = int(len(xs))
        if len(xs):
            k = len(xs) // 2; o = np.argsort(ys)[k]
            dr.text((int(xs[o]) - 25, int(ys[o])), n, fill=(255, 255, 255), font=f, stroke_width=2, stroke_fill=(0, 0, 0))
    im.save(HERE / "labels-review.png")
    (HERE / "labels.json").write_text(json.dumps({"names": NAMES, "px": stats}, indent=1), encoding="utf-8")
    print(stats)


if __name__ == "__main__":
    review(build())
