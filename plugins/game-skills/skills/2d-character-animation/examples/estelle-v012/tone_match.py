"""Low-frequency tone match of a generated in-place part to the reference, then copy to layers/.

Usage: python tone_match.py SHEET PART [PART ...]     e.g. python tone_match.py v2-S4 ChiffonL FrontLockL

The generated paint keeps its detail; only its broad colour (Gaussian sigma SIGMA) is moved to the
reference over the part's VISIBLE region (labelmap). The correction fades out over FADE px into the
hidden continuation, so hidden paint joins the corrected visible paint. This bakes the reference
look (for example navy showing through the sheer chiffon) into the part at rest.
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
SIGMA, FADE = 9.0, 40.0
LABEL = {}                  # layer name -> label name when they differ


def register(img, ref, vis, tmpl):
    """Codex sometimes paints the content a little off (scaled bust, shifted choker). Similarity-
    register the paint to the reference on the part's visible region, keep it only if the visible
    colour difference drops, then re-cut to the template."""
    sift = cv2.SIFT_create(4000)
    m = (cv2.dilate(vis.astype(np.uint8), np.ones((15, 15), np.uint8)) * 255)
    g1 = cv2.cvtColor(img[..., :3].astype(np.uint8), cv2.COLOR_RGB2GRAY)
    g2 = cv2.cvtColor(ref.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    k1, d1 = sift.detectAndCompute(g1, m); k2, d2 = sift.detectAndCompute(g2, m)
    if d1 is None or d2 is None or len(k1) < 10 or len(k2) < 10:
        return img, "no features"
    good = [a for a, b in (p for p in cv2.BFMatcher().knnMatch(d1, d2, k=2) if len(p) == 2) if a.distance < 0.75 * b.distance]
    if len(good) < 12:
        return img, f"{len(good)} matches"
    M, inl = cv2.estimateAffinePartial2D(np.float32([k1[g.queryIdx].pt for g in good]),
                                         np.float32([k2[g.trainIdx].pt for g in good]), method=cv2.RANSAC,
                                         ransacReprojThreshold=3.0)
    if M is None or inl.sum() < 12:
        return img, "no model"
    s = float(np.hypot(M[0, 0], M[1, 0]))
    if not 0.8 < s < 1.25:
        return img, f"scale {s:.2f} rejected"
    warped = cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    wa = warped[..., 3:4] / 255.0
    merged = img.copy()
    merged[..., :3] = warped[..., :3] * wa + img[..., :3] * (1 - wa)      # original fills where the warp leaves gaps
    merged[..., 3] = np.where(tmpl, 255, 0)
    err = lambda x: np.median(np.abs(ref - x[..., :3]).sum(-1)[vis])
    if err(merged) >= err(img):
        return img, f"no gain (inliers {int(inl.sum())})"
    shift = np.hypot(M[0, 2] + (M[0, 0] - 1) * 512, M[1, 2] + (M[1, 1] - 1) * 768)
    return merged, f"registered: scale {s:.3f}, inliers {int(inl.sum())}, {err(img):.0f}->{err(merged):.0f}"


def match(sheet, part):
    img = np.asarray(Image.open(HERE / "layers_t" / sheet / f"{part}.png").convert("RGBA")).astype(np.float32)
    ref = np.asarray(Image.open(HERE / "reference.png").convert("RGB")).astype(np.float32)
    lab = np.load(HERE / "labelmap" / "labels.npy")
    names = json.loads((HERE / "labelmap" / "labels.json").read_text(encoding="utf-8"))["names"]
    tmpl = np.asarray(Image.open(HERE / "template" / f"{sheet}-{part}.png")) > 128
    vis0 = (lab == names.index(LABEL.get(part, part))) & tmpl
    img, note = register(img, ref, vis0, tmpl)
    print(f"{part:12s} {note}")
    a = img[..., 3] > 128
    vis = (lab == names.index(LABEL.get(part, part))) & a
    vis = cv2.erode(vis.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    w = cv2.GaussianBlur(vis.astype(np.float32), (0, 0), SIGMA)
    diff = np.zeros_like(ref)
    for c in range(3):
        diff[..., c] = cv2.GaussianBlur((ref[..., c] - img[..., c]) * vis, (0, 0), SIGMA) / np.maximum(w, 1e-3)
    dist = cv2.distanceTransform((~vis).astype(np.uint8), cv2.DIST_L2, 5)
    k = np.clip(1 - dist / FADE, 0, 1)[..., None] * (w > 0.02)[..., None]
    out = img.copy()
    out[..., :3] = np.clip(img[..., :3] + diff * k, 0, 255)
    Image.fromarray(out.astype(np.uint8)).save(HERE / "layers" / f"{part}.png")
    before = np.median(np.abs(ref - img[..., :3]).sum(-1)[vis])
    after = np.median(np.abs(ref - out[..., :3]).sum(-1)[vis])
    print(f"{part:12s} visible px {vis.sum():6d}  median |RGB diff| {before:5.1f} -> {after:5.1f}")


if __name__ == "__main__":
    for p in sys.argv[2:]:
        match(sys.argv[1], p)
