"""Measure mesh stretch of a layered rig at one clip frame, without Unity.

  python stretch_check.py <rig.json> <anim.json> <clip_index> <frame> <reference.png> <out.png> [x0 y0 x1 y1]

Linear-blend-skins every skinned layer with the clip pose (FK from rig.json bones) and reports
edges whose length changed by more than 15 %, overall and inside an optional region of
interest (reference px). The map draws stretched edges red and compressed edges blue over the
reference. Use it after posing limbs: cloth or body next to a moving limb must not stretch.
"""
import json
import math
import sys

import numpy as np
from PIL import Image, ImageDraw


def rot(a):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return np.array([[c, -s], [s, c]])


def world_fn(bones, H, ppu):
    pos = {b["name"]: np.array([b["x"], H - b["y"]], float) for b in bones}
    parent = {b["name"]: b["parent"] or None for b in bones}

    def world(pose, name, cache):
        if name in cache:
            return cache[name]
        par = parent[name]
        off = np.array([pose.get((name, "posX"), 0.0), pose.get((name, "posY"), 0.0)]) * ppu
        if par is None:
            res = (pos[name] + off, pose.get((name, "rot"), 0.0))
        else:
            pp, pa = world(pose, par, cache)
            res = (pp + rot(pa) @ (pos[name] - pos[par] + off), pa + pose.get((name, "rot"), 0.0))
        cache[name] = res
        return res
    return world


def measure(rig, anim, clip_index, frame, H, roi=None, tol=0.15):
    world = world_fn(rig["bones"], H, rig["refPpu"])
    clip = anim["clips"][clip_index]
    pose = {(c["bone"], c["prop"]): c["values"][frame] for c in clip["channels"] if c["prop"] in ("rot", "posX", "posY")}
    rest = {b["name"]: world({}, b["name"], {}) for b in rig["bones"]}
    cache = {}
    cur = {b["name"]: world(pose, b["name"], cache) for b in rig["bones"]}
    report, lines = {}, []
    for p in rig["parts"]:
        if "vertices" not in p:
            continue
        ox, oy, h = p["originX"], p["originY"], p["height"]
        names = [b["name"] for b in p["bones"]]
        V = np.array(p["vertices"]).reshape(-1, 2)
        Wt = np.array(p["weights"]).reshape(-1, 4, 2)
        ref = np.stack([V[:, 0] + ox, (oy + h) - V[:, 1]], 1)
        up = np.stack([ref[:, 0], H - ref[:, 1]], 1)
        out = np.zeros_like(up)
        for k in range(len(V)):
            for j in range(4):
                bn, w = names[int(Wt[k, j, 0])], Wt[k, j, 1]
                if w > 0:
                    P0, a0 = rest[bn]
                    P1, a1 = cur[bn]
                    out[k] += w * (P1 + rot(a1 - a0) @ (up[k] - P0))
        edges = set()
        for t in np.array(p["indices"]).reshape(-1, 3):
            for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                edges.add((min(a, b), max(a, b)))
        bad = bad_roi = worst = 0
        for a, b in edges:
            r = np.linalg.norm(out[a] - out[b]) / max(np.linalg.norm(up[a] - up[b]), 1e-6)
            if abs(r - 1) > tol:
                bad += 1
                mid = (ref[a] + ref[b]) / 2
                inside = roi is None or (roi[0] <= mid[0] <= roi[2] and roi[1] <= mid[1] <= roi[3])
                if inside:
                    bad_roi += 1
                    worst = max(worst, abs(r - 1))
                lines.append((tuple(ref[a]), tuple(ref[b]), r))
        report[p["name"]] = dict(edges=len(edges), off=bad, off_in_roi=bad_roi, worst_in_roi=round(float(worst), 2))
    return report, lines


if __name__ == "__main__":
    a = sys.argv[1:]
    rig, anim = json.load(open(a[0])), json.load(open(a[1]))
    ref = Image.open(a[4]).convert("RGBA")
    roi = tuple(map(float, a[6:10])) if len(a) >= 10 else None
    report, lines = measure(rig, anim, int(a[2]), int(a[3]), ref.height, roi)
    base = Image.new("RGBA", ref.size, (20, 20, 30, 255))
    base.alpha_composite(ref)
    img = Image.blend(Image.new("RGB", ref.size, (20, 20, 30)), base.convert("RGB"), 0.35)
    d = ImageDraw.Draw(img, "RGBA")
    for p0, p1, r in lines:
        d.line([p0, p1], fill=(255, 40, 40, 220) if r > 1 else (60, 140, 255, 220), width=3)
    if roi:
        d.rectangle(roi, outline=(255, 255, 0, 255), width=2)
    img.save(a[5])
    print(json.dumps(report, indent=1))
