"""Check a template-filled sheet against its template and place the parts on the guide.

Usage: python check_template.py SHEET [TEMPLATE]     e.g. python check_template.py T1a-limbs limbs

Per part (the component that overlaps the template shape most):
  iou        overlap of the painted part with its grey silhouette
  length     painted extent along the axis / template extent
  width      painted width / template width at 25, 50, 75 % between the joints
Pass: iou >= 0.85, length within 8 %, every width within 12 %.
Passing and failing parts are both placed with the template joints -> guide joints
(uniform scale 1/S + rotation) into layers_t/<SHEET>/<Name>.png for review.
"""

import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
W, H = 1024, 1536


def main(sheet, template="limbs"):
    tinfo = json.loads((HERE / "template" / f"{template}.json").read_text(encoding="utf-8"))
    tmpl = np.asarray(Image.open(HERE / "template" / f"{template}.png"))[:, :, 3] > 128
    G = json.loads((HERE / "guide" / "guide.json").read_text(encoding="utf-8"))
    im = Image.open(HERE / "gen" / f"{sheet}.png").convert("RGBA")
    if im.size != (W, H):
        print(f"sheet is {im.size}, resized to {W}x{H}")
        im = im.resize((W, H), Image.LANCZOS)
    rgba = np.asarray(im).copy()
    alpha = rgba[:, :, 3] > 128
    if alpha.mean() > 0.8:
        raise SystemExit("no transparent background")
    n, lab = cv2.connectedComponents(alpha.astype(np.uint8), connectivity=8)
    tn, tlab = cv2.connectedComponents(tmpl.astype(np.uint8), connectivity=8)
    out_dir = HERE / "layers_t" / sheet
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {}
    for name, p in tinfo["parts"].items():
        x0, y0, x1, y1 = p["bbox"]
        shape = np.zeros_like(tmpl)
        shape[y0:y1 + 1, x0:x1 + 1] = tmpl[y0:y1 + 1, x0:x1 + 1]
        ids, counts = np.unique(lab[shape & alpha], return_counts=True)
        if len(ids) == 0:
            report[name] = {"pass": False, "reason": "nothing painted"}
            continue
        part = lab == ids[np.argmax(counts)]
        iou = np.count_nonzero(part & shape) / np.count_nonzero(part | shape)
        (jx, jy0), (_, jy1) = p["joint_from"], p["joint_to"]
        L = jy1 - jy0

        def width(mask, y):
            xs = np.nonzero(mask[int(round(y))])[0]
            return int(xs.max() - xs.min() + 1) if len(xs) else 0

        ws = [width(part, jy0 + t * L) for t in (0.25, 0.5, 0.75)]
        wt = [width(shape, jy0 + t * L) for t in (0.25, 0.5, 0.75)]
        ys = np.nonzero(part.any(1))[0]
        yt = np.nonzero(shape.any(1))[0]
        length = (ys.max() - ys.min()) / (yt.max() - yt.min())
        wr = [round(a / b, 3) if b else 0 for a, b in zip(ws, wt)]
        ok = iou >= 0.85 and abs(length - 1) <= 0.08 and all(abs(r - 1) <= 0.12 for r in wr)
        report[name] = {"pass": bool(ok), "iou": round(float(iou), 3), "length": round(float(length), 3),
                        "width_ratio": wr, "width_px_sheet": ws}

        # place: template joints -> guide joints
        b = G["bones"][p["bone"]]
        src = np.float64([p["joint_from"], p["joint_to"]])
        dst = np.float64([G["joints"][b["from"]], G["joints"][b["to"]]])
        v, w = src[1] - src[0], dst[1] - dst[0]
        s = np.linalg.norm(w) / np.linalg.norm(v)
        r = math.atan2(w[1], w[0]) - math.atan2(v[1], v[0])
        R = np.array([[math.cos(r), -math.sin(r)], [math.sin(r), math.cos(r)]]) * s
        M = np.hstack([R, (dst[0] - R @ src[0])[:, None]])
        layer = rgba.copy()
        layer[~part] = 0
        placed = cv2.warpAffine(layer, M, (W, H), flags=cv2.INTER_AREA,
                                borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
        Image.fromarray(placed).save(out_dir / f"{name}.png")
        print(f"{name:10s} {'PASS' if ok else 'fail'} iou {iou:.3f} length {length:.3f} width {wr}")
    (out_dir / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


if __name__ == "__main__":
    main(*sys.argv[1:])
