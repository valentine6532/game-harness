"""Render the layered rig at any clip frame without Unity (linear blend skinning, textured).

  python pose_render.py <clip_index> <frame|time_s> <out.png> [x0 y0 x1 y1] [--scale s] [--bg r,g,b]
  python pose_render.py sheet <clip_index> <out.png> <frames comma list> [x0 y0 x1 y1]

Uses the same rig.json / anim.json as Unity. Each skinned layer is drawn triangle by triangle
(piecewise affine), rigid layers follow their anchor bone. Good for fast visual review and
before/after comparisons; the final evidence still comes from Unity renders.
"""
import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
H_REF = 1536


def rot(a):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return np.array([[c, -s], [s, c]])


class Rig:
    def __init__(self, rig_path=os.path.join(HERE, "rig.json"), anim_path=os.path.join(HERE, "anim.json"),
                 parts_dir=os.path.join(HERE, "parts")):
        self.rig = json.load(open(rig_path))
        self.anim = json.load(open(anim_path))
        self.ppu = self.rig["refPpu"]
        self.pos = {b["name"]: np.array([b["x"], H_REF - b["y"]], float) for b in self.rig["bones"]}
        self.parent = {b["name"]: b["parent"] or None for b in self.rig["bones"]}
        self.img = {p["name"]: np.asarray(Image.open(os.path.join(parts_dir, p["file"])).convert("RGBA"))
                    for p in self.rig["parts"]}
        self.parts = sorted(self.rig["parts"], key=lambda p: p["order"])

    def pose(self, clip_index, t):
        clip = self.anim["clips"][clip_index]
        out = {}
        for c in clip["channels"]:
            out[(c["bone"], c["prop"])] = float(np.interp(t, c["times"], c["values"]))
        return out

    def world(self, pose, name, cache):
        if name in cache:
            return cache[name]
        par = self.parent[name]
        off = np.array([pose.get((name, "posX"), 0.0), pose.get((name, "posY"), 0.0)]) * self.ppu
        if par is None:
            res = (self.pos[name] + off, pose.get((name, "rot"), 0.0))
        else:
            pp, pa = self.world(pose, par, cache)
            res = (pp + rot(pa) @ (self.pos[name] - self.pos[par] + off), pa + pose.get((name, "rot"), 0.0))
        cache[name] = res
        return res

    def transforms(self, pose):
        rest, cur, c0, c1 = {}, {}, {}, {}
        for n in self.pos:
            rest[n] = self.world({}, n, c0)
            cur[n] = self.world(pose, n, c1)
        return rest, cur

    def deform(self, part, rest, cur):
        """Deformed vertex positions in reference px (y down) and source px in the part image."""
        ox, oy, h = part["originX"], part["originY"], part["height"]
        names = [b["name"] for b in part["bones"]]
        V = np.array(part["vertices"], float).reshape(-1, 2)
        Wt = np.array(part["weights"], float).reshape(-1, 4, 2)
        src = np.stack([V[:, 0], h - V[:, 1]], 1)                  # part image px, y down
        up = np.stack([V[:, 0] + ox, H_REF - ((oy + h) - V[:, 1])], 1)   # ref px, y up
        out = np.zeros_like(up)
        for j in range(4):
            idx = Wt[:, j, 0].astype(int)
            w = Wt[:, j, 1]
            for bi in np.unique(idx):
                sel = (idx == bi) & (w > 0)
                if not sel.any():
                    continue
                P0, a0 = rest[names[bi]]
                P1, a1 = cur[names[bi]]
                out[sel] += w[sel, None] * (P1 + (up[sel] - P0) @ rot(a1 - a0).T)
        dst = np.stack([out[:, 0], H_REF - out[:, 1]], 1)
        return src, dst


def draw_triangles(canvas, img, src, dst, tris, scale, offset, alpha=1.0):
    """Piecewise-affine paste of `img` (RGBA) into premultiplied float `canvas` (over)."""
    Hc, Wc = canvas.shape[:2]
    layer = np.zeros((Hc, Wc, 4), np.float32)
    rgba = img.astype(np.float32) / 255.0
    rgba[..., :3] *= rgba[..., 3:4]
    for t in tris:
        s = src[t].astype(np.float32)
        d = ((dst[t] - offset) * scale).astype(np.float32)
        x0, y0 = np.floor(d.min(0)).astype(int) - 2
        x1, y1 = np.ceil(d.max(0)).astype(int) + 2
        if x1 < 0 or y1 < 0 or x0 >= Wc or y0 >= Hc:
            continue
        x0c, y0c, x1c, y1c = max(x0, 0), max(y0, 0), min(x1, Wc), min(y1, Hc)
        if x1c <= x0c or y1c <= y0c:
            continue
        M = cv2.getAffineTransform(s, d - np.array([x0c, y0c], np.float32))
        patch = cv2.warpAffine(rgba, M, (x1c - x0c, y1c - y0c), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        mask = np.zeros((y1c - y0c, x1c - x0c), np.uint8)
        cen = d.mean(0)
        grow = d + (d - cen) / np.maximum(np.linalg.norm(d - cen, axis=1, keepdims=True), 1e-6) * 0.7
        cv2.fillConvexPoly(mask, np.round((grow - [x0c, y0c]) * 4).astype(np.int32), 1, lineType=cv2.LINE_8, shift=2)
        m = mask.astype(bool)
        region = layer[y0c:y1c, x0c:x1c]
        region[m] = patch[m]
    layer *= alpha
    a = layer[..., 3:4]
    canvas[:] = layer + canvas * (1 - a)


def render(r, clip_index, t, box=(0, 0, 1024, 1536), scale=0.5, bg=(20, 22, 36), flash=True):
    pose = r.pose(clip_index, t) if clip_index is not None else {}
    rest, cur = r.transforms(pose)
    x0, y0, x1, y1 = box
    Wc, Hc = int(round((x1 - x0) * scale)), int(round((y1 - y0) * scale))
    canvas = np.zeros((Hc, Wc, 4), np.float32)
    canvas[..., :3] = np.array(bg, np.float32) / 255.0
    canvas[..., 3] = 1.0
    offset = np.array([x0, y0], float)
    for p in r.parts:
        img = r.img[p["name"]]
        if "vertices" in p:
            src, dst = r.deform(p, rest, cur)
            tris = np.array(p["indices"]).reshape(-1, 3)
        else:
            bn = p["anchor"]
            P0, a0 = rest[bn]
            P1, a1 = cur[bn]
            hh, ww = img.shape[:2]
            src = np.array([[0, 0], [ww, 0], [ww, hh], [0, hh]], float)
            up = np.stack([src[:, 0] + p["originX"], H_REF - (src[:, 1] + p["originY"])], 1)
            moved = P1 + (up - P0) @ rot(a1 - a0).T
            dst = np.stack([moved[:, 0], H_REF - moved[:, 1]], 1)
            tris = np.array([[0, 1, 2], [0, 2, 3]])
        # sprite swaps: a part flagged "hidden" shows only while its "alpha" channel is keyed up; any
        # other part can be keyed out with "hide" (Estelle v014 extended strike arm)
        alpha = pose.get((p["name"], "alpha"), 0.0 if p.get("hidden") else 1.0)
        alpha *= 1.0 - pose.get((p["name"], "hide"), 0.0)
        if alpha <= 0.001:
            continue
        draw_triangles(canvas, img, src, dst, tris, scale, offset, alpha)
    if flash and clip_index is not None:
        a = pose.get(("CastFlash", "alpha"), 0.0)
        s = pose.get(("CastFlash", "scale"), 0.0)
        if a > 0.01 and s > 0.01:
            tip, _ = cur["StaffTip"]
            cx, cy = (tip[0] - x0) * scale, ((H_REF - tip[1]) - y0) * scale
            rad = 0.72 * 256 / 2 * s * scale
            yy, xx = np.mgrid[0:Hc, 0:Wc]
            g = np.clip(1 - np.hypot(xx - cx, yy - cy) / rad, 0, 1) ** 2 * a
            glow = np.array([1.0, 0.92, 0.65], np.float32)
            canvas[..., :3] = canvas[..., :3] * (1 - g[..., None]) + glow * g[..., None]
    out = np.clip(canvas[..., :3] * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGB")


def parse_time(r, clip_index, s):
    return float(s[:-1]) if s.endswith("s") else int(s) / 30.0


if __name__ == "__main__":
    a = sys.argv[1:]
    r = Rig()
    if a[0] == "sheet":
        ci, out, frames = int(a[1]), a[2], a[3].split(",")
        box = tuple(map(float, a[4:8])) if len(a) >= 8 else (0, 0, 1024, 1536)
        tiles = [render(r, ci, parse_time(r, ci, f), box, 0.5 if len(a) < 8 else 1.0) for f in frames]
        w, h = tiles[0].size
        sheet = Image.new("RGB", (w * len(tiles), h + 24), (10, 10, 18))
        d = ImageDraw.Draw(sheet)
        for i, (f, tile) in enumerate(zip(frames, tiles)):
            sheet.paste(tile, (i * w, 24))
            d.text((i * w + 6, 5), f, fill=(255, 230, 120))
        sheet.save(out)
    else:
        ci = None if a[0] == "rest" else int(a[0])
        t = 0.0 if ci is None else parse_time(r, ci, a[1])
        box = tuple(map(float, a[3:7])) if len(a) >= 7 else (0, 0, 1024, 1536)
        scale = 1.0 if len(a) >= 7 else 0.5
        render(r, ci, t, box, scale).save(a[2])
