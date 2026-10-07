"""Estelle v007: layered rig cut from the v001 full-body study.

The study (`references/2_art/estelle-fullbody-right.png`) already has the source design (shawl
draped over both arms, gloved hand gripping the staff) and ~8.5-head proportions. It is split
into layers in place (reference pixel space == sprite pixel space, 1 unit = 256 px):

  Body      one skinned mesh: back hair, torso, hanging shawl panels, dress, legs
  Head      skinned (neck + chest at the cut so the seam never opens)
  SleeveL/R shawl over each upper arm, skinned chest -> shoulder -> shawl panel root
  FreeArm   rigid glove + hand on the free elbow
  StaffArm  skinned forearm (elbow) + gripping hand (wrist)
  Staff     clean staff sprite on the wrist, drawn behind the gripping hand

Hidden pixels behind moving layers are inpainted in the Body; glove tops are extended under
the sleeves. All skinned layers sample ONE global weight field, so neighbouring layers agree
at their seams.

Usage: python rig_v7.py extract | preview <png>
"""
import json
import math
import os
import shutil
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
from rig_layers import make_flash  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
# Worked example copied into the skill. Point these at your files (environment variables):
#   RIG_REFERENCE  full-body reference PNG (Estelle: references/2_art/estelle-fullbody-right.png)
#   RIG_UNITY_ROOT Unity folder receiving rig.json + Art/ (e.g. <project>/Assets/EstelleV7)
#   RIG_OUT        working output folder for parts/, rig.json, anim.json
STUDY = os.environ.get("RIG_REFERENCE", os.path.join(HERE, "estelle-fullbody-right.png"))
UNITY_V4 = os.environ.get("RIG_UNITY_ROOT", os.path.join(HERE, "out", "unity"))
OUT = os.environ.get("RIG_OUT", os.path.join(HERE, "out"))
OUT_PARTS = os.path.join(OUT, "parts")
PPU = 256.0
W, H = 1024, 1536

# Staff sprite -> study similarity, measured with SIFT/RANSAC (v003).
STAFF_M = np.array([[0.733 * math.cos(math.radians(-0.49)), -0.733 * math.sin(math.radians(-0.49)), 424.08],
                    [0.733 * math.sin(math.radians(-0.49)), 0.733 * math.cos(math.radians(-0.49)), 4.19]])

# ------------------------------------------------------------------------ skeleton (study px)
BONES = [
    ("Root", None, (620, 1508)),
    ("Hips", "Root", (590, 640)),
    ("Spine", "Hips", (588, 520)),
    ("Chest", "Spine", (580, 380)),
    ("Neck", "Chest", (565, 290)),
    ("HairL1", "Neck", (420, 420)),
    ("HairL2", "HairL1", (360, 580)),
    ("HairL3", "HairL2", (300, 730)),
    ("HairR1", "Neck", (680, 400)),
    ("HairR2", "HairR1", (735, 540)),
    ("FreeShoulder", "Chest", (452, 385)),
    ("FreeElbow", "FreeShoulder", (392, 590)),
    ("ShawlL1", "Chest", (380, 640)),
    ("ShawlL2", "ShawlL1", (310, 880)),
    ("ShawlL3", "ShawlL2", (220, 1130)),
    ("StaffShoulder", "Chest", (672, 352)),
    ("StaffElbow", "StaffShoulder", (706, 520)),
    ("StaffWrist", "StaffElbow", (782, 462)),
    ("StaffTip", "StaffWrist", (801, 160)),
    ("ShawlR1", "Chest", (752, 570)),
    ("ShawlR2", "ShawlR1", (825, 810)),
    ("ShawlR3", "ShawlR2", (895, 1070)),
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
BONE_POS = {n: p for n, _, p in BONES}
PARENT = {n: q for n, q, _ in BONES}

# --------------------------------------------------------------------------- layer polygons
HEAD_CUT = [(350, 350), (430, 332), (470, 306), (515, 274), (545, 257), (575, 252), (605, 256),
            (632, 264), (662, 286), (730, 300)]
HEAD_POLY = HEAD_CUT + [(760, 300), (760, 0), (330, 0), (330, 350)]
SLEEVE_L_POLY = [(362, 390), (420, 376), (478, 388), (490, 450), (478, 540), (448, 600), (424, 616),
                 (360, 612), (316, 604), (296, 572), (316, 520), (342, 470), (352, 420)]
SLEEVE_R_POLY = [(652, 368), (690, 360), (722, 376), (738, 420), (738, 470), (726, 520), (716, 548),
                 (700, 566), (662, 566), (654, 520), (652, 440)]          # left edge = shawl edge, not the corset piping
FREE_ARM_POLY = [(352, 592), (368, 575), (412, 562), (430, 580), (420, 620), (394, 660), (362, 700),
                 (336, 730), (310, 762), (284, 792), (254, 820), (212, 820), (190, 804), (203, 782),
                 (236, 758), (266, 732), (290, 702), (316, 668), (336, 632)]
STAFF_FORE_POLY = [(698, 478), (745, 460), (768, 440), (792, 440), (795, 470), (786, 490), (760, 508),
                   (730, 528), (712, 542), (698, 536)]
HAND_POLY = [(770, 346), (800, 348), (817, 362), (834, 384), (836, 416), (828, 447), (809, 471),
             (792, 482), (772, 474), (765, 440), (767, 400)]

STAFF_TOP_POLY = [(705, 0), (905, 0), (905, 330), (820, 345), (780, 345), (705, 300)]
STAFF_AXIS = [(800, 330), (796, 450), (793, 600), (784, 900), (776, 1102)]
STAFF_HALF = 8.5
STAFF_POMMEL_POLY = [(766, 1100), (786, 1100), (792, 1160), (808, 1195), (812, 1232), (800, 1266), (795, 1300),
                     (802, 1330), (798, 1362), (791, 1402), (773, 1462), (764, 1462), (756, 1402), (748, 1362),
                     (745, 1330), (750, 1300), (744, 1266), (737, 1232), (742, 1195), (758, 1160)]

# Weight regions (only steer skinning; layer pixels come from the masks above).
TORSO_POLY = [(430, 300), (705, 300), (712, 420), (694, 560), (655, 655), (528, 655), (480, 560), (440, 420)]
HAIR_L_POLY = [(240, 330), (475, 320), (470, 420), (420, 470), (335, 560), (300, 650), (335, 790), (240, 790), (220, 600)]
HAIR_R_POLY = [(600, 262), (725, 282), (795, 420), (795, 650), (738, 650), (700, 525), (650, 380)]
PANEL_L_POLY = [(286, 590), (472, 600), (472, 720), (432, 900), (392, 1150), (344, 1440), (0, 1440),
                (0, 1300), (118, 1050), (226, 820), (266, 680)]
PANEL_R_POLY = [(700, 545), (792, 528), (872, 700), (942, 950), (1024, 1250), (1024, 1440), (772, 1440),
                (760, 1200), (730, 950), (706, 720)]
LEG_POLYS = [
    [(583, 700), (702, 700), (702, 900), (692, 1000), (675, 1150), (662, 1262), (690, 1330), (732, 1470),
     (738, 1514), (690, 1518), (632, 1502), (626, 1506), (602, 1506), (600, 1420), (597, 1330),
     (588, 1262), (574, 1150), (574, 1000), (578, 900)],
    [(470, 1100), (562, 1100), (582, 1300), (592, 1462), (522, 1472), (468, 1440)],
]

# Chains for weighting: list of (bone, anchor point). Bone k owns the segment k..k+1.
CHAINS = {
    # v005: the Chest anchor sits below the underbust (y 455) so the whole bust belongs to Chest;
    # the spine bends at the waist, not through the bust.
    "torso": [("Hips", (590, 660)), ("Spine", (588, 530)), ("Chest", (585, 482))],
    "head": [("Neck", (565, 250))],
    "hairL": [("Neck", (450, 320)), ("HairL1", (420, 420)), ("HairL2", (360, 580)), ("HairL3", (300, 730))],
    "hairR": [("Neck", (640, 290)), ("HairR1", (680, 400)), ("HairR2", (735, 540))],
    "sleeveL": [("Chest", (455, 340)), ("FreeShoulder", (440, 430)), ("ShawlL1", (385, 620))],
    "sleeveR": [("Chest", (665, 335)), ("StaffShoulder", (692, 420)), ("ShawlR1", (748, 570))],
    "panelL": [("ShawlL1", (385, 620)), ("ShawlL2", (310, 880)), ("ShawlL3", (220, 1130))],
    "panelR": [("ShawlR1", (748, 570)), ("ShawlR2", (825, 810)), ("ShawlR3", (895, 1070))],
    "dressL": [("Hips", (560, 660)), ("DressL1", (485, 770)), ("DressL2", (440, 1010)), ("DressL3", (400, 1250))],
    "dressC": [("Hips", (590, 660)), ("DressC1", (600, 770)), ("DressC2", (612, 1010)), ("DressC3", (622, 1250))],
    "dressR": [("Hips", (620, 660)), ("DressR1", (690, 770)), ("DressR2", (718, 1010)), ("DressR3", (738, 1250))],
    "legs": [("Root", (620, 1508))],
    "freeArm": [("FreeElbow", (392, 590))],
    "staffFore": [("StaffElbow", (706, 520))],
    "hand": [("StaffWrist", (782, 462))],
}
BLEND = 0.35
WEIGHT_SIGMA = 14      # px, smooths region borders
WEIGHT_SCALE = 2       # weight maps are computed at 1/2 resolution


def poly_mask(poly, shape=(H, W)):
    m = Image.new("L", (shape[1], shape[0]), 0)
    ImageDraw.Draw(m).polygon([tuple(p) for p in poly], fill=255)
    return np.asarray(m) > 0


def hsv(img):
    return cv2.cvtColor(np.ascontiguousarray(img[..., :3]), cv2.COLOR_RGB2HSV_FULL).astype(float)


def keep_largest(mask):
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8))
    if n <= 1:
        return mask
    return lab == 1 + int(np.argmax(st[1:, 4]))


def build_masks(study):
    rgba = np.asarray(study)
    alpha = rgba[..., 3] > 8
    hv = hsv(rgba)
    hue, sat, val = hv[..., 0] * 360 / 255, hv[..., 1] / 255, hv[..., 2] / 255
    r, g, b = [rgba[..., i].astype(int) for i in range(3)]
    navy = (b > r + 12) & (val < 0.62)
    glove = (sat < 0.22) & (val > 0.5)

    # The painted staff is cut from the study: armillary top, a strip along the shaft, and the
    # pommel. Navy shawl, white chiffon and hair inside those shapes stay in the body.
    white = (sat < 0.13) & (val > 0.72)
    top = poly_mask(STAFF_TOP_POLY) & alpha
    shaft = np.zeros((H, W), bool)
    for (x0, y0), (x1, y1) in zip(STAFF_AXIS, STAFF_AXIS[1:]):
        for yy in range(y0, y1):
            cx = x0 + (x1 - x0) * (yy - y0) / (y1 - y0)
            shaft[yy, int(round(cx - STAFF_HALF)):int(round(cx + STAFF_HALF)) + 1] = True
    shaft &= alpha & ~navy & ~white
    pommel = poly_mask(STAFF_POMMEL_POLY) & alpha & ~navy & ~white
    staff = top | shaft | pommel
    staff = cv2.morphologyEx(staff.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)) > 0
    staff &= alpha

    hand = poly_mask(HAND_POLY) & alpha

    def arm(poly):
        m = poly_mask(poly) & alpha & ~navy & ~hand
        m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8)) > 0
        m = keep_largest(m & poly_mask(poly))
        # include the dark ink outline around the glove
        return (cv2.dilate(m.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & poly_mask(poly) & alpha & ~hand

    staff_fore = arm(STAFF_FORE_POLY)
    free_arm = arm(FREE_ARM_POLY)

    def sleeve(poly):
        m = poly_mask(poly) & alpha & (navy | ((sat > 0.35) & (val > 0.45) & (hue < 60)) | (val < 0.3))
        m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8)) > 0
        m = keep_largest(m & poly_mask(poly))
        return (cv2.dilate(m.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) & poly_mask(poly) & alpha

    sleeve_l = sleeve(SLEEVE_L_POLY) & ~free_arm
    sleeve_r = sleeve(SLEEVE_R_POLY) & ~staff_fore
    head = poly_mask(HEAD_POLY) & alpha & ~staff
    staff_only = staff & ~hand
    body = alpha & ~(head | sleeve_l | sleeve_r | free_arm | staff_fore | hand | staff_only)
    return dict(alpha=alpha, staff=staff, hand=hand, staff_fore=staff_fore, free_arm=free_arm,
                sleeve_l=sleeve_l, sleeve_r=sleeve_r, head=head, body=body, navy=navy, hue=hue, sat=sat, val=val)


def bleed(rgba, keep, extend):
    """Fill `extend` pixels with the nearest `keep` pixel colour (opaque)."""
    out = rgba.copy()
    out[..., 3] = np.where(keep, rgba[..., 3], 0)
    if extend.any():
        dist, idx = cv2.distanceTransformWithLabels((~keep).astype(np.uint8), cv2.DIST_L2, 5,
                                                    labelType=cv2.DIST_LABEL_PIXEL)
        ys, xs = np.nonzero(keep)
        lab_to_pix = np.zeros((idx.max() + 1, 2), int)
        lab_to_pix[idx[keep]] = np.stack([ys, xs], 1)
        ey, ex = np.nonzero(extend & ~keep)
        src = lab_to_pix[idx[ey, ex]]
        out[ey, ex, :3] = rgba[src[:, 0], src[:, 1], :3]
        out[ey, ex, 3] = 255
    return out


def inpaint_holes(rgba, keep, holes):
    """Body layer: remove `holes` and inpaint colour and coverage there from the surrounding body."""
    rgb = np.ascontiguousarray(rgba[..., :3])
    a = np.where(keep, rgba[..., 3], 0).astype(np.uint8)
    m = (holes & ~keep).astype(np.uint8) * 255
    rgb2 = cv2.inpaint(rgb, m, 7, cv2.INPAINT_TELEA)
    a2 = cv2.inpaint(a, m, 7, cv2.INPAINT_TELEA)
    a2 = cv2.GaussianBlur(a2, (0, 0), 2.5)
    a2 = np.clip((a2.astype(float) - 128) * 4 + 128, 0, 255).astype(np.uint8)      # smooth, anti-aliased edge
    out = np.dstack([rgb2, np.where(m > 0, a2, a)]).astype(np.uint8)
    return out


# Under the staff-side sleeve and forearm the body needs structure, not a blur: the corset
# continues to its side seam, and behind it hangs more of the same navy shawl.
TORSO_SIDE_POLY = [(630, 372), (690, 392), (688, 428), (672, 468), (657, 515), (650, 566), (630, 566)]
STAFF_SIDE_FILL = [(640, 366), (704, 358), (736, 412), (748, 470), (752, 540), (760, 575), (648, 590)]
SHAWL_DONOR_OFFSET = (120, 300)


def refill_staff_side(study, body_rgba, body, M):
    hole = (M["sleeve_r"] | M["staff_fore"] | M["hand"]) & ~body
    region = poly_mask(STAFF_SIDE_FILL)
    fill = hole & region
    fill = (cv2.GaussianBlur(fill.astype(np.float32), (0, 0), 3) > 0.5) & dil_(hole, 1) & region
    side = fill & poly_mask(TORSO_SIDE_POLY)
    shawl = fill & ~side
    out = body_rgba.copy()
    # Corset side: extend each row from the nearest visible corset pixel on its left.
    corset = body & poly_mask(TORSO_POLY) & ~M["navy"] & (M["val"] > 0.5)
    for y in np.unique(np.nonzero(side)[0]):
        xs = np.nonzero(side[y])[0]
        src = np.nonzero(corset[y, :xs.min()])[0]
        if len(src):
            edge_x = src.max() - 3
            width = xs.max() - edge_x + 1
            plain = corset[y] & (M["sat"][y] < 0.2) & (M["val"][y] > 0.7)     # white fabric only
            row_white = study[y, plain][:, :3]
            tone = np.median(row_white, 0) if len(row_white) else study[y, edge_x, :3]
            for x in xs:                                  # mirror the neighbouring fabric outward
                mx = max(edge_x - (x - edge_x), 0)
                out[y, x, :3] = study[y, mx, :3] if plain[mx] else tone
    # Shawl behind the arm: navy base from the sleeve with soft diagonal folds.
    navy_px = study[M["sleeve_r"] & M["navy"]][:, :3].astype(float)
    base = np.median(navy_px, 0)
    ys, xs = np.nonzero(shawl)
    ang = math.radians(62)                                    # folds run down and outwards
    u = (xs * math.cos(ang) + ys * math.sin(ang)) / 60.0
    v = (-xs * math.sin(ang) + ys * math.cos(ang)) / 7.5
    shade = 1 + 0.16 * np.sin(v + 0.8 * np.sin(u * 2.1)) + 0.06 * np.sin(v * 2.7 + 1.3)
    out[ys, xs, :3] = np.clip(base[None, :] * shade[:, None], 0, 255).astype(np.uint8)
    out[fill, 3] = 255
    # Ink line along the corset's side seam.
    seam = dil_(side, 1) & ~side & shawl
    out[seam, :3] = (out[seam, :3] * 0.45).astype(np.uint8)
    # Outside the plausible silhouette the hole is background.
    out[hole & ~region & ~dil_(body, 2), 3] = 0
    blur = cv2.GaussianBlur(out, (3, 3), 0)
    edge = dil_(fill, 2) & ~erode_(fill, 2)
    out[edge] = blur[edge]
    return out


def mirror_fill_strip(study, body_rgba, body, strip):
    """Thin removed strips (the staff shaft) are refilled per row by mirroring the neighbouring
    real pixels from both sides, which keeps cloth texture, folds and gold trims continuous."""
    out = body_rgba.copy()
    hole = strip & ~body
    for y in np.unique(np.nonzero(hole)[0]):
        row = hole[y]
        xs = np.nonzero(row)[0]
        runs = np.split(xs, np.nonzero(np.diff(xs) > 1)[0] + 1)
        for run in runs:
            x0, x1 = run[0], run[-1]
            n = x1 - x0 + 1
            left_ok = x0 - 1 >= 0 and body[y, x0 - 1]
            right_ok = x1 + 1 < W and body[y, x1 + 1]
            if not (left_ok and right_ok):
                continue                                # cloth edge: keep the smooth inpainted fill
            for i, x in enumerate(run):
                wl, wr = (n - i) / (n + 1), (i + 1) / (n + 1)   # weight toward the nearer side
                cl = study[y, max(x0 - 1 - i, 0)] if left_ok and body[y, max(x0 - 1 - i, 0)] else None
                cr = study[y, min(x1 + 1 + (n - 1 - i), W - 1)] if right_ok and body[y, min(x1 + 1 + (n - 1 - i), W - 1)] else None
                if cl is not None and cr is not None:
                    c = cl.astype(float) * wl + cr.astype(float) * wr
                    c[3] = 255 if (cl[3] > 128 or cr[3] > 128) else max(cl[3], cr[3])
                elif cl is not None or cr is not None:
                    c = (cl if cl is not None else cr).astype(float)
                else:                                   # mirror source left the body: use the edge pixel
                    c = study[y, x0 - 1 if left_ok else x1 + 1].astype(float)
                out[y, x] = np.clip(c, 0, 255).astype(np.uint8)
    return out


def dil_(m, r):
    if r <= 0:
        return m
    return cv2.dilate(m.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))) > 0


def erode_(m, r):
    return cv2.erode(m.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))) > 0


# v007: true outer contour of the staff-side bust, continuing under the shawl (study px).
BUST_SIDE_CONTOUR = [(662, 300), (684, 338), (694, 378), (697, 410), (694, 438), (684, 456), (670, 468),
                     (663, 500), (659, 535), (657, 566)]          # bust, then the corset side to the waist
BUST_SIDE_REGION = [(600, 300)] + BUST_SIDE_CONTOUR + [(600, 566)]
BUST_SKIN_Y = 394
BACK_REGION = [(640, 380), (760, 380), (760, 600), (640, 600)]
BACK_Y0 = 400                              # back-shawl layer starts behind the bust side


def paint_bust_side(study, body, M):
    """Repaint the bust side hidden under the staff sleeve: continue the visible skin/satin
    by mirroring each row's neighbouring texture, then ink the outer contour."""
    out = body.copy()
    region = poly_mask(BUST_SIDE_REGION) & M["sleeve_r"]
    region = dil(region, 1) & poly_mask(BUST_SIDE_REGION)
    visible = M["alpha"] & ~M["sleeve_r"] & ~M["navy"] & poly_mask(BUST_SIDE_REGION)
    for y in np.unique(np.nonzero(region)[0]):
        xs = np.nonzero(region[y])[0]
        src = np.nonzero(visible[y, :xs.min()])[0]
        if not len(src):
            continue
        edge = src.max() - 2
        for x in xs:
            mx = max(edge - (x - edge), 0)
            out[y, x, :3] = study[y, mx, :3] if visible[y, mx] else study[y, edge, :3]
        out[y, xs, 3] = 255
    # soften the repaint, then draw the contour line in the art's ink colour
    blur = cv2.GaussianBlur(out, (5, 5), 1.2)
    out[region] = blur[region]
    ink = Image.fromarray(np.zeros((H, W, 4), np.uint8), "RGBA")
    ImageDraw.Draw(ink).line(BUST_SIDE_CONTOUR, fill=(96, 74, 78, 235), width=2, joint="curve")
    ink = np.asarray(ink.filter(ImageFilter.GaussianBlur(0.6)))
    m = (ink[..., 3] > 0) & dil(region, 2)
    a = ink[m, 3:4] / 255.0
    out[m, :3] = (out[m, :3] * (1 - a) + ink[m, :3] * a).astype(np.uint8)
    # outside the contour the revealed area belongs to the back shawl layer
    outside = M["sleeve_r"] & ~poly_mask(BUST_SIDE_REGION) & poly_mask([(600, 290), (760, 290), (760, 566), (600, 566)])
    out[outside & ~M["body"], 3] = 0
    return out


# v007 sleeve split. The body piece is the band of the sleeve lying on the bust edge: within
# 4 px of the torso silhouette and above the underbust. Everything else covers the upper arm.
SLEEVE_BODY_Y_MAX = 465


def sleeve_body_band():
    band = dil(poly_mask(TORSO_EDGE_POLY), 4)
    band[SLEEVE_BODY_Y_MAX:] = False
    return band


def erode_(m, r):
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    return cv2.erode(m.astype(np.uint8), k) > 0


def dil(m, r):
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    return cv2.dilate(m.astype(np.uint8), k) > 0
UNDER_SHADE = 0.86                     # back of the shawl behind the lifted arm, lightly shaded
USE_LAMA_UNDER = False                # A/B in v007: LaMa drew dark hair-like streaks here; folds read better
UNDER_LAMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sleeve-under-lama.png")


def fill_under_sleeve(study, layer, under, keep):
    """Cloth continuing under the arm piece. Uses a precomputed LaMa fill when present
    (make_under_v7.py), otherwise procedural folds; darkened as the shaded underside."""
    out = layer.copy()
    if USE_LAMA_UNDER and os.path.exists(UNDER_LAMA):
        lama = np.asarray(Image.open(UNDER_LAMA).convert("RGB"))
        out[under, :3] = lama[under]
    else:
        navy = study[keep & (study[..., 2].astype(int) > study[..., 0].astype(int) + 12)][:, :3]
        procedural = procedural_fill(out.copy(), under, np.median(navy, 0))
        out[under, :3] = procedural[under, :3]
    out[under, :3] = (out[under, :3] * UNDER_SHADE).astype(np.uint8)
    out[under, 3] = 255
    return out


def procedural_fill(out, region, base_rgb, angle_deg=70, period_px=40, strength=0.16):
    ys, xs = np.nonzero(region)
    a = math.radians(angle_deg)
    u = (xs * math.cos(a) + ys * math.sin(a)) / 60.0
    v = (-xs * math.sin(a) + ys * math.cos(a)) / (period_px / (2 * math.pi))
    shade = 1 + strength * np.sin(v + 0.8 * np.sin(u * 2.1))
    out[ys, xs, :3] = np.clip(np.asarray(base_rgb, float)[None, :] * shade[:, None], 0, 255).astype(np.uint8)
    return out


def build_layers():
    study = Image.open(STUDY).convert("RGBA")
    rgba = np.asarray(study).copy()
    M = build_masks(study)
    k5 = np.ones((5, 5), np.uint8)

    def dil(m, r):
        return cv2.dilate(m.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))) > 0

    layers = {}
    front = M["head"] | M["sleeve_l"] | M["sleeve_r"] | M["free_arm"] | M["staff_fore"] | M["hand"] | M["staff"]
    body = M["body"].copy()
    n, lab, st, _ = cv2.connectedComponentsWithStats(body.astype(np.uint8))
    for i in range(1, n):
        if st[i, 4] < 300:                       # stray specks left around removed parts
            body[lab == i] = False
    body_rgba = inpaint_holes(rgba, body, front & dil(body, 60))
    body_rgba = refill_staff_side(rgba, body_rgba, body, M)
    body_rgba = mirror_fill_strip(rgba, body_rgba, body, M["staff"] & ~M["hand"] & ~M["staff_fore"])
    layers["Body"] = body_rgba
    layers["Head"] = bleed(rgba, M["head"], np.zeros_like(M["head"]))
    layers["SleeveL"] = bleed(rgba, M["sleeve_l"], np.zeros_like(M["head"]))
    # v007: the staff sleeve is split along its gold fold line. The arm piece (over the upper
    # arm) rotates rigidly with the shoulder; the body piece (bust edge and side) stays on the
    # body and continues under the arm piece as shaded inner cloth, shown when the arm lifts.
    # The whole staff sleeve lifts with the upper arm (rigid on the shoulder). What it uncovers:
    # the bust side (repainted in the Body layer, see paint_bust_side) and, outside the torso,
    # the shaded back of the shawl (the "SleeveR" layer below the arm piece).
    arm_piece = M["sleeve_r"]
    layers["SleeveRArm"] = bleed(rgba, arm_piece, np.zeros_like(arm_piece))
    # Above the arm the lifted sleeve reveals open background; below it the back of the shawl
    # continues down into the hanging panel, fading in from BACK_Y0.
    # share the painted contour with the Body repaint (overlap 2 px under it) so no gap opens
    layers["Body"] = paint_bust_side(rgba, layers["Body"], M)
    # Everything in the back region the Body layer leaves empty (sleeve, forearm, hand gaps)
    # plus the arm piece itself, outside the painted bust/corset contour.
    body_empty = layers["Body"][..., 3] < 128
    # the forearm counts only where it tucks into the sleeve (near the cuff), never its outer part
    tucked = M["staff_fore"] & dil(arm_piece, 8)
    # Convex hull of the sleeve (+ tucked forearm) below BACK_Y0: a smooth back-cloth shape with
    # no notches, clipped behind the painted bust/corset contour.
    src = (arm_piece | tucked).copy()
    src[:BACK_Y0] = False
    ys, xs = np.nonzero(src)
    hull = cv2.convexHull(np.stack([xs, ys], 1).astype(np.int32))
    hull_mask = np.zeros((H, W), np.uint8)
    cv2.fillPoly(hull_mask, [hull], 1)
    under = (hull_mask > 0) & poly_mask(BACK_REGION) & dil(M["alpha"], 2)   # never beyond the silhouette
    under[:BACK_Y0] = False
    under = cv2.morphologyEx(under.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)) > 0
    back = np.zeros_like(rgba)
    back = fill_under_sleeve(rgba, back, under, M["sleeve_r"])
    alpha = cv2.GaussianBlur(under.astype(np.float32), (0, 0), 1.6)            # soft silhouette
    ramp = np.clip((np.arange(H)[:, None] - BACK_Y0) / 24.0, 0, 1)
    alpha = alpha * ramp
    # fold texture so the back cloth is not a flat block
    yy, xx = np.nonzero(under)
    fold = 1 + 0.07 * np.sin((xx * 0.34 + yy * 0.94) / 5.5 + 0.8 * np.sin(yy / 23.0))
    back[yy, xx, :3] = np.clip(back[yy, xx, :3] * fold[:, None], 0, 255).astype(np.uint8)
    back[..., 3] = (np.clip(alpha * 1.6, 0, 1) * 255).astype(np.uint8) * (dil(under, 3))
    layers["SleeveR"] = back
    # Glove tops continue under their sleeves so elbow motion never reveals a cut edge.
    layers["FreeArm"] = bleed(rgba, M["free_arm"], dil(M["free_arm"], 26) & M["sleeve_l"])
    staff_arm = M["staff_fore"] | M["hand"]
    # v006: the hidden glove top only continues along the forearm axis (a strip toward the
    # shoulder); a round dilation poked out of the cuff as a grey block when the elbow bent.
    layers["StaffArm"] = bleed(rgba, staff_arm, dil(M["staff_fore"], 26) & M["sleeve_r"] & poly_mask(STAFF_GLOVE_EXT))
    layers["Staff"] = bleed(rgba, M["staff"] & ~M["hand"], np.zeros_like(M["head"]))
    return layers, M


ORDER = {"Body": 10, "FreeArm": 30, "SleeveL": 35, "StaffArm": 40, "SleeveR": 9, "SleeveRArm": 46, "Staff": 38, "Head": 60}
SKINNED = {"Body", "Head", "SleeveL", "SleeveR", "StaffArm"}
RIGID = {"FreeArm": "FreeElbow", "Staff": "StaffWrist", "SleeveRArm": "StaffShoulder"}


# ------------------------------------------------------------------------------ weight field
def chain_weights(pt, chain):
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
        if abs(s - j) < BLEND:
            t = (s - (j - BLEND)) / (2 * BLEND)
            t = t * t * (3 - 2 * t)
            w[chain[j - 1][0]] = w.get(chain[j - 1][0], 0) + 1 - t
            w[chain[j][0]] = w.get(chain[j][0], 0) + t
            return w
    k = min(int(math.floor(s)), n - 1)
    return {chain[k][0]: 1.0}


def region_labels(M, include_arms=True):
    """Per-pixel weighting region (string label index) at full resolution."""
    names = list(CHAINS)
    lab = np.full((H, W), names.index("dressC"), np.int16)
    x = np.arange(W)[None, :].repeat(H, 0)
    y = np.arange(H)[:, None].repeat(W, 1)
    lab[(x < 540)] = names.index("dressL")
    lab[(x > 655)] = names.index("dressR")
    lab[poly_mask(TORSO_POLY)] = names.index("torso")
    blonde = (M["hue"] > 25) & (M["hue"] < 60) & (M["sat"] > 0.1) & (M["sat"] < 0.5) & (M["val"] > 0.55)
    lab[poly_mask(PANEL_L_POLY)] = names.index("panelL")
    lab[poly_mask(PANEL_R_POLY)] = names.index("panelR")
    lab[poly_mask(HAIR_L_POLY) & (blonde | ~M["alpha"] | ~M["navy"])] = names.index("hairL")
    lab[poly_mask(HAIR_R_POLY) & (blonde | ~M["alpha"]) & ~poly_mask(TORSO_POLY)] = names.index("hairR")
    lab[poly_mask(SLEEVE_L_POLY)] = names.index("sleeveL")
    lab[poly_mask(SLEEVE_R_POLY)] = names.index("sleeveR")
    for lp in LEG_POLYS:
        lab[poly_mask(lp)] = names.index("legs")
    if include_arms:
        lab[M["free_arm"]] = names.index("freeArm")
        lab[M["staff_fore"]] = names.index("staffFore")
        lab[M["hand"]] = names.index("hand")
    lab[poly_mask(HEAD_POLY)] = names.index("head")
    return lab, names


def weight_field(M, include_arms=True):
    lab, names = region_labels(M, include_arms)
    s = WEIGHT_SCALE
    h, w = H // s, W // s
    labs = lab[::s, ::s]
    bones = [n for n, _, _ in BONES]
    field = np.zeros((len(bones), h, w), np.float32)
    ys, xs = np.mgrid[0:h, 0:w]
    for ci, cname in enumerate(names):
        sel = labs == ci
        if not sel.any():
            continue
        for yy, xx in zip(ys[sel], xs[sel]):
            for bn, wt in chain_weights((xx * s, yy * s), CHAINS[cname]).items():
                field[bones.index(bn), yy, xx] += wt
    sig = WEIGHT_SIGMA / s
    for i in range(len(bones)):
        if field[i].any():
            field[i] = cv2.GaussianBlur(field[i], (0, 0), sig)
    tot = field.sum(0, keepdims=True)
    field /= np.maximum(tot, 1e-6)
    return field, bones


def sample_weights(field, bones, x, y, allowed=None):
    s = WEIGHT_SCALE
    xi = min(max(int(round(x / s)), 0), field.shape[2] - 1)
    yi = min(max(int(round(y / s)), 0), field.shape[1] - 1)
    v = field[:, yi, xi].copy()
    if allowed is not None:
        mask = np.array([b in allowed for b in bones])
        if (v * mask).sum() > 1e-4:
            v = v * mask
        else:                                   # nothing allowed nearby: nearest allowed chain root
            v = mask.astype(float) * 0
            v[bones.index(sorted(allowed, key=lambda n: [x for x, _, _ in BONES].index(n))[0])] = 1
    top = np.argsort(-v)[:4]
    top = [i for i in top if v[i] > 0.02] or [int(np.argmax(v))]
    tot = sum(v[i] for i in top)
    return [(bones[i], float(v[i] / tot)) for i in top]


# ------------------------------------------------------------------------------ meshes/export
def crop(layer, pad=4):
    a = layer[..., 3] > 0
    ys, xs = np.nonzero(a)
    x0, y0 = max(0, xs.min() - pad), max(0, ys.min() - pad)
    x1, y1 = min(W, xs.max() + pad + 1), min(H, ys.max() + pad + 1)
    return layer[y0:y1, x0:x1], (x0, y0)


def grid_mesh(img_alpha, origin, cell, field, bones, allowed=None):
    a = img_alpha > 0
    h, w = a.shape
    nx, ny = int(math.ceil(w / cell)), int(math.ceil(h / cell))
    used = np.zeros((ny, nx), bool)
    for j in range(ny):
        for i in range(nx):
            used[j, i] = a[max(0, j * cell - 2):min(h, (j + 1) * cell + 2), max(0, i * cell - 2):min(w, (i + 1) * cell + 2)].any()
    vid, verts, tris, ecount = {}, [], [], {}

    def v(i, j):
        if (i, j) not in vid:
            vid[(i, j)] = len(verts)
            verts.append((float(min(i * cell, w)), float(min(j * cell, h))))
        return vid[(i, j)]

    for j in range(ny):
        for i in range(nx):
            if used[j, i]:
                q = (v(i, j), v(i + 1, j), v(i + 1, j + 1), v(i, j + 1))
                tris += [q[0], q[1], q[3], q[1], q[2], q[3]]
                for e in ((q[0], q[1]), (q[1], q[2]), (q[2], q[3]), (q[3], q[0])):
                    k = tuple(sorted(e))
                    ecount[k] = ecount.get(k, 0) + 1
    weights = [sample_weights(field, bones, origin[0] + px, origin[1] + py, allowed) for px, py in verts]
    edges = [list(k) for k, c in ecount.items() if c == 1]
    return verts, tris, edges, weights


def bone_tree(used):
    """Smallest bone subtree (parents first) containing `used` bones, rooted at their LCA."""
    def chain(n):
        out = []
        while n:
            out.append(n)
            n = PARENT[n]
        return out[::-1]
    paths = [chain(n) for n in used]
    lca = 0
    while all(len(p) > lca + 1 for p in paths) and len({p[lca + 1] for p in paths}) == 1:
        lca += 1
    root = paths[0][lca]
    keep = {root}
    for p in paths:
        keep.update(p[lca:])
    return [n for n, _, _ in BONES if n in keep], root


ALLOWED = {
    "Head": {"Neck", "Chest", "HairL1", "HairR1"},
    "SleeveL": {"Chest", "FreeShoulder", "ShawlL1"},
    "SleeveR": {"Chest", "ShawlR1"},                 # v007: the body piece never follows the arm
    "StaffArm": {"StaffElbow", "StaffWrist"},
    # v006: the body never follows the arm bones; only sleeves and arm layers do.
    "Body": {n for n, _, _ in BONES} - {"FreeShoulder", "FreeElbow", "StaffShoulder", "StaffElbow", "StaffWrist", "StaffTip"},
}
CELL = {"Body": 26, "Head": 18, "SleeveL": 14, "SleeveR": 14, "StaffArm": 12}


# v005: rigid bust and body-pinned sleeves.
# Bust (skin + corset cups, study px). Every Body/Head vertex inside follows Chest only.
BUST_POLY = [(505, 290), (655, 290), (684, 350), (694, 400), (692, 440), (676, 462), (520, 462), (500, 420)]
# Torso silhouette: sleeve pixels close to it stay on Chest (the shawl rests on the body);
# the part farther out follows the shoulder chain. PIN_BAND is the blend width in px.
TORSO_EDGE_POLY = [(520, 300), (640, 300), (672, 330), (690, 380), (692, 430), (682, 460), (668, 500), (660, 560),
                   (560, 560), (535, 500), (520, 450)]
PIN_BAND = 18.0
PIN_HANG_Y0, PIN_HANG_Y1 = 430.0, 470.0       # pin fades out toward the underbust
_TORSO_DIST = None


def torso_distance():
    global _TORSO_DIST
    if _TORSO_DIST is None:
        inside = poly_mask(TORSO_EDGE_POLY)
        _TORSO_DIST = cv2.distanceTransform((~inside).astype(np.uint8), cv2.DIST_L2, 5)
    return _TORSO_DIST


def pin_weights(name, verts, wts, origin, h):
    """Post-process sampled weights: rigid bust for Body/Head, body-pinned inner sleeves."""
    ox, oy = origin
    bust = poly_mask(BUST_POLY)
    dist = torso_distance()
    out = []
    for (px, py), vw in zip(verts, wts):
        x, y = int(round(min(max(ox + px, 0), W - 1))), int(round(min(max(oy + py, 0), H - 1)))
        if name in ("Body", "Head") and bust[y, x]:
            vw = [("Chest", 1.0)]
        elif name in ("SleeveL", "SleeveR"):
            t = min(max(dist[y, x] / PIN_BAND, 0.0), 1.0)
            t = t * t * (3 - 2 * t)                        # 0 on the body edge -> 1 a band away
            limb = [(b, w) for b, w in vw if b != "Chest"]
            tot = sum(w for _, w in limb)
            chest = sum(w for b, w in vw if b == "Chest")
            if tot > 0:
                keep_chest = chest + (1 - chest) * (1 - t)
                # Only the band lying on the bust edge (above the underbust) rests on the body;
                # below it the sleeve follows the arm fully, so nothing stretches.
                u = min(max((oy + py - PIN_HANG_Y0) / (PIN_HANG_Y1 - PIN_HANG_Y0), 0.0), 1.0)
                keep_chest = keep_chest * (1 - u * u * (3 - 2 * u))
                vw = [("Chest", float(keep_chest))] + [(b, float(w / tot * (1 - keep_chest))) for b, w in limb]
                vw = sorted([v for v in vw if v[1] > 0.02], key=lambda v: -v[1])[:4]
                s_ = sum(w for _, w in vw)
                vw = [(b, float(w / s_)) for b, w in vw]
        out.append(vw)
    return out


# v006: soft attachment of the hanging shawl panels. Near where a panel hangs from the body its
# root bone hands its weight to Chest, fading over PANEL_SOFT px, so the gravity swing spreads
# down the panel instead of shearing a narrow seam next to the torso.
STAFF_GLOVE_EXT = [(723, 526), (705, 502), (665, 532), (683, 556)]    # elbow -> shoulder strip, 30 px wide
PANEL_ROOTS = {"ShawlR1": 545.0, "ShawlL1": 600.0}      # bone -> attachment y (study px)
PANEL_SOFT = 170.0


def soften_panels(verts, wts, origin):
    ox, oy = origin
    out = []
    for (px, py), vw in zip(verts, wts):
        y = oy + py
        d = dict(vw)
        for root, y0 in PANEL_ROOTS.items():
            if d.get(root, 0) > 0:
                f = min(max((y - y0) / PANEL_SOFT, 0.0), 1.0)
                f = f * f * (3 - 2 * f)                 # 0 at the attachment -> 1 lower down
                moved = d[root] * (1 - f)
                d[root] -= moved
                d["Chest"] = d.get("Chest", 0.0) + moved
        vw = sorted([(b, float(w)) for b, w in d.items() if w > 0.02], key=lambda v: -v[1])[:4]
        s_ = sum(w for _, w in vw)
        out.append([(b, w / s_) for b, w in vw])
    return out


def export():
    layers, M = build_layers()
    field, bones = weight_field(M, True)
    body_field, _ = weight_field(M, False)    # the body under the arms keeps its own cloth weights
    os.makedirs(OUT_PARTS, exist_ok=True)
    os.makedirs(os.path.join(UNITY_V4, "Art"), exist_ok=True)
    parts = []
    for name, layer in layers.items():
        img, (ox, oy) = crop(layer)
        h, w = img.shape[:2]
        file = "v7-" + name + ".png"
        Image.fromarray(img, "RGBA").save(os.path.join(OUT_PARTS, file))
        shutil.copyfile(os.path.join(OUT_PARTS, file), os.path.join(UNITY_V4, "Art", file))
        entry = dict(name=name, file=file, width=int(w), height=int(h), order=ORDER[name], ppu=PPU, originX=int(ox), originY=int(oy))
        if name in SKINNED:
            verts, tris, edges, wts = grid_mesh(img[..., 3], (ox, oy), CELL[name],
                                                body_field if name == "Body" else field, bones, ALLOWED[name])
            wts = pin_weights(name, verts, wts, (ox, oy), h)
            if name in ("Body", "SleeveL", "SleeveR"):
                wts = soften_panels(verts, wts, (ox, oy))
            used = sorted({b for vw in wts for b, _ in vw}, key=lambda n: [x for x, _, _ in BONES].index(n))
            tree, root = bone_tree(used)
            index = {n: i for i, n in enumerate(tree)}
            sb = []
            for n in tree:
                bx, by = BONE_POS[n]
                sx, sy = float(bx - ox), float((oy + h) - by)          # sprite px, y up
                par = PARENT[n] if n != root else None
                if par is None:
                    sb.append(dict(name=n, parent=-1, x=sx, y=sy))
                else:
                    px, py = BONE_POS[par]
                    sb.append(dict(name=n, parent=index[par], x=bx - px, y=py - by))
            anchor = root
            entry.update(bones=sb, vertices=[c for p in verts for c in (p[0], h - p[1])], indices=tris,
                         edges=[c for e in edges for c in e])
            flat = []
            for vw in wts:
                vw = (vw + [(vw[0][0], 0.0)] * 4)[:4]
                for bn, wt in vw:
                    flat += [index[bn], wt]
            entry["weights"] = flat
        else:
            anchor = RIGID[name]
        ax, ay = BONE_POS[anchor]
        entry["anchor"] = anchor
        entry["pivotX"] = float((ax - ox) / w)
        entry["pivotY"] = float(1 - (ay - oy) / h)
        parts.append(entry)
    make_flash(os.path.join(UNITY_V4, "Art", "v7-CastFlash.png"))
    rig = dict(refPpu=PPU, groundY=1508.0, originX=620.0,
               bones=[dict(name=n, parent=p or "", x=q[0], y=q[1]) for n, p, q in BONES], parts=parts)
    with open(os.path.join(OUT, "rig.json"), "w", encoding="utf-8") as f:
        json.dump(rig, f)
    shutil.copyfile(os.path.join(OUT, "rig.json"), os.path.join(UNITY_V4, "rig.json"))
    return rig, layers, M, field, bones


def preview(path):
    layers, M = build_layers()
    names = sorted(layers, key=lambda n: ORDER[n])
    bg = lambda: Image.new("RGBA", (W, H), (20, 22, 36, 255))
    comp = bg()
    for n in names:
        comp.alpha_composite(Image.fromarray(layers[n], "RGBA"))
    study = bg(); study.alpha_composite(Image.open(STUDY).convert("RGBA"))
    body = bg(); body.alpha_composite(Image.fromarray(layers["Body"], "RGBA"))
    tint = np.zeros((H, W, 4), np.uint8)
    colors = {"head": (255, 80, 80), "sleeve_l": (80, 255, 80), "sleeve_r": (80, 255, 80), "free_arm": (80, 160, 255),
              "staff_fore": (80, 160, 255), "hand": (255, 220, 0), "staff": (255, 0, 255)}
    for k, c in colors.items():
        tint[M[k]] = c + (150,)
    seg = bg(); seg.alpha_composite(Image.open(STUDY).convert("RGBA")); seg.alpha_composite(Image.fromarray(tint, "RGBA"))
    out = Image.new("RGBA", (W * 4, H))
    for i, im in enumerate((study, seg, body, comp)):
        out.paste(im, (W * i, 0))
    out.resize((W * 2, H // 2)).save(path)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "preview"
    if cmd == "extract":
        rig = export()[0]
        for p in rig["parts"]:
            print(p["name"], p["width"], p["height"], len(p.get("vertices", [])) // 2, "verts",
                  [b["name"] for b in p.get("bones", [])])
    else:
        preview(sys.argv[2])
        print("preview written")
