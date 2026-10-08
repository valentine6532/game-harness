"""Layer, refill, weight and mesh helpers for rigging a finished illustration in place.

Import this module from a per-character script that supplies the character data (polygons,
bones, weight chains). See ../references/layered-illustration-rig.md for the method.

Conventions
- Work in the pixel space of ONE reference image (y down). Layers are cut in place, so the
  reference pixel space is also every sprite's pixel space (one PPU for all sprites).
- Bones: list of (name, parent or None, (x, y)). Every joint rests at local rotation 0.
- Chains for weighting: {region: [(bone, anchor_xy), ...]}. Bone k owns segment k..k+1.

Requires numpy, opencv-python, Pillow.
"""
import json
import math
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw


# ----------------------------------------------------------------------------- masks
def poly_mask(poly, shape):
    """Boolean mask of a polygon (list of (x, y)) for an image of shape (H, W)."""
    m = Image.new("L", (shape[1], shape[0]), 0)
    ImageDraw.Draw(m).polygon([tuple(p) for p in poly], fill=255)
    return np.asarray(m) > 0


def hsv_channels(rgba):
    """Hue in degrees, saturation and value in 0..1."""
    hv = cv2.cvtColor(np.ascontiguousarray(rgba[..., :3]), cv2.COLOR_RGB2HSV_FULL).astype(float)
    return hv[..., 0] * 360 / 255, hv[..., 1] / 255, hv[..., 2] / 255


def keep_largest(mask):
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8))
    if n <= 1:
        return mask
    return lab == 1 + int(np.argmax(st[1:, 4]))


def drop_specks(mask, min_area=300):
    """Remove small disconnected islands (leftovers around removed parts)."""
    out = mask.copy()
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8))
    for i in range(1, n):
        if st[i, 4] < min_area:
            out[lab == i] = False
    return out


def dilate(mask, r):
    if r <= 0:
        return mask
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    return cv2.dilate(mask.astype(np.uint8), k) > 0


def erode(mask, r):
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    return cv2.erode(mask.astype(np.uint8), k) > 0


# ------------------------------------------------------------------------------ fills
def bleed(rgba, keep, extend):
    """Layer from `keep` pixels; `extend` pixels get the nearest kept colour (opaque).
    Use for hidden continuations such as a glove top that slides under a sleeve."""
    out = rgba.copy()
    out[..., 3] = np.where(keep, rgba[..., 3], 0)
    if extend.any():
        _, idx = cv2.distanceTransformWithLabels((~keep).astype(np.uint8), cv2.DIST_L2, 5,
                                                 labelType=cv2.DIST_LABEL_PIXEL)
        ys, xs = np.nonzero(keep)
        lab_to_pix = np.zeros((idx.max() + 1, 2), int)
        lab_to_pix[idx[keep]] = np.stack([ys, xs], 1)
        ey, ex = np.nonzero(extend & ~keep)
        src = lab_to_pix[idx[ey, ex]]
        out[ey, ex, :3] = rgba[src[:, 0], src[:, 1], :3]
        out[ey, ex, 3] = 255
    return out


def inpaint_holes(rgba, keep, holes, radius=7):
    """Base-layer refill: colour and coverage are inpainted (TELEA) where front layers were
    removed; coverage is smoothed so the new silhouette edge is anti-aliased."""
    rgb = np.ascontiguousarray(rgba[..., :3])
    a = np.where(keep, rgba[..., 3], 0).astype(np.uint8)
    m = (holes & ~keep).astype(np.uint8) * 255
    rgb2 = cv2.inpaint(rgb, m, radius, cv2.INPAINT_TELEA)
    a2 = cv2.inpaint(a, m, radius, cv2.INPAINT_TELEA)
    a2 = cv2.GaussianBlur(a2, (0, 0), 2.5)
    a2 = np.clip((a2.astype(float) - 128) * 4 + 128, 0, 255).astype(np.uint8)
    return np.dstack([rgb2, np.where(m > 0, a2, a)]).astype(np.uint8)


def mirror_fill_strip(source, base_rgba, base, strip):
    """Refill a thin removed strip (e.g. a staff shaft painted over cloth) row by row by
    blending mirrored real pixels from both sides. Rows where the strip touches open
    background keep the existing (inpainted) fill."""
    H, W = base.shape
    out = base_rgba.copy()
    hole = strip & ~base
    for y in np.unique(np.nonzero(hole)[0]):
        xs = np.nonzero(hole[y])[0]
        for run in np.split(xs, np.nonzero(np.diff(xs) > 1)[0] + 1):
            x0, x1 = run[0], run[-1]
            n = x1 - x0 + 1
            if not (x0 - 1 >= 0 and base[y, x0 - 1] and x1 + 1 < W and base[y, x1 + 1]):
                continue
            for i, x in enumerate(run):
                wl, wr = (n - i) / (n + 1), (i + 1) / (n + 1)
                lx, rx = max(x0 - 1 - i, 0), min(x1 + 1 + (n - 1 - i), W - 1)
                cl = source[y, lx] if base[y, lx] else None
                cr = source[y, rx] if base[y, rx] else None
                if cl is not None and cr is not None:
                    c = cl.astype(float) * wl + cr.astype(float) * wr
                    c[3] = 255 if (cl[3] > 128 or cr[3] > 128) else max(cl[3], cr[3])
                elif cl is not None or cr is not None:
                    c = (cl if cl is not None else cr).astype(float)
                else:
                    c = source[y, x0 - 1].astype(float)
                out[y, x] = np.clip(c, 0, 255).astype(np.uint8)
    return out


def mirror_extend_rows(source, out, region, texture_ok):
    """Continue a surface (e.g. a corset under a sleeve) into `region` by mirroring, per row,
    the strip of real texture just left of it. `texture_ok` marks usable source pixels;
    rows fall back to the row's median usable colour."""
    for y in np.unique(np.nonzero(region)[0]):
        xs = np.nonzero(region[y])[0]
        src = np.nonzero(texture_ok[y, :xs.min()])[0]
        if not len(src):
            continue
        edge_x = src.max() - 3
        row = source[y, texture_ok[y]][:, :3]
        tone = np.median(row, 0) if len(row) else source[y, edge_x, :3]
        for x in xs:
            mx = max(edge_x - (x - edge_x), 0)
            out[y, x, :3] = source[y, mx, :3] if texture_ok[y, mx] else tone
    return out


def procedural_folds(out, region, base_rgb, angle_deg=62, period_px=47, strength=0.16):
    """Fill `region` with a cloth base colour and soft diagonal fold shading."""
    ys, xs = np.nonzero(region)
    a = math.radians(angle_deg)
    u = (xs * math.cos(a) + ys * math.sin(a)) / 60.0
    v = (-xs * math.sin(a) + ys * math.cos(a)) / (period_px / (2 * math.pi))
    shade = 1 + strength * np.sin(v + 0.8 * np.sin(u * 2.1)) + 0.06 * np.sin(v * 2.7 + 1.3)
    out[ys, xs, :3] = np.clip(np.asarray(base_rgb, float)[None, :] * shade[:, None], 0, 255).astype(np.uint8)
    out[ys, xs, 3] = 255
    return out


# ----------------------------------------------------------------------------- weights
def chain_weights(pt, chain, blend=0.35):
    """{bone: weight} for a point against one chain [(bone, anchor_xy), ...]."""
    pts = [np.array(p, float) for _, p in chain]
    n = len(pts)
    if n == 1:
        return {chain[0][0]: 1.0}
    p = np.array(pt, float)
    best_d, s = None, 0.0
    for i in range(n - 1):
        a, b = pts[i], pts[i + 1]
        ab = b - a
        u = float(np.dot(p - a, ab) / np.dot(ab, ab))
        d = np.linalg.norm(a + ab * min(max(u, 0.0), 1.0) - p)
        if best_d is None or d < best_d - 1e-6:
            lo = -np.inf if i == 0 else 0.0
            hi = np.inf if i == n - 2 else 1.0
            best_d, s = d, i + min(max(u, lo), hi)
    s = min(max(s, 0.0), n - 1 + 0.999)
    w = {}
    for j in range(1, n):
        if abs(s - j) < blend:
            t = (s - (j - blend)) / (2 * blend)
            t = t * t * (3 - 2 * t)
            w[chain[j - 1][0]] = w.get(chain[j - 1][0], 0) + 1 - t
            w[chain[j][0]] = w.get(chain[j][0], 0) + t
            return w
    return {chain[min(int(math.floor(s)), n - 1)][0]: 1.0}


def weight_field(labels, names, chains, bone_names, sigma=14, scale=2, blend=0.35):
    """ONE shared weight field for all skinned layers.
    labels: int map (H, W) indexing `names`; chains: {name: [(bone, xy), ...]}.
    Returns field (bones, H/scale, W/scale), normalised, blurred by `sigma` px."""
    H, W = labels.shape
    h, w = H // scale, W // scale
    labs = labels[::scale, ::scale]
    field = np.zeros((len(bone_names), h, w), np.float32)
    ys, xs = np.mgrid[0:h, 0:w]
    for ci, cname in enumerate(names):
        sel = labs == ci
        if not sel.any():
            continue
        for yy, xx in zip(ys[sel], xs[sel]):
            for bn, wt in chain_weights((xx * scale, yy * scale), chains[cname], blend).items():
                field[bone_names.index(bn), yy, xx] += wt
    for i in range(len(bone_names)):
        if field[i].any():
            field[i] = cv2.GaussianBlur(field[i], (0, 0), sigma / scale)
    field /= np.maximum(field.sum(0, keepdims=True), 1e-6)
    return field


def sample_weights(field, bone_names, x, y, allowed=None, scale=2, order=None):
    """Top-4 (bone, weight) at a reference-space point; `allowed` restricts the bone set."""
    xi = min(max(int(round(x / scale)), 0), field.shape[2] - 1)
    yi = min(max(int(round(y / scale)), 0), field.shape[1] - 1)
    v = field[:, yi, xi].copy()
    if allowed is not None:
        mask = np.array([b in allowed for b in bone_names])
        if (v * mask).sum() > 1e-4:
            v = v * mask
        else:
            order = order or bone_names
            v = mask.astype(float) * 0
            v[bone_names.index(sorted(allowed, key=order.index)[0])] = 1
    top = [i for i in np.argsort(-v)[:4] if v[i] > 0.02] or [int(np.argmax(v))]
    tot = sum(v[i] for i in top)
    return [(bone_names[i], float(v[i] / tot)) for i in top]


# ------------------------------------------------------------------------------ meshes
def crop_layer(layer, pad=4):
    a = layer[..., 3] > 0
    ys, xs = np.nonzero(a)
    H, W = a.shape
    x0, y0 = max(0, xs.min() - pad), max(0, ys.min() - pad)
    x1, y1 = min(W, xs.max() + pad + 1), min(H, ys.max() + pad + 1)
    return layer[y0:y1, x0:x1], (int(x0), int(y0))


def grid_mesh(alpha, origin, cell, field, bone_names, allowed=None, scale=2):
    """Grid mesh over painted pixels. Vertices are image px (y down) of the cropped layer."""
    a = alpha > 0
    h, w = a.shape
    nx, ny = int(math.ceil(w / cell)), int(math.ceil(h / cell))
    vid, verts, tris, ecount = {}, [], [], {}

    def v(i, j):
        if (i, j) not in vid:
            vid[(i, j)] = len(verts)
            verts.append((float(min(i * cell, w)), float(min(j * cell, h))))
        return vid[(i, j)]

    for j in range(ny):
        for i in range(nx):
            if not a[max(0, j * cell - 2):min(h, (j + 1) * cell + 2), max(0, i * cell - 2):min(w, (i + 1) * cell + 2)].any():
                continue
            q = (v(i, j), v(i + 1, j), v(i + 1, j + 1), v(i, j + 1))
            tris += [q[0], q[1], q[3], q[1], q[2], q[3]]
            for e in ((q[0], q[1]), (q[1], q[2]), (q[2], q[3]), (q[3], q[0])):
                k = tuple(sorted(e))
                ecount[k] = ecount.get(k, 0) + 1
    weights = [sample_weights(field, bone_names, origin[0] + px, origin[1] + py, allowed, scale) for px, py in verts]
    edges = [list(k) for k, c in ecount.items() if c == 1]
    return verts, tris, edges, weights


def bone_tree(used, bones):
    """Smallest subtree (parents first) holding `used`, rooted at their lowest common ancestor."""
    parent = {n: p for n, p, _ in bones}

    def path(n):
        out = []
        while n:
            out.append(n)
            n = parent[n]
        return out[::-1]
    paths = [path(n) for n in used]
    lca = 0
    while all(len(p) > lca + 1 for p in paths) and len({p[lca + 1] for p in paths}) == 1:
        lca += 1
    root = paths[0][lca]
    keep = {root}
    for p in paths:
        keep.update(p[lca:])
    return [n for n, _, _ in bones if n in keep], root


# ------------------------------------------------------------------------------ export
def export_rig(layers, bones, order, skinned, rigid, field, cells, out_dir, unity_dir,
               allowed=None, body_field=None, body_layer=None, ppu=256.0, ground_y=None,
               origin_x=None, prefix="rig-", post_weights=None):
    """Write layer PNGs + rig.json (read by scripts/unity/LayeredRigBuild.cs).

    layers: {name: RGBA (H, W, 4) in reference space}; order: {name: sortingOrder};
    skinned: set of skinned layer names; rigid: {name: anchor bone};
    cells: {skinned name: grid cell px}; allowed: {name: set(bones) or None};
    body_field/body_layer: optional separate field for the base layer (e.g. without arms).
    post_weights(name, verts, weights, origin) -> weights: per-layer fix-ups such as
    rigid_region (bust stays one bone) and pin_to_body (shawl edge rests on the body).
    """
    allowed = allowed or {}
    bone_pos = {n: p for n, _, p in bones}
    parent = {n: q for n, q, _ in bones}
    bone_names = [n for n, _, _ in bones]
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.join(unity_dir, "Art"), exist_ok=True)
    parts = []
    for name, layer in layers.items():
        img, (ox, oy) = crop_layer(layer)
        h, w = img.shape[:2]
        file = prefix + name + ".png"
        Image.fromarray(img, "RGBA").save(os.path.join(out_dir, file))
        Image.fromarray(img, "RGBA").save(os.path.join(unity_dir, "Art", file))
        entry = dict(name=name, file=file, width=int(w), height=int(h), order=order[name], ppu=ppu,
                     originX=int(ox), originY=int(oy))
        if name in skinned:
            fld = body_field if (body_field is not None and name == body_layer) else field
            verts, tris, edges, wts = grid_mesh(img[..., 3], (ox, oy), cells[name], fld, bone_names, allowed.get(name))
            if post_weights is not None:          # e.g. rigid_region / pin_to_body
                wts = post_weights(name, verts, wts, (ox, oy))
            used = sorted({b for vw in wts for b, _ in vw}, key=bone_names.index)
            tree, root = bone_tree(used, bones)
            index = {n: i for i, n in enumerate(tree)}
            sb = []
            for n in tree:
                bx, by = bone_pos[n]
                if n == root:
                    sb.append(dict(name=n, parent=-1, x=float(bx - ox), y=float((oy + h) - by)))
                else:
                    px, py = bone_pos[parent[n]]
                    sb.append(dict(name=n, parent=index[parent[n]], x=float(bx - px), y=float(py - by)))
            flat = []
            for vw in wts:
                for bn, wt in (vw + [(vw[0][0], 0.0)] * 4)[:4]:
                    flat += [index[bn], wt]
            entry.update(bones=sb, vertices=[c for p in verts for c in (p[0], h - p[1])], indices=tris,
                         edges=[c for e in edges for c in e], weights=flat)
            anchor = root
        else:
            anchor = rigid[name]
        ax, ay = bone_pos[anchor]
        entry.update(anchor=anchor, pivotX=float((ax - ox) / w), pivotY=float(1 - (ay - oy) / h))
        parts.append(entry)
    rig = dict(refPpu=ppu, groundY=float(ground_y), originX=float(origin_x),
               bones=[dict(name=n, parent=p or "", x=q[0], y=q[1]) for n, p, q in bones], parts=parts)
    for d in (out_dir, unity_dir):
        with open(os.path.join(d, "rig.json"), "w", encoding="utf-8") as f:
            json.dump(rig, f)
    return rig


# ------------------------------------------------------------------------------ effects
def make_flash(path, size=256):
    """Generated cast-flash sprite: soft gold glow plus an eight-point star (RGBA)."""
    y, x = np.mgrid[0:size, 0:size].astype(float)
    c = (size - 1) / 2
    dx, dy = (x - c) / c, (y - c) / c
    r = np.hypot(dx, dy)
    ang = np.arctan2(dy, dx)
    glow = np.clip(1 - r, 0, 1) ** 2.2
    rays = np.clip(1 - r, 0, 1) * (np.abs(np.cos(2 * ang)) ** 40 + 0.55 * np.abs(np.cos(2 * ang + np.pi / 4)) ** 60)
    core = np.clip(1 - r / 0.18, 0, 1) ** 1.5
    a = np.clip(glow * 0.75 + rays * 0.9 + core, 0, 1)
    white = np.clip(core + rays * 0.6, 0, 1)
    rgb = np.stack([255 * np.ones_like(a), 214 + 41 * white, 120 + 135 * white], -1)
    Image.fromarray(np.concatenate([rgb, 255 * a[..., None]], -1).astype(np.uint8), "RGBA").save(path)


# ------------------------------------------------------------ weight post-processing
def rigid_region(weights, verts, origin, region_mask, bone):
    """Every vertex inside `region_mask` (reference space) follows `bone` only.
    Use for anatomy that must never bend or squash: bust, face, hands, rigid armour."""
    ox, oy = origin
    H, W = region_mask.shape
    out = []
    for (px, py), vw in zip(verts, weights):
        x, y = int(min(max(round(ox + px), 0), W - 1)), int(min(max(round(oy + py), 0), H - 1))
        out.append([(bone, 1.0)] if region_mask[y, x] else vw)
    return out


def pin_to_body(weights, verts, origin, body_mask, body_bone, band=18.0, y_fade=None):
    """Cloth lying on the body (a shawl over the bust edge) keeps `body_bone` near the body
    silhouette and hands over to its limb weights `band` px away. Optional y_fade=(y0, y1)
    fades the pin out below y0..y1 so lower cloth follows the limb fully.
    Keep the pinned band narrow and close to the joint pivot: a wide pin between a still body
    and a moving limb stretches the cloth (seen as smeared trims)."""
    ox, oy = origin
    dist = cv2.distanceTransform((~body_mask).astype(np.uint8), cv2.DIST_L2, 5)
    H, W = body_mask.shape
    out = []
    for (px, py), vw in zip(verts, weights):
        x, y = int(min(max(round(ox + px), 0), W - 1)), int(min(max(round(oy + py), 0), H - 1))
        t = min(max(dist[y, x] / band, 0.0), 1.0)
        t = t * t * (3 - 2 * t)
        body = sum(w for b, w in vw if b == body_bone)
        limb = [(b, w) for b, w in vw if b != body_bone]
        tot = sum(w for _, w in limb)
        if tot <= 0:
            out.append(vw)
            continue
        keep = body + (1 - body) * (1 - t)
        if y_fade:
            u = min(max((y - y_fade[0]) / (y_fade[1] - y_fade[0]), 0.0), 1.0)
            keep *= 1 - u * u * (3 - 2 * u)
        vw = [(body_bone, float(keep))] + [(b, float(w / tot * (1 - keep))) for b, w in limb]
        vw = sorted([v for v in vw if v[1] > 0.02], key=lambda v: -v[1])[:4]
        s = sum(w for _, w in vw)
        out.append([(b, w / s) for b, w in vw])
    return out


def soften_attachment(weights, verts, origin, roots, parent_bone, soft_px=170.0):
    """Hanging cloth (a panel simulated from `root` bones) hands its root weight to
    `parent_bone` near the attachment, fading over `soft_px` below it. roots = {bone: attach_y}.
    Spreads the gravity swing down the panel instead of shearing a narrow seam at the body."""
    ox, oy = origin
    out = []
    for (px, py), vw in zip(verts, weights):
        y = oy + py
        d = dict(vw)
        for root, y0 in roots.items():
            if d.get(root, 0) > 0:
                f = min(max((y - y0) / soft_px, 0.0), 1.0)
                f = f * f * (3 - 2 * f)
                moved = d[root] * (1 - f)
                d[root] -= moved
                d[parent_bone] = d.get(parent_bone, 0.0) + moved
        vw = sorted([(b, float(w)) for b, w in d.items() if w > 0.02], key=lambda v: -v[1])[:4]
        s = sum(w for _, w in vw)
        out.append([(b, w / s) for b, w in vw])
    return out
