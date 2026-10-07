"""Check an in-place template sheet and write its parts to layers_t/<sheet>/.

Usage: python check_inplace.py SHEET        e.g. python check_inplace.py C3-shawl-drape
Reads gen/P-<SHEET>.png and template/<SHEET>.json.

Per part: coverage (painted share of the mask), grey (template grey left unpainted),
and for the sheet: spill (painted pixels outside every mask, in mask-area %).
Pass: coverage >= 0.97, grey <= 0.02, and (v2) median LAB difference to the reference over the
part's visible region (labelmap) <= 20. The layer is the painted pixels inside the mask
(Codex already masks to the template; the mask only drops stray pixels).
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent


def main(sheet):
    info = json.loads((HERE / "template" / f"{sheet}.json").read_text(encoding="utf-8"))
    im = Image.open(HERE / "gen" / f"P-{sheet}.png").convert("RGBA")
    if im.size != (1024, 1536):
        im = im.resize((1024, 1536), Image.LANCZOS)
    g = np.asarray(im)
    painted = g[:, :, 3] > 128
    rgb = g[:, :, :3].astype(int)
    grey = (np.abs(rgb - 200).max(2) <= 6) & painted
    out = HERE / "layers_t" / sheet
    out.mkdir(parents=True, exist_ok=True)
    union = np.zeros(painted.shape, bool)
    import cv2
    ref = np.asarray(Image.open(HERE / "reference.png").convert("RGB"))
    labp = HERE / "labelmap" / "labels.npy"
    LAB = np.load(labp) if labp.exists() else None
    NAMES = json.loads((HERE / "labelmap" / "labels.json").read_text(encoding="utf-8"))["names"] if LAB is not None else []
    lab_r = cv2.cvtColor(ref, cv2.COLOR_RGB2LAB).astype(float)
    a = g[..., 3:4] / 255.0                      # generated paint over the reference: no black fringe
    over = (g[..., :3] * a + ref * (1 - a)).astype(np.uint8)
    lab_r = cv2.cvtColor(cv2.GaussianBlur(ref, (0, 0), 2), cv2.COLOR_RGB2LAB).astype(float)
    lab_g = cv2.cvtColor(cv2.GaussianBlur(over, (0, 0), 2), cv2.COLOR_RGB2LAB).astype(float)
    dmap = np.linalg.norm(lab_r - lab_g, axis=2)
    rep = {}
    for name, p in info["parts"].items():
        m = np.asarray(Image.open(HERE / "template" / p["mask"])) > 128
        union |= m
        cov = np.count_nonzero(painted & m) / m.sum()
        gr = np.count_nonzero(grey & m) / m.sum()
        colour = None
        if name in NAMES:
            vis = (cv2.erode((LAB == NAMES.index(name)).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & m
            if vis.any():
                colour = float(np.median(dmap[vis]))
        ok = cov >= 0.97 and gr <= 0.02 and (colour is None or colour <= 20)
        layer = g.copy()
        layer[~m] = 0
        Image.fromarray(layer).save(out / f"{name}.png")
        rep[name] = {"pass": bool(ok), "coverage": round(float(cov), 3), "grey": round(float(gr), 3),
                     "visible_colour_diff_median": None if colour is None else round(colour, 1)}
        print(f"{name:12s} {'PASS' if ok else 'fail'} coverage {cov:.3f} grey {gr:.3f} colour-diff(visible) {colour if colour is None else round(colour,1)}")
    spill = np.count_nonzero(painted & ~union) / union.sum()
    rep["_spill"] = round(float(spill), 4)
    print(f"spill outside masks {spill:.4f}")
    (out / "report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
