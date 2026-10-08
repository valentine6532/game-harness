"""v012 proportion guide: joint landmarks measured on the approved full-body art.

Writes guide.json (joints, bones with length/rest angle, head units) and
guide-overlay.png (skeleton on the faded reference). Every generated part is
later fitted to one bone of this guide with a uniform scale only.

Coordinates are reference pixels (1024x1536). Unity frame: 256 px = 1 unit,
origin x=620, floor y=1508 (same as v004-v011).
"""

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
REF = HERE.parents[2] / "2_art" / "estelle-fullbody-right.png"

# Measured on gridded zoom crops of the reference. R = staff arm / near leg (image right).
JOINTS = {
    "crown": (470, 78),        # top of the hair at the skull, horns excluded
    "chin": (548, 248),
    "headPivot": (548, 268),   # top of the neck, under the jaw
    "neckBase": (566, 322),
    "chest": (574, 440),       # underbust line on the spine
    "waist": (572, 578),
    "pelvis": (562, 690),
    "shoulderR": (650, 345),
    "elbowR": (712, 545),
    "wristR": (778, 447),
    "gripR": (798, 395),       # centre of the closed fist on the staff
    "shoulderL": (455, 372),   # far shoulder, behind hair and shawl
    "elbowL": (385, 588),
    "wristL": (302, 735),
    "fingerL": (205, 790),
    "hipR": (598, 715),
    "kneeR": (622, 1022),
    "ankleR": (633, 1305),
    "heelR": (612, 1472),
    "toeR": (722, 1490),
    "hipL": (522, 712),
    "kneeL": (524, 1025),
    "ankleL": (515, 1300),
    "heelL": (492, 1425),
    "toeL": (575, 1398),
    "staffTop": (800, 8),
    "staffOrb": (800, 155),
    "staffBottom": (772, 1452),
}

# bone: (parent, head joint, tail joint)
BONES = {
    "Pelvis": (None, "pelvis", "waist"),
    "Chest": ("Pelvis", "waist", "neckBase"),
    "Neck": ("Chest", "neckBase", "headPivot"),
    "Head": ("Neck", "headPivot", "crown"),
    "UpperArmR": ("Chest", "shoulderR", "elbowR"),
    "ForearmR": ("UpperArmR", "elbowR", "wristR"),
    "HandR": ("ForearmR", "wristR", "gripR"),
    "UpperArmL": ("Chest", "shoulderL", "elbowL"),
    "ForearmL": ("UpperArmL", "elbowL", "wristL"),
    "HandL": ("ForearmL", "wristL", "fingerL"),
    "ThighR": ("Pelvis", "hipR", "kneeR"),
    "ShinR": ("ThighR", "kneeR", "ankleR"),
    "FootR": ("ShinR", "ankleR", "toeR"),
    "ThighL": ("Pelvis", "hipL", "kneeL"),
    "ShinL": ("ThighL", "kneeL", "ankleL"),
    "FootL": ("ShinL", "ankleL", "toeL"),
    "Staff": ("HandR", "staffBottom", "staffTop"),
}

FLOOR_Y = 1508


def build():
    bones = {}
    for name, (parent, a, b) in BONES.items():
        (x0, y0), (x1, y1) = JOINTS[a], JOINTS[b]
        length = math.hypot(x1 - x0, y1 - y0)
        # angle in image space, 0 = pointing right, positive = clockwise (y down)
        angle = math.degrees(math.atan2(y1 - y0, x1 - x0))
        bones[name] = {"parent": parent, "from": a, "to": b,
                       "length_px": round(length, 1), "rest_angle_deg": round(angle, 1)}

    head_px = JOINTS["chin"][1] - JOINTS["crown"][1]
    height_px = FLOOR_Y - JOINTS["crown"][1]
    guide = {
        "reference": str(REF.relative_to(HERE.parents[2])).replace("\\", "/"),
        "canvas": [1024, 1536],
        "unity_frame": {"px_per_unit": 256, "origin_x": 620, "floor_y": FLOOR_Y},
        "head_px": head_px,
        "height_heads": round(height_px / head_px, 2),
        "joints": JOINTS,
        "bones": bones,
        "note": "Parts are drawn straight; the rest pose is these bone angles.",
    }
    (HERE / "guide.json").write_text(json.dumps(guide, indent=1), encoding="utf-8")
    render(guide)
    return guide


def render(guide):
    ref = Image.open(REF).convert("RGBA")
    base = Image.new("RGBA", ref.size, (255, 255, 255, 255))
    faded = ref.copy()
    faded.putalpha(ref.getchannel("A").point(lambda v: v * 45 // 100))
    base.alpha_composite(faded)
    d = ImageDraw.Draw(base)
    f = ImageFont.truetype("arial.ttf", 15)
    fb = ImageFont.truetype("arialbd.ttf", 18)
    J = guide["joints"]

    # head-unit ruler at the left edge
    top, hp = J["crown"][1], guide["head_px"]
    k = 0
    while top + k * hp <= FLOOR_Y + 1:
        y = top + k * hp
        d.line([(20, y), (60, y)], fill=(30, 30, 30), width=2)
        d.text((64, y - 9), f"{k}", fill=(30, 30, 30), font=fb)
        k += 1
    d.line([(40, top), (40, FLOOR_Y)], fill=(30, 30, 30), width=2)
    d.text((20, FLOOR_Y + 4), f"{guide['height_heads']} heads (head {hp}px)", fill=(30, 30, 30), font=f)

    colors = {"R": (220, 40, 40), "L": (40, 90, 220)}
    for name, b in guide["bones"].items():
        c = colors.get(name[-1], (20, 150, 60)) if name[-1] in "RL" else (20, 150, 60)
        if name == "Staff":
            c = (190, 140, 0)
        p0, p1 = J[b["from"]], J[b["to"]]
        d.line([p0, p1], fill=c, width=5)
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        d.text((mx + 6, my - 8), f"{name} {b['length_px']:.0f}", fill=c, font=f)
    for n, (x, y) in J.items():
        d.ellipse([x - 6, y - 6, x + 6, y + 6], outline=(0, 0, 0), fill=(255, 255, 255), width=2)
    d.line([(0, FLOOR_Y), (1024, FLOOR_Y)], fill=(120, 120, 120), width=1)
    base.convert("RGB").save(HERE / "guide-overlay.png")


if __name__ == "__main__":
    g = build()
    for n, b in g["bones"].items():
        print(f"{n:10s} {b['length_px']:7.1f}px {b['rest_angle_deg']:7.1f}deg")
    print("head", g["head_px"], "px, height", g["height_heads"], "heads")
