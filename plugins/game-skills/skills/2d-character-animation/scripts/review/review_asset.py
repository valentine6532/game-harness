"""Independent review of a layered 2D rig against its reference illustration.

Usage: python review_asset.py review.json [--out DIR]

Writes DIR (default <rig dir>/review/):
  regions/<nn>-<name>.png   one sheet per region: reference | rest | every review frame, same crop
  hotspots/<k>.png          zooms on every automatic finding (hidden paint shown, holes, islands)
  findings.json             automatic findings + the list of sheets that MUST be looked at
  README.md                 summary for the reviewer to complete

Regions are derived from the part map (one per label bbox, large ones tiled), plus any extra
regions in the config, so no body area can be skipped by leaving it out of a list.

Automatic checks (they only point; the visual review decides):
  rest_colour     LAB difference of the rest composite vs the reference, per region
  hidden_exposed  pixels that were hidden at rest and show in a frame, per layer cluster
  holes           enclosed transparent gaps inside the figure in a frame
  islands         opaque pieces in a frame that are not connected to the figure
  join_pop        frame difference at clip joins vs an ordinary frame step (Unity frames)

Config keys (paths relative to the config file):
  reference, labels (owner or label map .npy), label_names (json with "names"), label_of {layer: label}
  rig, anim, parts (pose_render inputs), frames [[clip_index, frame], ...], fps
  unity (optional): {"frames": {"name": path}, "joins": [[a_last, b_first, a_first, a_second]],
                     "camera": {"screen_w", "screen_h", "ortho_size", "cam_x", "cam_y", "rig_x",
                                "ref_ppu", "origin_x", "ground_y"}}
  extra_regions {name: [x0, y0, x1, y1]}, tile (max region side, default 420)
"""
import argparse
import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pose_render as pr  # noqa: E402

BG = (20, 22, 36)


def font(size):
    for f in ("malgun.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default()


# --------------------------------------------------------------------------- inputs
class Ctx:
    def __init__(self, cfg_path):
        self.base = Path(cfg_path).resolve().parent
        self.cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
        p = lambda k: str(self.base / self.cfg[k])
        self.ref = np.asarray(Image.open(p("reference")).convert("RGBA"))
        self.H, self.W = self.ref.shape[:2]
        pr.H_REF = self.H
        self.lab = np.load(p("labels"))
        self.names = json.loads(Path(p("label_names")).read_text(encoding="utf-8"))["names"]
        self.label_of = self.cfg.get("label_of", {})
        self.rig = pr.Rig(p("rig"), p("anim"), p("parts"))
        self.fps = self.cfg.get("fps", 30)
        self.A = self.ref[..., 3] > 128

    def vis_mask(self, part):
        base = part[:-3] if part.endswith("Art") else part
        l = self.label_of.get(base, base)
        return self.lab == self.names.index(l) if l in self.names else np.zeros(self.lab.shape, bool)


# --------------------------------------------------------------------------- python frames
def frame(ctx, clip, t):
    """Render one frame at reference scale; per pixel: top layer index, hidden-at-rest flag."""
    r = ctx.rig
    pose = r.pose(clip, t) if clip is not None else {}
    rest, cur = r.transforms(pose)
    canvas = np.zeros((ctx.H, ctx.W, 4), np.float32)
    canvas[..., :3] = np.array(BG) / 255
    canvas[..., 3] = 1
    owner = np.full((ctx.H, ctx.W), -1, np.int32)
    hidden = np.zeros((ctx.H, ctx.W), bool)
    for i, p in enumerate(r.parts):
        img = r.img[p["name"]]
        # sprite swaps (pose_render): "hidden" parts show only while keyed up, "hide" keys others out
        alpha = pose.get((p["name"], "alpha"), 0.0 if p.get("hidden") else 1.0) * (1.0 - pose.get((p["name"], "hide"), 0.0))
        if alpha <= 0.001:
            continue
        ox, oy, w, h = p["originX"], p["originY"], p["width"], p["height"]
        vis = ctx.vis_mask(p["name"])[oy:oy + h, ox:ox + w]
        flag = np.zeros_like(img)
        flag[..., 3] = img[..., 3]
        flag[..., 0] = np.where(vis, 0, 255)
        if "vertices" in p:
            src, dst = r.deform(p, rest, cur)
            tris = np.array(p["indices"]).reshape(-1, 3)
        else:
            P0, a0 = rest[p["anchor"]]
            P1, a1 = cur[p["anchor"]]
            src = np.array([[0, 0], [w, 0], [w, h], [0, h]], float)
            up = np.stack([src[:, 0] + ox, ctx.H - (src[:, 1] + oy)], 1)
            mv = P1 + (up - P0) @ pr.rot(a1 - a0).T
            dst = np.stack([mv[:, 0], ctx.H - mv[:, 1]], 1)
            tris = np.array([[0, 1, 2], [0, 2, 3]])
        pr.draw_triangles(canvas, img, src, dst, tris, 1.0, np.zeros(2), alpha)
        fl = np.zeros((ctx.H, ctx.W, 4), np.float32)
        pr.draw_triangles(fl, flag, src, dst, tris, 1.0, np.zeros(2))
        top = fl[..., 3] > 0.5
        owner[top] = i
        hidden[top] = fl[..., 0][top] / np.maximum(fl[..., 3][top], 1e-6) > 0.5
    rgb = np.clip(canvas[..., :3] * 255, 0, 255).astype(np.uint8)
    return rgb, owner, hidden


def interior_holes(owner, max_area=2500, min_area=12):
    n, lab, st, cen = cv2.connectedComponentsWithStats((owner < 0).astype(np.uint8), connectivity=4)
    H, W = owner.shape
    out = []
    for c in range(1, n):
        x, y, w, h, a = st[c]
        if x > 0 and y > 0 and x + w < W and y + h < H and min_area <= a <= max_area:
            out.append({"bbox": [int(x), int(y), int(x + w), int(y + h)], "px": int(a)})
    return out


def islands(owner, min_area=15):
    fig = (owner >= 0).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(fig, connectivity=8)
    if n <= 2:
        return []
    main = 1 + int(np.argmax(st[1:, 4]))
    return [{"bbox": [int(st[c, 0]), int(st[c, 1]), int(st[c, 0] + st[c, 2]), int(st[c, 1] + st[c, 3])], "px": int(st[c, 4])}
            for c in range(1, n) if c != main and st[c, 4] >= min_area]


def hidden_clusters(owner, hidden, parts, min_area=150):
    out = []
    for i in np.unique(owner[hidden & (owner >= 0)]):
        m = (hidden & (owner == i)).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        for c in range(1, n):
            if st[c, 4] >= min_area:
                out.append({"layer": parts[i]["name"], "px": int(st[c, 4]),
                            "bbox": [int(st[c, 0]), int(st[c, 1]), int(st[c, 0] + st[c, 2]), int(st[c, 1] + st[c, 3])]})
    return out


HIDDEN_MIN = 400


def merge_boxes(items, min_px, gap=30):
    """Merge nearby clusters (any layer) into one area; keep areas >= min_px."""
    boxes = [dict(b) for b in items]
    changed = True
    while changed:
        changed = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i]["bbox"], boxes[j]["bbox"]
                if a[0] - gap <= b[2] and b[0] - gap <= a[2] and a[1] - gap <= b[3] and b[1] - gap <= a[3]:
                    boxes[i] = {"layer": ",".join(sorted(set(boxes[i]["layer"].split(",") + boxes[j]["layer"].split(",")))),
                                "px": boxes[i]["px"] + boxes[j]["px"],
                                "bbox": [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]}
                    boxes.pop(j); changed = True; break
            if changed:
                break
    return [b for b in boxes if b["px"] >= min_px]


def dedupe(findings):
    """Same check at the same place in several frames: keep the biggest one."""
    def iou(a, b):
        ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
        u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - ix * iy
        return ix * iy / max(u, 1)
    keep = []
    for f in sorted(findings, key=lambda f: -f.get("px", 0)):
        if "bbox" in f and any(k["check"] == f["check"] and "bbox" in k and iou(k["bbox"], f["bbox"]) > 0.3 for k in keep):
            continue
        keep.append(f)
    return keep


# --------------------------------------------------------------------------- unity frames
def unity_to_ref(img, cam, H, W):
    ppu = cam["screen_h"] / (2 * cam["ortho_size"])

    def px(x, y):
        wx = cam["rig_x"] + (x - cam["origin_x"]) / cam["ref_ppu"]
        wy = (cam["ground_y"] - y) / cam["ref_ppu"]
        return cam["screen_w"] / 2 + (wx - cam["cam_x"]) * ppu, cam["screen_h"] / 2 - (wy - cam["cam_y"]) * ppu

    (x0, y0), (x1, y1) = px(0, 0), px(W, H)
    return img.crop((round(x0), round(y0), round(x1), round(y1))).resize((W, H), Image.LANCZOS)


# --------------------------------------------------------------------------- regions
def regions(ctx):
    tile = ctx.cfg.get("tile", 520)
    out = {}
    for i, n in enumerate(ctx.names):
        ys, xs = np.nonzero(ctx.lab == i)
        if len(xs) < 300:
            continue
        x0, y0, x1, y1 = xs.min() - 20, ys.min() - 20, xs.max() + 20, ys.max() + 20
        nx, ny = max(1, int(np.ceil((x1 - x0) / tile))), max(1, int(np.ceil((y1 - y0) / tile)))
        for a in range(nx):
            for b in range(ny):
                bx0 = int(x0 + (x1 - x0) * a / nx); bx1 = int(x0 + (x1 - x0) * (a + 1) / nx)
                by0 = int(y0 + (y1 - y0) * b / ny); by1 = int(y0 + (y1 - y0) * (b + 1) / ny)
                box = [max(bx0, 0), max(by0, 0), min(bx1, ctx.W), min(by1, ctx.H)]
                sub = ((ctx.lab == i)[box[1]:box[3], box[0]:box[2]]).sum()
                if sub >= 300:
                    out[f"{n}" + (f"-{a}{b}" if nx * ny > 1 else "")] = box
    for k, v in ctx.cfg.get("extra_regions", {}).items():
        out[k] = v
    return out


def sheet(tiles, path, label_font):
    w, h = tiles[0][1].size
    sc = 460 / max(w, h)
    tw, th = max(1, int(w * sc)), max(1, int(h * sc))
    o = Image.new("RGB", (len(tiles) * (tw + 6), th + 26), (30, 30, 30))
    d = ImageDraw.Draw(o)
    for i, (n, t) in enumerate(tiles):
        o.paste(t.resize((tw, th), Image.LANCZOS), (i * (tw + 6), 26))
        d.text((i * (tw + 6) + 4, 3), n, fill=(255, 255, 255), font=label_font)
    o.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--out")
    a = ap.parse_args()
    ctx = Ctx(a.config)
    out = Path(a.out) if a.out else ctx.base / "review"
    for d in ("regions", "hotspots"):
        (out / d).mkdir(parents=True, exist_ok=True)
    f = font(16)
    findings, frames_rgb = [], {}

    ref_img = Image.new("RGBA", (ctx.W, ctx.H), BG + (255,))
    ref_img.alpha_composite(Image.fromarray(ctx.ref))
    ref_img = ref_img.convert("RGB")

    # rest composite and its colour difference
    rest_rgb, _, _ = frame(ctx, None, 0.0)
    ra = cv2.cvtColor(cv2.GaussianBlur(np.asarray(ref_img), (0, 0), 2), cv2.COLOR_RGB2LAB).astype(float)
    ca = cv2.cvtColor(cv2.GaussianBlur(rest_rgb, (0, 0), 2), cv2.COLOR_RGB2LAB).astype(float)
    dmap = np.linalg.norm(ra - ca, axis=2)
    frames_rgb["rest(py)"] = Image.fromarray(rest_rgb)

    # gaps that exist in the art itself (between curls, inside rings) are not defects
    _, rest_owner, _ = frame(ctx, None, 0.0)
    art_gaps = np.zeros((ctx.H, ctx.W), bool)
    for h in interior_holes(rest_owner, max_area=10 ** 6, min_area=1):
        x0, y0, x1, y1 = h["bbox"]
        art_gaps[y0:y1, x0:x1] |= rest_owner[y0:y1, x0:x1] < 0
    art_gaps = cv2.dilate(art_gaps.astype(np.uint8), np.ones((25, 25), np.uint8)) > 0

    # posed python frames
    diag = {}
    for clip, fr in ctx.cfg["frames"]:
        rgb, owner, hidden = frame(ctx, clip, fr / ctx.fps)
        key = f"c{clip}f{fr}(py)"
        frames_rgb[key] = Image.fromarray(rgb)
        diag[key] = (rgb, owner, hidden)
        for h in merge_boxes(hidden_clusters(owner, hidden, ctx.rig.parts), min_px=HIDDEN_MIN):
            findings.append({"check": "hidden_exposed", "frame": key, **h})
        holes = []
        for h in interior_holes(owner, min_area=40):
            x0, y0, x1, y1 = h["bbox"]
            gap = (owner[y0:y1, x0:x1] < 0)
            if (gap & art_gaps[y0:y1, x0:x1]).sum() >= 0.5 * gap.sum():
                continue
            # a gap enclosed by one layer is that part's own opening (staff rings, hair curls);
            # a gap between different layers is a seam that opened
            X0, Y0 = max(x0 - 3, 0), max(y0 - 3, 0)
            sub = owner[Y0:y1 + 3, X0:x1 + 3]
            g = np.zeros(sub.shape, np.uint8); g[y0 - Y0:y0 - Y0 + gap.shape[0], x0 - X0:x0 - X0 + gap.shape[1]] = gap
            ring = (cv2.dilate(g, np.ones((5, 5), np.uint8)) > 0) & (g == 0) & (sub >= 0)
            if ring.any():
                top = np.bincount(sub[ring]).max() / ring.sum()
                if top >= 0.9:
                    continue
                h["layers"] = sorted({ctx.rig.parts[i]["name"] for i in np.unique(sub[ring])})
            holes.append({**h, "layer": ",".join(h.get("layers", []))})
        for h in merge_boxes(holes, min_px=60):
            findings.append({"check": "holes", "frame": key, **h})
        for h in islands(owner):
            findings.append({"check": "islands", "frame": key, **h})
    findings = dedupe(findings)

    # unity frames
    u = ctx.cfg.get("unity")
    if u:
        for name, path in u.get("frames", {}).items():
            im = Image.open(ctx.base / path).convert("RGB")
            frames_rgb[f"{name}(unity)"] = unity_to_ref(im, u["camera"], ctx.H, ctx.W)
        for a_last, b_first, a_first, a_second in u.get("joins", []):
            ld = lambda p: np.asarray(Image.open(ctx.base / p).convert("RGB")).astype(int)
            d = lambda x, y: int((np.abs(ld(x) - ld(y)).sum(2) > 40).sum())
            jump, step = d(a_last, b_first), d(a_first, a_second)
            findings.append({"check": "join_pop", "join": [a_last, b_first], "px": jump, "normal_step_px": step,
                             "severity": "high" if jump > 2 * step else "ok"})

    # regions: every one gets a sheet and a rest colour number
    regs = regions(ctx)
    must_look = []
    for k, (x0, y0, x1, y1) in sorted(regs.items(), key=lambda kv: (kv[1][1], kv[1][0])):
        m = ctx.A[y0:y1, x0:x1]
        share = float((dmap[y0:y1, x0:x1][m] > 25).mean()) if m.any() else 0.0
        if share > 0.02:
            findings.append({"check": "rest_colour", "region": k, "share_over_25": round(share, 3), "bbox": [x0, y0, x1, y1]})
        tiles = [("ref", ref_img.crop((x0, y0, x1, y1)))] + [(n, im.crop((x0, y0, x1, y1))) for n, im in frames_rgb.items()]
        path = out / "regions" / f"{len(must_look):02d}-{k}.png"
        sheet(tiles, path, f)
        must_look.append(str(path.relative_to(out)))

    # hotspots: every automatic motion finding gets a zoom (render | layers tinted)
    rng = np.random.RandomState(1)
    cols = (rng.rand(len(ctx.rig.parts), 3) * 200 + 55).astype(np.uint8)
    hot = 0
    for fd in findings:
        if fd["check"] not in ("hidden_exposed", "holes", "islands") or fd.get("px", 0) < 60:
            continue
        rgb, owner, hidden = diag[fd["frame"]]
        x0, y0, x1, y1 = fd["bbox"]
        pad = 50
        box = (max(x0 - pad, 0), max(y0 - pad, 0), min(x1 + pad, ctx.W), min(y1 + pad, ctx.H))
        tint = rgb.copy()
        m = hidden & (owner >= 0)
        tint[m] = (rgb[m] * 0.35 + cols[owner[m]] * 0.65).astype(np.uint8)
        if fd["check"] == "holes":
            tint[y0:y1, x0:x1][owner[y0:y1, x0:x1] < 0] = (255, 0, 255)
        tiles = [("ref", ref_img.crop(box)), ("rest", frames_rgb["rest(py)"].crop(box)),
                 (fd["frame"], Image.fromarray(rgb).crop(box)), ("hidden/holes", Image.fromarray(tint).crop(box))]
        path = out / "hotspots" / f"{hot:03d}-{fd['check']}-{fd['frame'][:7]}.png"
        sheet(tiles, path, f)
        fd["image"] = str(path.relative_to(out))
        must_look.append(fd["image"])
        hot += 1

    rep = {"config": str(Path(a.config).resolve()), "frames": list(frames_rgb), "regions": regs,
           "rest_share_over_25_all": round(float((dmap[ctx.A] > 25).mean()), 4),
           "findings": findings, "must_look": must_look}
    (out / "findings.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    counts = {}
    for fd in findings:
        counts[fd["check"]] = counts.get(fd["check"], 0) + 1
    (out / "README.md").write_text(
        "# Review\n\nAutomatic: " + json.dumps(counts) +
        f"\nRest pixels with LAB diff > 25: {rep['rest_share_over_25_all'] * 100:.2f} %\n\n"
        f"Sheets to look at: {len(must_look)} (regions {len(regs)}, hotspots {hot}). "
        "The reviewer opens every one and writes the verdict below.\n\n## Visual findings\n\n## Not checked\n",
        encoding="utf-8")
    print(json.dumps({"out": str(out), "counts": counts, "sheets": len(must_look),
                      "rest_share_over_25": rep["rest_share_over_25_all"]}))


if __name__ == "__main__":
    main()
