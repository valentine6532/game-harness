"""Precompute the cloth under the v007 staff-sleeve arm piece with LaMa.

Run with the LaMa environment (see the skill's scripts/lama_fill.py):
  LAMA_MODEL=D:/ai-tools/models/big-lama.pt D:/ai-tools/venv/Scripts/python.exe make_under_v7.py
Writes sleeve-under-lama.png (full reference size, RGB). rig_v7.py uses it when present and
falls back to procedural folds otherwise.
"""
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
import rig_v7 as R          # noqa: E402
from lama_fill import lama_fill  # noqa: E402

st = np.asarray(Image.open(R.STUDY).convert("RGBA"))
a = st[..., 3:4] / 255.0
rgb = (st[..., :3] * a + np.array([9, 11, 24]) * (1 - a)).astype(np.uint8)
M = R.build_masks(Image.open(R.STUDY).convert("RGBA"))
arm_piece = M["sleeve_r"]
# Hide everything that moves away so LaMa cannot rebuild it: arm piece, forearm, hand, staff.
hole = arm_piece | M["staff_fore"] | M["hand"] | (M["staff"] & R.poly_mask([(640, 330), (840, 330), (840, 620), (640, 620)]))
out = lama_fill(rgb, hole, grow=5, margin=140)
Image.fromarray(out).save(R.UNDER_LAMA)
print("wrote sleeve-under-lama.png, hole px", int(hole.sum()))
