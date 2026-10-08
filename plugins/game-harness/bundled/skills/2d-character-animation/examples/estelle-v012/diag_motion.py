"""Motion diagnosis: where does a posed frame show paint that was hidden at rest (generated), and
from which layer?

Usage: python diag_motion.py CLIP FRAMES OUT [x0 y0 x1 y1]
  e.g. python diag_motion.py 1 0,9,14,20 check/motion/diag-lower.png 250 650 850 1520

Per frame: top = the render, bottom = the render with generated (hidden-at-rest) pixels tinted by
layer, largest regions labelled. Reference pixels stay untinted.
"""
import json
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import pose_render as pr

LAB = np.load("labelmap/labels.npy")
NAMES = json.load(open("labelmap/labels.json"))["names"]
from assemble_v12 import LABEL_OF  # noqa: E402


def part_vis(part_name, p):
    """Visible-at-rest mask of a rig part, in the part image's own pixel frame."""
    base = part_name[:-3] if part_name.endswith("Art") else part_name
    lab = LABEL_OF.get(base, base)
    full = LAB == NAMES.index(lab) if lab in NAMES else np.zeros(LAB.shape, bool)
    ox, oy, w, h = p["originX"], p["originY"], p["width"], p["height"]
    return full[oy:oy + h, ox:ox + w]


def frame(r, clip, t, box):
    pose = r.pose(clip, t)
    rest, cur = r.transforms(pose)
    x0, y0, x1, y1 = box
    Wc, Hc = int(x1 - x0), int(y1 - y0)
    canvas = np.zeros((Hc, Wc, 4), np.float32); canvas[..., :3] = np.array([20, 22, 36]) / 255; canvas[..., 3] = 1
    owner = np.full((Hc, Wc), -1, np.int32)
    hidden = np.zeros((Hc, Wc), bool)
    off = np.array([x0, y0], float)
    for i, p in enumerate(r.parts):
        img = r.img[p["name"]]
        vis = part_vis(p["name"], p)
        flag = np.zeros_like(img)
        flag[..., 3] = img[..., 3]
        flag[..., 0] = np.where(vis, 0, 255)
        if "vertices" in p:
            src, dst = r.deform(p, rest, cur)
            tris = np.array(p["indices"]).reshape(-1, 3)
        else:
            P0, a0 = rest[p["anchor"]]; P1, a1 = cur[p["anchor"]]
            hh, ww = img.shape[:2]
            src = np.array([[0, 0], [ww, 0], [ww, hh], [0, hh]], float)
            up = np.stack([src[:, 0] + p["originX"], pr.H_REF - (src[:, 1] + p["originY"])], 1)
            mv = P1 + (up - P0) @ pr.rot(a1 - a0).T
            dst = np.stack([mv[:, 0], pr.H_REF - mv[:, 1]], 1)
            tris = np.array([[0, 1, 2], [0, 2, 3]])
        pr.draw_triangles(canvas, img, src, dst, tris, 1.0, off)
        fl = np.zeros((Hc, Wc, 4), np.float32)
        pr.draw_triangles(fl, flag, src, dst, tris, 1.0, off)
        top = fl[..., 3] > 0.5
        owner[top] = i
        hidden[top] = fl[..., 0][top] / np.maximum(fl[..., 3][top], 1e-6) > 0.5
    rgb = np.clip(canvas[..., :3] * 255, 0, 255).astype(np.uint8)
    return rgb, owner, hidden


def main():
    clip, frames, out = int(sys.argv[1]), sys.argv[2].split(","), sys.argv[3]
    box = tuple(map(float, sys.argv[4:8])) if len(sys.argv) >= 8 else (0, 0, 1024, 1536)
    r = pr.Rig()
    f = ImageFont.truetype("arial.ttf", 13)
    rng = np.random.RandomState(1)
    cols = (rng.rand(len(r.parts), 3) * 200 + 55).astype(np.uint8)
    tiles = []
    for fr in frames:
        rgb, owner, hidden = frame(r, clip, int(fr) / 30.0, box)
        tint = rgb.copy()
        m = hidden & (owner >= 0)
        tint[m] = (rgb[m] * 0.35 + cols[owner[m]] * 0.65).astype(np.uint8)
        # interior gaps (no layer, enclosed): magenta
        n_, lab_, st_, _ = cv2.connectedComponentsWithStats((owner < 0).astype(np.uint8), connectivity=4)
        H_, W_ = owner.shape
        for c in range(1, n_):
            x, y, w, h, ar = st_[c]
            if x > 0 and y > 0 and x + w < W_ and y + h < H_ and ar < 400:
                tint[lab_ == c] = (255, 0, 255)
        im = Image.fromarray(tint); d = ImageDraw.Draw(im)
        for i in np.unique(owner[m]):
            reg = m & (owner == i)
            n, lab, st, cen = cv2.connectedComponentsWithStats(reg.astype(np.uint8))
            for c in range(1, n):
                if st[c, 4] > 150:
                    d.text((int(cen[c][0]) - 20, int(cen[c][1])), r.parts[i]["name"], fill=(255, 255, 255), font=f,
                           stroke_width=2, stroke_fill=(0, 0, 0))
        col = Image.new("RGB", (rgb.shape[1], rgb.shape[0] * 2 + 20), (10, 10, 18))
        col.paste(Image.fromarray(rgb), (0, 20)); col.paste(im, (0, rgb.shape[0] + 20))
        ImageDraw.Draw(col).text((4, 3), f"frame {fr}", fill=(255, 230, 120), font=f)
        tiles.append(col)
    w, h = tiles[0].size
    sheet = Image.new("RGB", (w * len(tiles), h))
    for i, t in enumerate(tiles):
        sheet.paste(t, (i * w, 0))
    sheet.save(out)


if __name__ == "__main__":
    main()
