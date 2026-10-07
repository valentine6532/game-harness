"""Inspection helpers used throughout the decomposition method.

  python inspect_tools.py grid  <image> <x0> <y0> <x1> <y1> <zoom> <out.png> [step]
  python inspect_tools.py register <part.png> <reference.png> [x y w h]
  python inspect_tools.py overlay <render.png> <reference.png> <out.png> <px_per_unit> <cam_x> <cam_y> <root_x> <origin_x> <ground_y> [ref_ppu]
  python inspect_tools.py sheet <out.png> <tile_w> <tile_h> <img1> <img2> ...
  python inspect_tools.py mp4 <out.mp4> <fps> <frame1.png> <frame2.png> ...   (or a glob pattern)

`grid` is how polygon/joint coordinates are read: zoom a region with a labelled pixel grid,
look at it, and write coordinates in reference pixels. Repeat with a finer step near edges.
"""
import glob
import os
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw


def grid_zoom(image_path, box, zoom=2, step=20, out=None, bg=(30, 30, 45)):
    """Crop `box` (x0, y0, x1, y1), scale by `zoom`, draw a grid every `step` px with labels
    every 100 px (every 50 px when step <= 10). Coordinates stay in source pixels."""
    im = Image.open(image_path).convert("RGBA")
    base = Image.new("RGBA", im.size, bg + (255,))
    base.alpha_composite(im)
    x0, y0, x1, y1 = box
    c = base.crop(box).resize(((x1 - x0) * zoom, (y1 - y0) * zoom), Image.LANCZOS)
    d = ImageDraw.Draw(c)
    major = 50 if step <= 10 else 100
    for x in range(x0 - x0 % step, x1, step):
        xx = (x - x0) * zoom
        d.line([(xx, 0), (xx, c.height)], fill=(60, 200, 255) if x % major == 0 else (90, 90, 90))
        if x % major == 0:
            d.text((xx + 2, 2), str(x), fill=(0, 255, 255))
    for y in range(y0 - y0 % step, y1, step):
        yy = (y - y0) * zoom
        d.line([(0, yy), (c.width, yy)], fill=(255, 60, 60) if y % major == 0 else (90, 90, 90))
        if y % major == 0:
            d.text((2, yy + 2), str(y), fill=(255, 255, 0))
    if out:
        c.save(out)
    return c


def register_similarity(part_path, reference_path, box=None, ratio=0.78, reproj=6.0):
    """SIFT + RANSAC similarity mapping part pixels -> reference pixels.
    Returns (scale, rotation_deg_clockwise_on_screen, tx, ty, inliers)."""
    def gray(im):
        a = im[..., 3:4] / 255.0 if im.shape[2] == 4 else 1.0
        rgb = im[..., :3] * a + 30 * (1 - a)
        return cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_BGR2GRAY)
    ref = cv2.imread(reference_path, cv2.IMREAD_UNCHANGED)
    part = cv2.imread(part_path, cv2.IMREAD_UNCHANGED)
    ox = oy = 0
    if box:
        x, y, w, h = box
        part, ox, oy = part[y:y + h, x:x + w], x, y
    sift = cv2.SIFT_create(nfeatures=8000)
    mask = lambda im: (im[..., 3] > 8).astype(np.uint8) if im.shape[2] == 4 else None
    kr, dr = sift.detectAndCompute(gray(ref), mask(ref))
    kp, dp = sift.detectAndCompute(gray(part), mask(part))
    good = [m for m, n in cv2.BFMatcher().knnMatch(dp, dr, k=2) if m.distance < ratio * n.distance]
    if len(good) < 4:
        raise RuntimeError("too few matches: %d" % len(good))
    src = np.float32([[kp[m.queryIdx].pt[0] + ox, kp[m.queryIdx].pt[1] + oy] for m in good])
    dst = np.float32([kr[m.trainIdx].pt for m in good])
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=reproj)
    s = float(np.hypot(M[0, 0], M[1, 0]))
    r = float(np.degrees(np.arctan2(M[1, 0], M[0, 0])))
    return s, r, float(M[0, 2]), float(M[1, 2]), int(inl.sum())


def overlay_on_reference(render_path, reference_path, out, px_per_unit, cam_x, cam_y, root_x,
                         origin_x, ground_y, ref_ppu=256.0, alpha=0.5, bg=(9, 11, 24)):
    """Proportion check: place the reference at the scale/position the Unity render uses and
    blend both. Render: orthographic camera at (cam_x, cam_y), `px_per_unit` = height_px / (2*size).
    The rig instance sits at world x = root_x; reference px (x, y) maps to world
    (root_x + (x - origin_x)/ref_ppu, (ground_y - y)/ref_ppu)."""
    ren = Image.open(render_path).convert("RGB")
    ref = Image.open(reference_path).convert("RGBA")
    W, H = ren.size
    s = px_per_unit / ref_ppu
    bx = (root_x - origin_x / ref_ppu - cam_x) * px_per_unit + W / 2
    by = H / 2 - (ground_y / ref_ppu - cam_y) * px_per_unit
    placed = ref.transform(ren.size, Image.AFFINE, (1 / s, 0, -bx / s, 0, 1 / s, -by / s), resample=Image.BICUBIC)
    base = Image.new("RGBA", ren.size, bg + (255,))
    base.alpha_composite(placed)
    blend = Image.blend(ren, base.convert("RGB"), alpha)
    sheet = Image.new("RGB", (W * 3, H), bg)
    for i, im in enumerate((ren, base.convert("RGB"), blend)):
        sheet.paste(im, (W * i, 0))
    sheet.save(out)
    return sheet


def mask_overlay(image_path, masks, out, colors=None, bg=(20, 22, 36)):
    """Tint boolean masks {name: mask} over the image to review a segmentation."""
    im = Image.open(image_path).convert("RGBA")
    base = Image.new("RGBA", im.size, bg + (255,))
    base.alpha_composite(im)
    tint = np.zeros((im.height, im.width, 4), np.uint8)
    palette = [(255, 80, 80), (80, 255, 80), (80, 160, 255), (255, 220, 0), (255, 0, 255), (0, 255, 255)]
    for i, (name, m) in enumerate(masks.items()):
        c = (colors or {}).get(name, palette[i % len(palette)])
        tint[m] = tuple(c) + (150,)
    base.alpha_composite(Image.fromarray(tint, "RGBA"))
    base.save(out)
    return base


def contact_sheet(paths, out, tile=(320, 360), labels=None, bg=(9, 11, 24)):
    tiles = [Image.open(p).convert("RGB").resize(tile) for p in paths]
    top = 28 if labels else 0
    sheet = Image.new("RGB", (tile[0] * len(tiles), tile[1] + top), bg)
    d = ImageDraw.Draw(sheet)
    for i, t in enumerate(tiles):
        sheet.paste(t, (i * tile[0], top))
        if labels:
            d.text((i * tile[0] + 8, 8), labels[i], fill=(230, 220, 160))
    sheet.save(out)
    return sheet


def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


def encode_mp4(frames, out, fps=30, crf=18):
    """Encode PNG frames (in order, repeats allowed) to H.264 MP4 without assuming a numbering."""
    lst = out + ".txt"
    with open(lst, "w") as f:
        for p in frames:
            f.write("file '%s'\nduration %.6f\n" % (os.path.abspath(p).replace("\\", "/"), 1 / fps))
        f.write("file '%s'\n" % os.path.abspath(frames[-1]).replace("\\", "/"))
    try:
        subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
                        "-vf", "fps=%d,format=yuv420p" % fps, "-c:v", "libx264", "-crf", str(crf), out], check=True)
    finally:
        os.remove(lst)


if __name__ == "__main__":
    cmd, a = sys.argv[1], sys.argv[2:]
    if cmd == "grid":
        grid_zoom(a[0], tuple(map(int, a[1:5])), int(a[5]), int(a[7]) if len(a) > 7 else 20, a[6])
    elif cmd == "register":
        print("scale %.4f rot %.2f tx %.2f ty %.2f inliers %d" % register_similarity(a[0], a[1], tuple(map(int, a[2:6])) if len(a) >= 6 else None))
    elif cmd == "overlay":
        overlay_on_reference(a[0], a[1], a[2], *map(float, a[3:9]), *(map(float, a[9:10]) if len(a) > 9 else []))
    elif cmd == "sheet":
        contact_sheet(a[3:], a[0], (int(a[1]), int(a[2])))
    elif cmd == "mp4":
        frames = a[2:] if len(a) > 3 else sorted(glob.glob(a[2]))
        encode_mp4(frames, a[0], int(a[1]))
    else:
        raise SystemExit(__doc__)
