"""Cut the painted extended strike arm into bone pieces and place them in rest space.

Usage: python armext_parts.py
armext/ARMEXT-c.png is painted at the thrust pose (armext/pose.json, canvas crop x0). It is split at
the posed elbow and wrist (with overlap) into ArmExtUpper (StaffShoulder), ArmExtFore (StaffElbow) and
ArmExtHand (StaffWrist); each piece is moved back by the inverse of its bone's rest->thrust transform, so
the rig shows it exactly as painted at the thrust pose. Writes layers_ext/<piece>.png (1024x1536).
"""
import json, os
import cv2, numpy as np
from PIL import Image
import pose_render as pr

HERE = os.path.dirname(os.path.abspath(__file__))
P = json.load(open(os.path.join(HERE, "armext", "pose.json")))
X0 = P["crop_x0"]
art = np.asarray(Image.open(os.path.join(HERE, "armext", "ARMEXT-c.png")).convert("RGBA").resize((1024, 1536), Image.LANCZOS))
CAN = P["canvas"]
posed = np.zeros((CAN, CAN, 4), np.uint8); posed[:, X0:X0 + 1024] = art
S, E, Wr = (np.array(P[k]) for k in ("shoulder", "elbow", "wrist"))
OV = 18.0
ys, xs = np.mgrid[0:CAN, 0:CAN].astype(np.float32)
def along(a, b):
    d = (b - a) / np.linalg.norm(b - a); return (xs - a[0]) * d[0] + (ys - a[1]) * d[1]
t_el = along(E, Wr)        # 0 at the elbow, > 0 toward the wrist
t_wr = along(Wr, Wr + (Wr - E))
pieces = {"ArmExtUpper": ("StaffShoulder", t_el < OV), "ArmExtFore": ("StaffElbow", (t_el > -OV) & (t_wr < OV)),
          "ArmExtHand": ("StaffWrist", t_wr > -OV)}
r = pr.Rig(rig_path=os.path.join(HERE, "armext", "rig-v013.json"), anim_path=os.path.join(HERE, "armext", "anim-pose.json"),
           parts_dir=os.path.join(HERE, "..", "v013", "parts"))
ci = [c["name"] for c in r.anim["clips"]].index("EstelleAttackV13")
rest, cur = r.transforms(r.pose(ci, 0.48))
os.makedirs(os.path.join(HERE, "layers_ext"), exist_ok=True)
H, W = 1536, 1024
ry, rx = np.mgrid[0:H, 0:W].astype(np.float64)
for name, (bone, sel) in pieces.items():
    img = posed.copy(); img[~sel, 3] = 0
    # soft seam in the overlap so the pieces blend where they meet
    P0, a0 = rest[bone]; P1, a1 = cur[bone]
    R = pr.rot(a1 - a0)
    up = np.stack([rx, pr.H_REF - ry], -1)                      # rest px, y up
    moved = P1 + (up - P0) @ R.T                                   # where this rest pixel is at the thrust pose
    mx = moved[..., 0].astype(np.float32); my = (pr.H_REF - moved[..., 1]).astype(np.float32)
    out = cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    Image.fromarray(out).save(os.path.join(HERE, "layers_ext", f"{name}.png"))
    print(name, bone, "px", int((out[..., 3] > 128).sum()), "of", int((img[..., 3] > 128).sum()))
