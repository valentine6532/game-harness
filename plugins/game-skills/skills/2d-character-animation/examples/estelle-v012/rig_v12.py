"""Estelle v012: parts generated to the proportion guide, one bone per body part.

Body parts are rigid on their own bone (upper arm, forearm, hand, thigh, shin, foot, pelvis,
chest, neck, head); they were painted with rounded ends past each joint, so joints rotate
without gaps. Cloth and hair are skinned on simulated chains as in v011:
  hair      HairBack, FrontLockL
  shawl     SleeveL (chest / upper arm / panel chain), SleeveR (rigid), ShawlPanelL / R chains
  skirt     SkirtBack + ChiffonL / ChiffonR on the DressL / DressR columns; WaistDrape on the
            hips and the DressC column; WaistCharm rigid on the hips
Joint positions come from guide/guide.json.

Usage: python rig_v12.py extract | preview OUT.png
"""
import json
import math
import os
import shutil
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.normpath(os.path.join(HERE, "..", ".."))
LAYERS = os.path.join(HERE, "layers")
REFERENCE = os.path.join(REFS, "2_art", "estelle-fullbody-right.png")
UNITY_V12 = os.path.normpath(os.path.join(REFS, "..", "unity", "Estelle2D", "Assets", "EstelleV12"))
OUT_PARTS = os.path.join(HERE, "parts")
SKILL = os.path.join(os.environ.get("ANIM2D_SKILL", os.path.normpath(os.path.join(HERE, "..", ".."))), "scripts")
sys.path.insert(0, SKILL)
import rig_layers as rl  # noqa: E402  (grid_mesh, sample_weights, bone_tree, rigid_region, pin_to_body, soften_attachment)

PPU = 256.0
W, H = 1024, 1536
SCALE = 2              # weight fields at half resolution
SIGMA = 14             # px, smooths region borders
BLEND = 0.35

# ------------------------------------------------------------------------ skeleton (ref px)
GUIDE = json.load(open(os.path.join(HERE, "guide", "guide.json")))["joints"]
J = {k: tuple(v) for k, v in GUIDE.items()}
BONES = [
    ("Root", None, (620, 1508)),
    ("Hips", "Root", J["pelvis"]),
    ("Chest", "Hips", J["waist"]),            # the torso bends at the waist, never through the bust
    ("Neck", "Chest", J["neckBase"]),
    ("Head", "Neck", J["headPivot"]),
    ("HairL1", "Neck", (420, 420)),
    ("HairL2", "HairL1", (360, 580)),
    ("HairL3", "HairL2", (300, 730)),
    ("HairR1", "Neck", (680, 400)),
    ("HairR2", "HairR1", (735, 540)),
    ("FreeShoulder", "Chest", J["shoulderL"]),
    ("FreeElbow", "FreeShoulder", J["elbowL"]),
    ("FreeWrist", "FreeElbow", J["wristL"]),
    ("ShawlL1", "Chest", (380, 640)),
    ("ShawlL2", "ShawlL1", (310, 880)),
    ("ShawlL3", "ShawlL2", (220, 1130)),
    ("StaffShoulder", "Chest", J["shoulderR"]),
    ("StaffElbow", "StaffShoulder", J["elbowR"]),
    ("StaffWrist", "StaffElbow", J["wristR"]),
    ("StaffTip", "StaffWrist", (801, 160)),
    ("ShawlR1", "Chest", (752, 570)),
    ("ShawlR2", "ShawlR1", (825, 810)),
    ("ShawlR3", "ShawlR2", (895, 1070)),
    ("ThighR", "Hips", J["hipR"]),
    ("KneeR", "ThighR", J["kneeR"]),
    ("AnkleR", "KneeR", J["ankleR"]),
    ("ThighL", "Hips", J["hipL"]),
    ("KneeL", "ThighL", J["kneeL"]),
    ("AnkleL", "KneeL", J["ankleL"]),
    ("DressL1", "Hips", (485, 770)),
    ("DressL2", "DressL1", (440, 1010)),
    ("DressL3", "DressL2", (400, 1250)),
    ("DressC1", "Hips", (600, 770)),
    ("DressC2", "DressC1", (612, 1010)),
    ("DressC3", "DressC2", (622, 1250)),
    ("DressR1", "Hips", (690, 770)),
    ("DressR2", "DressR1", (718, 1010)),
    ("DressR3", "DressR2", (738, 1250)),
]
BONE_NAMES = [n for n, _, _ in BONES]
BONE_POS = {n: p for n, _, p in BONES}
PARENT = {n: q for n, q, _ in BONES}

# Chains: [(bone, anchor)], bone k owns the segment anchor k .. k+1 (the last one extends).
CHAINS = {
    # Chest anchor below the underbust: the spine bends at the waist, never through the bust.
    "torso": [("Hips", (566, 640)), ("Chest", (572, 560))],
    "head": [("Neck", (565, 250))],
    "hairL": [("Neck", (450, 320)), ("HairL1", (420, 420)), ("HairL2", (360, 580)), ("HairL3", (300, 730))],
    "hairR": [("Neck", (640, 290)), ("HairR1", (680, 400)), ("HairR2", (735, 540))],
    "freeArm": [("Chest", (485, 310)), ("FreeShoulder", (452, 385)), ("FreeElbow", (418, 550))],
    "staffArm": [("Chest", (650, 318)), ("StaffShoulder", (672, 352)), ("StaffElbow", (706, 520)),
                 ("StaffWrist", (782, 462))],
    "sleeveL": [("Chest", (455, 340)), ("FreeShoulder", (440, 430)), ("ShawlL1", (385, 620))],
    "panelL": [("ShawlL1", (385, 620)), ("ShawlL2", (310, 880)), ("ShawlL3", (220, 1130))],
    "panelR": [("ShawlR1", (748, 570)), ("ShawlR2", (825, 810)), ("ShawlR3", (895, 1070))],
    "dressL": [("Hips", (560, 660)), ("DressL1", (485, 770)), ("DressL2", (440, 1010)), ("DressL3", (400, 1250))],
    "dressC": [("Hips", (590, 660)), ("DressC1", (600, 770)), ("DressC2", (612, 1010)), ("DressC3", (622, 1250))],
    "dressR": [("Hips", (620, 660)), ("DressR1", (690, 770)), ("DressR2", (718, 1010)), ("DressR3", (738, 1250))],
}

# ------------------------------------------------------------------------ regions (ref px)
HEAD_POLY = [(350, 350), (430, 332), (470, 306), (515, 274), (545, 257), (575, 252), (605, 256),
             (632, 264), (662, 286), (730, 300), (760, 300), (760, 0), (330, 0), (330, 350)]
# Base-body arms, read off gridded zooms of Body.png. The inner edge follows the armpit and the
# bust contour so the torso keeps its own weights.
FREE_ARM_POLY = [(478, 282), (445, 296), (428, 380), (412, 470), (398, 530), (366, 600), (318, 680),
                 (268, 728), (186, 772), (186, 846), (272, 832), (334, 764), (392, 684), (440, 598),
                 (464, 526), (478, 462), (488, 400), (492, 330)]
STAFF_ARM_POLY = [(640, 282), (676, 296), (692, 330), (700, 378), (704, 430), (712, 468), (744, 446),
                  (772, 420), (772, 336), (860, 326), (860, 492), (800, 494), (760, 518), (732, 544),
                  (704, 562), (672, 552), (660, 512), (664, 470), (682, 456), (694, 430), (694, 382),
                  (682, 340), (652, 304)]
# Rigid anatomy.
BUST_POLY = [(505, 290), (655, 290), (684, 350), (694, 400), (692, 440), (676, 462), (520, 462), (500, 420)]
# Free forearm and hand of the base body, rigid on the elbow like the painted glove over it.
FREE_FOREARM_POLY = [(430, 555), (470, 555), (440, 640), (330, 770), (270, 850), (150, 850), (170, 760), (300, 680), (380, 590)]
HAND_POLY = [(770, 346), (800, 348), (817, 362), (834, 384), (836, 416), (828, 447), (809, 471),
             (792, 482), (772, 474), (765, 440), (767, 400)]
# Shawl pin: sleeve pixels within PIN_BAND of the torso silhouette stay on Chest (above the underbust).
TORSO_EDGE_POLY = [(520, 300), (640, 300), (672, 330), (690, 380), (692, 430), (682, 460), (668, 500), (660, 560),
                   (560, 560), (535, 500), (520, 450)]
PIN_BAND = 18.0
PIN_FADE = (430.0, 470.0)
# Hanging panels hand their root weight to Chest near where they hang (soft attachment).
PANEL_ROOTS = {"ShawlR1": 545.0, "ShawlL1": 600.0}
PANEL_SOFT = 170.0
# Legs lean from the hips (top of the thigh) to the planted feet.
LEG_TOP, LEG_PLANT = 690.0, 1250.0
# Chiffon columns: left column -> DressL, right column -> DressR, wide blend between them.
CHIFFON_SPLIT = (530.0, 670.0)
CHIFFON_HIPS = (640.0, 720.0)
DRAPE_WAIST = (640.0, 740.0)
PANEL_FLOOR = (1290.0, 400.0)       # y where the left panel's hem meets the floor, x left of which it lies there
HEM_FLOOR = (1330.0, 1450.0)       # dress-wide: from here down to the floor the hem blends onto the root
CHIFFON_FLOOR = (1280.0, 380.0)      # y where the floor pooling starts, x left of which it is on the floor


def poly_mask(poly, shape=(H, W)):
    m = Image.new("L", (shape[1], shape[0]), 0)
    ImageDraw.Draw(m).polygon([tuple(p) for p in poly], fill=255)
    return np.asarray(m) > 0


def smooth(u):
    u = np.clip(u, 0.0, 1.0)
    return u * u * (3 - 2 * u)


# ------------------------------------------------------------------------ weight fields
def chain_field(xs, ys, chain):
    """Vectorised rig_layers.chain_weights: {bone: weight array} for points (xs, ys)."""
    n = len(chain)
    if n == 1:
        return {chain[0][0]: np.ones_like(xs)}
    pts = [np.array(p, float) for _, p in chain]
    best_d = np.full(xs.shape, np.inf)
    s = np.zeros(xs.shape)
    for i in range(n - 1):
        a, b = pts[i], pts[i + 1]
        ab = b - a
        u = ((xs - a[0]) * ab[0] + (ys - a[1]) * ab[1]) / float(ab @ ab)
        uc = np.clip(u, 0.0, 1.0)
        d = np.hypot(a[0] + ab[0] * uc - xs, a[1] + ab[1] * uc - ys)
        lo = -np.inf if i == 0 else 0.0
        hi = np.inf if i == n - 2 else 1.0
        better = d < best_d - 1e-6
        best_d = np.where(better, d, best_d)
        s = np.where(better, i + np.clip(u, lo, hi), s)
    s = np.clip(s, 0.0, n - 1 + 0.999)
    out = {}

    def add(bone, w):
        out[bone] = out.get(bone, 0.0) + w

    done = np.zeros(xs.shape, bool)
    for j in range(1, n):
        zone = (np.abs(s - j) < BLEND) & ~done
        t = smooth((s - (j - BLEND)) / (2 * BLEND))
        add(chain[j - 1][0], np.where(zone, 1 - t, 0.0))
        add(chain[j][0], np.where(zone, t, 0.0))
        done |= zone
    k = np.clip(np.floor(s).astype(int), 0, n - 1)
    for j in range(n):
        add(chain[j][0], np.where(~done & (k == j), 1.0, 0.0))
    return out


def legs_field(xs, ys):
    t = smooth((ys - LEG_TOP) / (LEG_PLANT - LEG_TOP))
    return {"Hips": 1 - t, "Root": t}


def build_field(terms, sigma=SIGMA):
    """terms: [(coef (H, W) float or bool, fn(xs, ys) -> {bone: w})]. Returns (bones, h, w)."""
    h, w = H // SCALE, W // SCALE
    ys, xs = np.mgrid[0:h, 0:w].astype(float) * SCALE
    field = np.zeros((len(BONE_NAMES), h, w), np.float32)
    for coef, fn in terms:
        c = np.asarray(coef, float)[::SCALE, ::SCALE]
        if not c.any():
            continue
        for bone, wt in fn(xs, ys).items():
            field[BONE_NAMES.index(bone)] += (c * wt).astype(np.float32)
    for i in range(len(BONE_NAMES)):
        if field[i].any():
            field[i] = cv2.GaussianBlur(field[i], (0, 0), sigma / SCALE)
    field /= np.maximum(field.sum(0, keepdims=True), 1e-6)
    return field


def chain(name):
    return lambda xs, ys: chain_field(xs, ys, CHAINS[name])


def fields():
    y = np.arange(H)[:, None].repeat(W, 1).astype(float)
    x = np.arange(W)[None, :].repeat(H, 0).astype(float)
    free_arm, staff_arm, head = poly_mask(FREE_ARM_POLY), poly_mask(STAFF_ARM_POLY), poly_mask(HEAD_POLY)
    other = ~(free_arm | staff_arm | head)
    upper = other & (y < LEG_TOP)
    lower = other & (y >= LEG_TOP)
    F = {}
    left = x < 560
    F["hair"] = build_field([(left, chain("hairL")), (~left, chain("hairR"))])
    F["hairL"] = build_field([(np.ones((H, W)), chain("hairL"))])
    F["hairR"] = build_field([(np.ones((H, W)), chain("hairR"))])
    F["torso"] = build_field([(np.ones((H, W)), chain("torso"))])
    F["dressC"] = build_field([(np.ones((H, W)), chain("dressC"))])
    # the drape hangs from the waist: torso chain at the waist, the DressC column below
    waist = 1 - smooth((y - DRAPE_WAIST[0]) / (DRAPE_WAIST[1] - DRAPE_WAIST[0]))
    F["drape"] = build_field([(waist, chain("torso")), (1 - waist, chain("dressC"))])
    hips = 1 - smooth((y - CHIFFON_HIPS[0]) / (CHIFFON_HIPS[1] - CHIFFON_HIPS[0]))
    right = smooth((x - CHIFFON_SPLIT[0]) / (CHIFFON_SPLIT[1] - CHIFFON_SPLIT[0]))
    # the hem pooled on the floor far left rests on the ground (root) instead of sweeping with
    # the tip of the left column
    # the hem that lies on the floor rests on the ground (root) across the whole dress, so it never
    # lifts off the floor or slides out under the shoes
    floor = np.maximum(smooth((y - CHIFFON_FLOOR[0]) / 150.0) * smooth((CHIFFON_FLOOR[1] - x) / 180.0),
                       smooth((y - HEM_FLOOR[0]) / (HEM_FLOOR[1] - HEM_FLOOR[0])))
    root = lambda xs, ys: {"Root": np.ones_like(xs)}
    F["chiffon"] = build_field([(hips, chain("torso")), ((1 - hips) * (1 - right) * (1 - floor), chain("dressL")),
                                ((1 - hips) * right * (1 - floor), chain("dressR")), ((1 - hips) * floor, root)])
    # the left panel's hem pooled on the floor rests on the ground with the chiffon hem there
    pfloor = smooth((y - PANEL_FLOOR[0]) / 120.0) * smooth((PANEL_FLOOR[1] - x) / 120.0)
    F["panelL"] = build_field([(1 - pfloor, chain("panelL")), (pfloor, lambda xs, ys: {"Root": np.ones_like(xs)})])
    F["panelR"] = build_field([(np.ones((H, W)), chain("panelR"))])
    F["sleeveL"] = build_field([(np.ones((H, W)), chain("sleeveL"))])
    return F


# ------------------------------------------------------------------------ layers
sys.path.insert(0, HERE)
from assemble_v12 import ORDER as _ORDER  # noqa: E402  back -> front
ORDER = [n for n in _ORDER if os.path.exists(os.path.join(LAYERS, n + ".png"))]
PART = {n: n for n in ORDER}
SORT = {n: 10 * (i + 1) for i, n in enumerate(ORDER)}
SKINNED = {
    # part: (field, allowed bones, grid cell px)
    "HairBack": ("hair", None, 20),
    "FrontLockL": ("hair", None, 14),
    "WaistDrape": ("drape", {"Hips", "Chest", "DressC1", "DressC2", "DressC3"}, 16),
    "SkirtBack": ("chiffon", None, 24),
    "ChiffonL": ("chiffon", None, 24),
    "ChiffonR": ("chiffon", None, 22),
    "FrontPanel": ("chiffon", None, 24),
    "ShawlPanelL": ("panelL", None, 22),
    "ShawlPanelR": ("panelR", None, 22),
    "SleeveL": ("sleeveL", None, 14),
}
RIGID = {
    "Head": "Head", "Neck": "Neck", "Chest": "Chest", "Pelvis": "Hips", "WaistCharm": "Hips",
    "UpperArmL": "FreeShoulder", "ForearmL": "FreeElbow", "HandL": "FreeWrist",
    "UpperArmR": "StaffShoulder", "SleeveR": "StaffShoulder", "ForearmR": "StaffElbow",
    "HandR_back": "StaffWrist", "HandR_front": "StaffWrist", "Staff": "StaffWrist",
    "ThighR": "ThighR", "ShinR": "KneeR", "FootR": "AnkleR",
    "ThighL": "ThighL", "ShinL": "KneeL", "FootL": "AnkleL",
}
PIECE_CELL = 12


# Joints between rigid limb parts. Every limb end at a joint is replaced by a straight extension of
# the part's own colours (no painted end-cap outline), so no arc shows at the joint in any pose.
# The part drawn in FRONT at a joint then fades out past the joint over the one behind.
# (part, joint, other end of the part, fade?)  fade=True for the part in front at that joint.
ENDS = [
    # limbs are cut from one continuous in-place piece with an overlap band (split_limbs.py): the
    # piece in front fades over the one behind, which shows the same paint -> no seam at rest,
    # no end-cap outline in motion
    ("ShinR", "kneeR", "ankleR", True), ("ShinL", "kneeL", "ankleL", True),
    # the shin ends at the ankle over the shoe (the foot piece carries the skin inside the shoe)
    ("ShinR", "ankleR", "kneeR", True), ("ShinL", "ankleL", "kneeL", True),
    ("ForearmR", "elbowR", "wristR", True), ("ForearmL", "elbowL", "wristL", True),
    # the proportion-template upper arm of the staff side (hidden under the sleeve) keeps a straight end
    ("UpperArmR", "elbowR", "shoulderR", False),
]
END_INSET, END_LEN = 8.0, 34.0          # sample colours END_INSET px inside the joint, extend END_LEN past it
FEATHER_KEEP, FEATHER_IN = 3.0, 22.0


def straighten_end(img, joint, other):
    p = np.array(J[joint], float)
    d = np.array(J[other], float) - p
    d /= np.linalg.norm(d)
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)
    t = (xs - p[0]) * d[0] + (ys - p[1]) * d[1]
    zone = t < END_INSET
    shift = np.where(zone, END_INSET - t, 0).astype(np.float32)
    mx = (xs + shift * d[0]).astype(np.float32); my = (ys + shift * d[1]).astype(np.float32)
    src = cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    out = img.copy()
    out[zone] = src[zone]
    out[t < -END_LEN, 3] = 0
    return out


def fade_end(img, joint, other):
    p = np.array(J[joint], float)
    d = np.array(J[other], float) - p
    d /= np.linalg.norm(d)
    ys, xs = np.mgrid[0:H, 0:W]
    t = (xs - p[0]) * d[0] + (ys - p[1]) * d[1]          # < 0 past the joint
    f = smooth((t + FEATHER_KEEP + FEATHER_IN) / FEATHER_IN)
    img = img.copy()
    img[..., 3] = (img[..., 3] * f).astype(np.uint8)
    return img


RIM_PX = {"UpperArmR": 3, "SkirtBack": 3, "Pelvis": 3}   # only layers still made of raw template paint; the rest carry reference edges


FILL_HOLES = {"FrontPanel", "HairBack", "FrontLockL", "SkirtBack", "ChiffonL", "ChiffonR", "ShawlPanelL", "ShawlPanelR",
              "WaistDrape", "SleeveL", "SleeveR", "Pelvis"}
HOLE_MAX = 1500          # px; enclosed gaps smaller than this are painted over (not the staff rings)


def fill_holes(img):
    a = img[..., 3] > 128
    n, lab, st, _ = cv2.connectedComponentsWithStats((~a).astype(np.uint8), connectivity=4)
    holes = np.zeros(a.shape, bool)
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if area < HOLE_MAX and x > 0 and y > 0 and x + w < W and y + h < H:
            holes |= (lab == i) & REF_A          # gaps that show background at rest stay open
    if holes.any():
        img[..., :3] = cv2.inpaint(np.ascontiguousarray(img[..., :3]), holes.astype(np.uint8), 4, cv2.INPAINT_TELEA)
        img[holes, 3] = 255
    return img


# Cloth and hair edges that sit under another part at rest (template cut lines): faded, so they
# never show as a hard line when the covering part moves away.
HIDDEN_EDGES = {
    "HairBack": ("Head", "Neck", "Chest", "SleeveL", "SleeveR", "FrontLockL"),
    "Neck": ("Head", "Chest"),
    "SleeveL": ("ShawlPanelL",), "SleeveR": ("ShawlPanelR",),      # sleeve hem blends into its panel (same fabric)
    "SkirtBack": ("Pelvis", "WaistDrape", "Chest", "ChiffonR", "ChiffonL", "FrontPanel"),
    "ShawlPanelL": ("FrontPanel", "ChiffonL", "SleeveL", "ForearmL", "HandL"),
    "ShawlPanelR": ("ChiffonR", "WaistDrape", "SleeveR", "Chest"),
    "ChiffonR": ("ThighR", "ShinR", "FootR", "ThighL", "ShinL", "FootL", "FrontPanel", "ChiffonL", "WaistDrape"),
    "FrontPanel": ("ChiffonL", "WaistDrape", "ThighR"),
    "ChiffonL": ("WaistDrape", "ThighR", "ShinR"),
    "WaistDrape": ("Chest", "WaistCharm"),
}


# Covered edges fade only a few px: a wide fade turned hair and cloth into see-through ghosts
# whenever the covering part moved away. Rigid limbs and props are never faded here.
HIDDEN_PX = {}
HIDDEN_DEFAULT = 5.0
EDGE_SIGMA = 0.7
NO_HIDDEN_FEATHER = {"UpperArmR", "UpperArmL", "ForearmR", "ForearmL", "ThighR", "ThighL", "ShinR", "ShinL",
                     "FootR", "FootL", "HandL", "HandR_back", "HandR_front", "Staff", "Head", "WaistCharm"}


def hidden_edge_feather(img, cover, px=22.0):
    """Fade the part within `px` of the stretch of its outline that lies under `cover` (the
    parts drawn in front of it), so the cut never shows as a hard line when they move."""
    a = img[..., 3] > 128
    edge = a & ~(cv2.erode(a.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
    hidden = edge & (cv2.dilate(cover.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0)
    if hidden.any():
        dist = cv2.distanceTransform((~hidden).astype(np.uint8), cv2.DIST_L2, 5)
        f = np.where(cover, smooth(dist / px), 1.0)      # never fade what is visible at rest
        img[..., 3] = (img[..., 3] * f).astype(np.uint8)
    return img


def antialias(img, name):
    """Codex composites its paint through the template mask and leaves a 2-3 px dark stair-step
    rim along the edge. Shave the rim, extend the colour 3 px outward, then soften the alpha
    edge, so the outline does not read as a dashed line."""
    r = RIM_PX.get(name, 0)
    if r == 0:
        return img
    keep = cv2.erode((img[..., 3] > 128).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    img[..., 3] = np.where(keep > 0, img[..., 3], 0)
    a = img[..., 3] > 128
    band = (cv2.dilate(a.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0) & ~a
    if band.any():
        x0, y0, bw, bh = cv2.boundingRect(band.astype(np.uint8))
        x0, y0 = max(x0 - 4, 0), max(y0 - 4, 0)
        sub = np.ascontiguousarray(img[y0:y0 + bh + 8, x0:x0 + bw + 8, :3])
        img[y0:y0 + bh + 8, x0:x0 + bw + 8, :3] = cv2.inpaint(sub, band[y0:y0 + bh + 8, x0:x0 + bw + 8].astype(np.uint8), 3, cv2.INPAINT_TELEA)
    img[..., 3] = cv2.GaussianBlur(img[..., 3], (0, 0), 0.8)
    return img


LABELS = np.load(os.path.join(HERE, "labelmap", "owner.npy"))
LABEL_NAMES = json.load(open(os.path.join(HERE, "labelmap", "labels.json"), encoding="utf-8"))["names"]
REF_A = np.asarray(Image.open(os.path.join(HERE, "reference.png")).convert("RGBA"))[..., 3] > 128
RIM = (cv2.dilate(REF_A.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & ~REF_A
_REF = np.asarray(Image.open(os.path.join(HERE, "reference.png")).convert("RGBA"))
REF_ALPHA, REF_RGB = _REF[..., 3], _REF[..., :3]
from assemble_v12 import LABEL_OF  # noqa: E402


def label_mask(layer):
    lab = LABEL_OF.get(layer, layer)
    return LABELS == LABEL_NAMES.index(lab) if lab in LABEL_NAMES else np.zeros((H, W), bool)


def rest_clip(img, i):
    """At rest a layer may only show where its own part is visible or where a part in front covers
    it (labelmap). Pixels over a part that is behind it, or over the background, are removed."""
    allowed = label_mask(ORDER[i]).copy()
    for n in ORDER[i + 1:]:
        allowed |= label_mask(n)
    allowed |= RIM                                               # anti-aliased rim of the silhouette
    bad = (img[..., 3] > 0) & ~allowed
    img[bad, 3] = 0
    out_a = ~REF_A                                               # outside the silhouette: never more opaque than the art
    img[..., 3] = np.where(out_a, np.minimum(img[..., 3], REF_ALPHA), img[..., 3])
    return img, int(bad.sum())


def drop_islands(img, name):
    """Pieces of hidden paint that do not touch the part's visible region float free in motion
    (a chiffon strip left under the staff). Remove them."""
    own = label_mask(name)
    if not own.any():
        return img
    a = img[..., 3] > 20
    n, lab = cv2.connectedComponents(a.astype(np.uint8), connectivity=8)
    keep = np.unique(lab[a & own])
    drop = a & ~np.isin(lab, keep)
    img[drop, 3] = 0
    return img


def coverage_fill(out, raw):
    """Every pixel visible at rest must show its own part: where the top layer is not the owner
    (a front layer faded, a kept part's outline is a few px short), the owner layer gets the
    reference pixel there, fully opaque."""
    top = np.full((H, W), -1)
    for i, n in enumerate(ORDER):
        top[out[n][..., 3] > 200] = i
    owners = {}
    for n in ORDER:
        owners.setdefault(LABEL_OF.get(n, n), []).append(n)
    fixed = {}
    for lab_name, layers in owners.items():
        if lab_name not in LABEL_NAMES:
            continue
        own = LABELS == LABEL_NAMES.index(lab_name)
        idx = [ORDER.index(n) for n in layers]
        gap = own & ~np.isin(top, idx)
        if not gap.any():
            continue
        # pick the owner piece that had paint there, else the one drawn furthest back
        for n in sorted(layers, key=ORDER.index, reverse=True):
            sel = gap & (raw[n][..., 3] > 0)
            if n == layers[0]:
                sel = gap.copy()
            if sel.any():
                out[n][sel, :3] = REF_RGB[sel]
                out[n][sel, 3] = 255
                fixed[n] = fixed.get(n, 0) + int(sel.sum())
                gap &= ~sel
    return fixed


def load_layers(report=False):
    """Process front -> back, so a layer's 'covered' test uses the finished alpha of the layers in
    front of it (a faded or clipped front layer never leaves a hole)."""
    out, raw = {}, {}
    for n in ORDER:
        img = np.asarray(Image.open(os.path.join(LAYERS, n + ".png")).convert("RGBA")).copy()
        img[img[..., 3] <= 8, 3] = 0
        raw[n] = img
    # the staff upper arm is a hidden limb under the shawl sleeve (both rigid on StaffShoulder): it may
    # only exist inside the sleeve, else its plain skin shows beside the bust (review round 1)
    if "UpperArmR" in raw and "SleeveR" in raw:
        inside = cv2.erode((raw["SleeveR"][..., 3] > 128).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        inside |= cv2.dilate((raw["ForearmR"][..., 3] > 128).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
        raw["UpperArmR"][~inside, 3] = 0
    cover = np.zeros((H, W), bool)
    for i in range(len(ORDER) - 1, -1, -1):
        n = ORDER[i]
        img = raw[n].copy()
        if n in FILL_HOLES:
            img = fill_holes(img)
        img = antialias(img, n)
        if n not in NO_HIDDEN_FEATHER:
            img = hidden_edge_feather(img, cover, HIDDEN_PX.get(n, HIDDEN_DEFAULT))
        for part, joint, other, fade in ENDS:
            if part == n and not fade:
                img = straighten_end(img, joint, other)
        for part, joint, other, fade in ENDS:
            if part == n and fade:
                img = fade_end(img, joint, other)
        img, removed = rest_clip(img, i)
        img = drop_islands(img, n)
        if report and removed:
            print(f"rest clip {n}: {removed} px")
        out[n] = img
        cover |= img[..., 3] > 200
    fixed = coverage_fill(out, raw)
    # label edges inside the figure are binary (owner map): soften them by ~1 px so a moving edge
    # does not read as a dashed stair-step line; the silhouette keeps the reference alpha
    for n in ORDER:
        a = out[n][..., 3].astype(np.float32)
        soft = cv2.GaussianBlur(a, (0, 0), EDGE_SIGMA)
        inside = REF_A & (cv2.erode(REF_A.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
        out[n][..., 3] = np.where(inside, soft, a).astype(np.uint8)
    if report:
        print("coverage fill:", fixed)
    return out


def post_weights(name, verts, wts, origin):
    if name == "SleeveL":
        wts = rl.pin_to_body(wts, verts, origin, poly_mask(TORSO_EDGE_POLY), "Chest", PIN_BAND, PIN_FADE)
    if name in ("SleeveL", "ShawlPanelL", "ShawlPanelR"):
        wts = rl.soften_attachment(wts, verts, origin, PANEL_ROOTS, "Chest", PANEL_SOFT)
    return wts


def export():
    layers = load_layers()
    F = fields()
    os.makedirs(OUT_PARTS, exist_ok=True)
    os.makedirs(os.path.join(UNITY_V12, "Art"), exist_ok=True)
    parts = []
    for name in ORDER:
        img, (ox, oy) = rl.crop_layer(layers[name])
        h, w = img.shape[:2]
        file = "v12-" + name + ".png"
        Image.fromarray(img, "RGBA").save(os.path.join(OUT_PARTS, file))
        shutil.copyfile(os.path.join(OUT_PARTS, file), os.path.join(UNITY_V12, "Art", file))
        # parts named like a bone get "Art" so every transform name stays unique in Unity
        entry = dict(name=name + "Art" if name in BONE_POS else name, file=file, width=int(w), height=int(h), order=SORT[name], ppu=PPU,
                     originX=int(ox), originY=int(oy))
        part = PART[name]
        if part in SKINNED:
            fname, allowed, cell = SKINNED[part]
            if name != part:
                cell = PIECE_CELL
            verts, tris, edges, wts = rl.grid_mesh(img[..., 3], (ox, oy), cell, F[fname], BONE_NAMES, allowed, SCALE)
            wts = post_weights(name, verts, wts, (ox, oy))
            used = sorted({b for vw in wts for b, _ in vw}, key=BONE_NAMES.index)
            tree, root = rl.bone_tree(used, BONES)
            index = {n: i for i, n in enumerate(tree)}
            sb = []
            for n in tree:
                bx, by = BONE_POS[n]
                if n == root:
                    sb.append(dict(name=n, parent=-1, x=float(bx - ox), y=float((oy + h) - by)))
                else:
                    px, py = BONE_POS[PARENT[n]]
                    sb.append(dict(name=n, parent=index[PARENT[n]], x=float(bx - px), y=float(py - by)))
            flat = []
            for vw in wts:
                for bn, wt in (vw + [(vw[0][0], 0.0)] * 4)[:4]:
                    flat += [index[bn], float(wt)]
            entry.update(bones=sb, vertices=[c for p in verts for c in (p[0], h - p[1])], indices=tris,
                         edges=[c for e in edges for c in e], weights=flat)
            anchor = root
        else:
            anchor = RIGID[part]
        ax, ay = BONE_POS[anchor]
        entry.update(anchor=anchor, pivotX=float((ax - ox) / w), pivotY=float(1 - (ay - oy) / h))
        parts.append(entry)
    flash_src = os.path.join(REFS, "3_parts", "v003", "parts", "v3-CastFlash.png")
    shutil.copyfile(flash_src, os.path.join(UNITY_V12, "Art", "v12-CastFlash.png"))
    rig = dict(refPpu=PPU, groundY=1508.0, originX=620.0,
               bones=[dict(name=n, parent=p or "", x=q[0], y=q[1]) for n, p, q in BONES], parts=parts)
    for d in (HERE, UNITY_V12):
        with open(os.path.join(d, "rig.json"), "w", encoding="utf-8") as f:
            json.dump(rig, f)
    return rig


def preview(path):
    """Rest composite of the layers next to the reference, plus the rig over it."""
    layers = load_layers()
    bg = lambda: Image.new("RGBA", (W, H), (20, 22, 36, 255))
    comp = bg()
    for n in ORDER:
        comp.alpha_composite(Image.fromarray(layers[n], "RGBA"))
    ref = bg(); ref.alpha_composite(Image.open(REFERENCE).convert("RGBA"))
    rigim = comp.copy(); d = ImageDraw.Draw(rigim)
    for n, p, q in BONES:
        if p:
            d.line([BONE_POS[p], q], fill=(255, 60, 60, 255), width=3)
        d.ellipse([q[0] - 5, q[1] - 5, q[0] + 5, q[1] + 5], fill=(80, 255, 80, 255))
    out = Image.new("RGBA", (W * 3, H))
    for i, im in enumerate((ref, comp, rigim)):
        out.paste(im, (W * i, 0))
    out.resize((W * 3 // 2, H // 2)).save(path)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "preview"
    if cmd == "extract":
        rig = export()
        for p in rig["parts"]:
            print(p["name"], p["width"], p["height"], len(p.get("vertices", [])) // 2, "verts",
                  [b["name"] for b in p.get("bones", [])] or p["anchor"])
    else:
        preview(sys.argv[2])
        print("preview written")
