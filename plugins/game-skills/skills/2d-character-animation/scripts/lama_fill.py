"""Optional LaMa (big-lama) inpainting for large cloth/hair refills.

Use only where the A/B test showed a gain: cloth folds, trims and patterns, hair strands, a
strip where a prop crossed cloth. Keep structured fills (rig_layers.mirror_extend_rows,
procedural_folds) where anatomy or garment construction must continue (bust, corset side).

Setup (once per machine, outside the project; about 4.4 GB). Needs an NVIDIA GPU (tested: RTX 2060
6 GB, 0.3 GB used). It also runs on CPU, slowly.
  uv venv --python 3.13 <tools>/venv
  uv pip install --python <tools>/venv/Scripts/python.exe torch torchvision --index-url https://download.pytorch.org/whl/cu126
  uv pip install --python <tools>/venv/Scripts/python.exe --no-deps simple-lama-inpainting
  uv pip install --python <tools>/venv/Scripts/python.exe fire pillow numpy opencv-python
  curl -L -o <tools>/models/big-lama.pt https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt
simple-lama-inpainting pins pillow 9.5, which does not build on new Pythons; hence --no-deps.

Run with that venv's python:
  LAMA_MODEL=<tools>/models/big-lama.pt <venv python> lama_fill.py <image.png> <hole_mask.png> <out.png> [grow_px]

Rules (from the Estelle A/B, references/layered-illustration-rig.md section 4):
- Grow the hole 4-6 px past the removed object. LaMa rebuilds whatever outline is left and
  repainted the staff from its anti-aliased edge.
- Keep every fragment of the removed object out of the context near the hole. It painted a
  gold pommel piece back onto a hem that had touched the staff tip.
- Paste only the hole pixels back and keep the base layer's coverage (alpha).
- Review the render at the frame where the fill is most exposed.
"""
import os
import sys

import cv2
import numpy as np
from PIL import Image

_MODEL = None


def model():
    global _MODEL
    if _MODEL is None:
        from simple_lama_inpainting import SimpleLama   # imported lazily: optional dependency
        _MODEL = SimpleLama()
    return _MODEL


def lama_fill(rgb, hole, grow=5, margin=128, keep=None):
    """Inpaint `hole` (bool H x W) in `rgb` (H x W x 3 uint8). The hole is grown by `grow` px
    (clipped to `keep`, e.g. the base layer's coverage). LaMa runs on a crop around the hole.
    Returns a new RGB array; only hole pixels change."""
    if grow > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1))
        hole = cv2.dilate(hole.astype(np.uint8), k) > 0
    if keep is not None:
        hole &= keep
    if not hole.any():
        return rgb.copy()
    ys, xs = np.nonzero(hole)
    H, W = hole.shape
    y0, y1 = max(ys.min() - margin, 0), min(ys.max() + margin, H)
    x0, x1 = max(xs.min() - margin, 0), min(xs.max() + margin, W)
    img = Image.fromarray(np.ascontiguousarray(rgb[y0:y1, x0:x1]))
    m = Image.fromarray((hole[y0:y1, x0:x1] * 255).astype(np.uint8))
    out = np.asarray(model()(img, m))[: y1 - y0, : x1 - x0]
    res = rgb.copy()
    sub = hole[y0:y1, x0:x1]
    res[y0:y1, x0:x1][sub] = out[sub]
    return res


def available():
    try:
        import simple_lama_inpainting  # noqa: F401
        return True
    except ImportError:
        return False


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    rgba = np.asarray(Image.open(sys.argv[1]).convert("RGBA"))
    hole = np.asarray(Image.open(sys.argv[2]).convert("L")) > 127
    grow = int(sys.argv[4]) if len(sys.argv) > 4 else 5
    rgb = lama_fill(rgba[..., :3], hole, grow, keep=rgba[..., 3] > 0)
    Image.fromarray(np.dstack([rgb, rgba[..., 3]]), "RGBA").save(sys.argv[3])
    print("wrote", sys.argv[3])
