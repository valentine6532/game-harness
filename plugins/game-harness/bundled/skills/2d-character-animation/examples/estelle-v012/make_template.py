"""Colouring-book template: grey limb silhouettes at guide proportions.

Usage: python make_template.py

Every limb segment is drawn vertically (proximal joint on top) at scale S of the
reference, with its length from guide.json, its width profile from the reference
(joint, 25/50/75 %, joint) and a rounded end continuing CAP px past each joint.
The generator paints inside the grey shapes, so length and width - the proportion -
come from the template, not from numbers in a prompt.

Writes template/limbs.png (RGBA, transparent background) and template/limbs.json
(per part: joint centres on the sheet, scale, width profile).
"""

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
G = json.loads((HERE / "guide" / "guide.json").read_text(encoding="utf-8"))
W, H = 1024, 1536
S = 1.7             # sheet scale vs reference (bigger = more detail; uniform for all parts)
CAP = 30            # px past each joint at reference scale
FILL = (200, 200, 200, 255)
LINE = (120, 120, 120, 255)

# Edge offsets from the bone axis, (t, a, b): a = image-right edge (negative),
# b = image-left edge (positive), in reference px along the perpendicular. Legs are
# measured on the reference skin where visible (skin/chiffon split by saturation) and
# extrapolated under cloth; the back leg is the front leg x0.92; arms are measured
# glove cross-sections plus anatomy (deltoid, elbow, forearm muscle, wrist).
def _sym(pairs):
    return [(t, -w / 2, w / 2) for t, w in pairs]
_THIGH_R = [(0, -78, 24), (0.25, -74, 20), (0.5, -68, 20), (0.65, -64, 23), (0.75, -50, 25),
            (0.85, -42, 28), (1.0, -31, 33)]
_SHIN_R = [(0, -31, 32), (0.1, -32, 39), (0.25, -33, 47), (0.4, -30, 43), (0.5, -29, 36),
           (0.6, -24, 29), (0.75, -22, 20), (0.9, -21, 14), (1.0, -19, 13)]
PROFILE = {
    "UpperArmR": _sym([(0, 60), (0.15, 62), (0.5, 52), (0.8, 46), (1.0, 44)]),
    "ForearmR": _sym([(0, 44), (0.25, 45), (0.5, 42), (0.75, 38), (1.0, 34)]),
    "UpperArmL": _sym([(0, 60), (0.15, 62), (0.5, 52), (0.8, 46), (1.0, 44)]),
    "ForearmL": _sym([(0, 44), (0.25, 44), (0.5, 40), (0.75, 36), (1.0, 32)]),
    "ThighR": _THIGH_R,
    "ShinR": _SHIN_R,
    "ThighL": [(t, a * 0.92, b * 0.92) for t, a, b in _THIGH_R],
    "ShinL": [(t, a * 0.92, b * 0.92) for t, a, b in _SHIN_R],
}
# columns: right arm, left arm, right leg, left leg (top segment, bottom segment)
COLUMNS = [("UpperArmR", "ForearmR"), ("UpperArmL", "ForearmL"),
           ("ThighR", "ShinR"), ("ThighL", "ShinL")]
GAP = 70


def outline(length, prof, cap):
    """Polygon in sheet space (x from the axis, y from the proximal joint), axis pointing
    down: an offset s maps to x = -s, so image-right edges stay on the right."""
    t = np.array([p[0] for p in prof]) * length
    ys = np.linspace(0, length, 80)
    a = np.interp(ys, t, [p[1] for p in prof])
    b = np.interp(ys, t, [p[2] for p in prof])
    k = np.hanning(21); k /= k.sum()                    # smooth the measured kinks
    a = np.convolve(np.pad(a, 10, mode="edge"), k, mode="valid")
    b = np.convolve(np.pad(b, 10, mode="edge"), k, mode="valid")
    right = [(-ai, y) for ai, y in zip(a, ys)]          # a < 0 -> x > 0
    left = [(-bi, y) for bi, y in zip(b, ys)]           # b > 0 -> x < 0
    c0, r0 = -(a[0] + b[0]) / 2, (b[0] - a[0]) / 2
    c1, r1 = -(a[-1] + b[-1]) / 2, (b[-1] - a[-1]) / 2
    top = [(c0 + r0 * np.cos(q), -cap * np.sin(q)) for q in np.linspace(0, np.pi, 30)]
    bot = [(c1 - r1 * np.cos(q), length + cap * np.sin(q)) for q in np.linspace(0, np.pi, 30)]
    return top + left + bot + right[::-1]


def main():
    out = HERE / "template"
    out.mkdir(exist_ok=True)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    col_w = W / len(COLUMNS)
    info = {"scale": S, "cap_px_ref": CAP, "parts": {}}
    for ci, pair in enumerate(COLUMNS):
        cx = col_w * (ci + 0.5)
        y = GAP
        for name in pair:
            b = G["bones"][name]
            L = b["length_px"] * S
            prof = [(t, a * S, b * S) for t, a, b in PROFILE[name]]
            cap = CAP * S
            y0 = y + cap
            poly = [(cx + x, y0 + yy) for x, yy in outline(L, prof, cap)]
            d.polygon(poly, fill=FILL, outline=LINE)
            info["parts"][name] = {
                "joint_from": [round(cx, 1), round(y0, 1)],
                "joint_to": [round(cx, 1), round(y0 + L, 1)],
                "bone": name,
                "edges_ref": PROFILE[name],
                "bbox": [round(min(p[0] for p in poly)), round(min(p[1] for p in poly)),
                         round(max(p[0] for p in poly)), round(max(p[1] for p in poly))],
            }
            y = y0 + L + cap + GAP
        if y > H:
            raise ValueError(f"column {ci} overflows ({y:.0f} px)")
    im.save(out / "limbs.png")
    (out / "limbs.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    prev = Image.new("RGBA", (W, H), (95, 95, 110, 255))
    prev.alpha_composite(im)
    prev.convert("RGB").save(out / "limbs-preview.png")
    for n, p in info["parts"].items():
        print(n, p["joint_from"], p["joint_to"], p["bbox"])


if __name__ == "__main__":
    main()
