"""Register a painted template sheet to its template before splitting it into parts.

Usage: python register_sheet.py SHEET
The generator is told to paint inside the grey masks in place, but in v013 several sheets came
back shifted or slightly scaled (coverage 0.49-0.83 at the right place). The painted alpha is
aligned to the template alpha with an ECC affine fit on blurred masks (then the colour-diff of the
visible region is checked by check_inplace.py). The original is kept as gen/P-<SHEET>-raw.png.
"""
import sys, shutil
from pathlib import Path
import cv2, numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
s = sys.argv[1]
raw = HERE / "gen" / f"P-{s}-raw.png"
if not raw.exists():
    shutil.copyfile(HERE / "gen" / f"P-{s}.png", raw)
g = np.asarray(Image.open(raw).convert("RGBA").resize((1024, 1536), Image.LANCZOS))
t = (np.asarray(Image.open(HERE / "template" / f"{s}.png").convert("RGBA"))[..., 3] > 128).astype(np.float32)
a = (g[..., 3] > 128).astype(np.float32)
best = None
for sig in (12, 6, 3):
    tb, ab = cv2.GaussianBlur(t, (0, 0), sig), cv2.GaussianBlur(a, (0, 0), sig)
    M = np.eye(2, 3, dtype=np.float32) if best is None else best
    try:
        _, M = cv2.findTransformECC(tb, ab, M, cv2.MOTION_AFFINE,
                                    (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 300, 1e-6), None, 5)
        best = M
    except cv2.error as e:
        print("ECC failed at sigma", sig, e)
M = best if best is not None else np.eye(2, 3, dtype=np.float32)
out = cv2.warpAffine(g, M, (1024, 1536), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderValue=(0, 0, 0, 0))
iou0 = (a * t).sum() / np.maximum(((a + t) > 0).sum(), 1)
a1 = (out[..., 3] > 128).astype(np.float32)
iou1 = (a1 * t).sum() / np.maximum(((a1 + t) > 0).sum(), 1)
Image.fromarray(out).save(HERE / "gen" / f"P-{s}.png")
print(f"{s}: affine {np.round(M, 3).tolist()}  IoU {iou0:.3f} -> {iou1:.3f}")
