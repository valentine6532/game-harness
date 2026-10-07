"""Extended staff arm (v014, user: "the arm should reach further"): guide images for the generator.

Usage: python arm_ext_guide.py
At the thrust pose POSE the rig's own arm pieces separate (the sleeve leaves the shoulder, the hidden
upper arm is missing), so a new arm is painted in that pose and swapped in during the strike.
Writes armext/pose.json, armext/context.png (posed body without the staff arm, staff kept),
armext/template.png (grey mask: posed arm pieces + a bridge to the shoulder), canvas 1536x1536.
"""
import json, os
import cv2, numpy as np
from PIL import Image
import anim_v14 as A
import pose_render as pr

POSE = dict(shoulder=88.0, elbow=-150.0, staff=-75.0)
ARM = ["SleeveR", "UpperArmR", "ForearmR", "HandR_back", "HandR_front"]
CAN = 1536
os.makedirs("armext", exist_ok=True)
A.SHOULDER_MAX = 180.0
A.ATTACK_KEYS = [(0.00, None, {}), (0.48, A.ease_out, A.attack_pose((-2.4, -4.0, -7.5), POSE["shoulder"], POSE["elbow"], POSE["staff"], -10, -5,
                 {("Neck", "rot"): 4.5})), (1.00, A.ease_in_out, {})]
clip = A.attack_clip()
anim = json.load(open("anim.json"))
ci = [c["name"] for c in anim["clips"]].index(clip["name"]); anim["clips"][ci] = clip
json.dump(anim, open("armext/anim-pose.json", "w"))
r = pr.Rig(anim_path="armext/anim-pose.json")
box = (0, 0, CAN, CAN)
names = [p["name"] for p in r.parts]
orig = dict(r.img)
def render_only(keep, bg=(0, 0, 0)):
    for n in names:
        r.img[n] = orig[n] if n in keep else np.zeros_like(orig[n])
    return np.asarray(pr.render(r, ci, 0.48, box=box, scale=1.0, bg=bg, flash=False))
full_ids = [n for n in names if n not in ARM]
ctx = render_only(set(full_ids), bg=(0, 177, 64))
Image.fromarray(ctx).save("armext/context.png")
# arm silhouette: render each arm piece white on black
masks = {}
for n in ARM:
    for m in names:
        im = orig[m].copy() if m == n else np.zeros_like(orig[m])
        if m == n:
            im[..., :3] = 255
        r.img[m] = im
    masks[n] = np.asarray(pr.render(r, ci, 0.48, box=box, scale=1.0, bg=(0, 0, 0), flash=False))[..., 0] > 127
pose = r.pose(ci, 0.48); rest, cur = r.transforms(pose)
P = lambda b: np.array([cur[b][0][0], pr.H_REF - cur[b][0][1]])
sh, el, wr = P("StaffShoulder"), P("StaffElbow"), P("StaffWrist")
d = (wr - el) / np.linalg.norm(wr - el)
grip = wr + d * 40                                   # the fist sits past the wrist on the staff
tmpl = np.zeros((CAN, CAN), np.uint8)
def capsule(a, b, w):
    cv2.line(tmpl, tuple(int(v) for v in a), tuple(int(v) for v in b), 1, int(w))
    cv2.circle(tmpl, tuple(int(v) for v in a), int(w // 2), 1, -1); cv2.circle(tmpl, tuple(int(v) for v in b), int(w // 2), 1, -1)
capsule(sh, el, 84)                                  # upper arm wrapped in the bunched shawl sleeve
capsule(el, wr, 44)                                  # gloved forearm
cv2.ellipse(tmpl, tuple(int(v) for v in grip), (38, 30), float(np.degrees(np.arctan2(d[1], d[0]))), 0, 360, 1, -1)   # fist
u = (el - sh) / np.linalg.norm(el - sh); nrm = np.array([-u[1], u[0]]) if u[0] * 0 + (-u[1]) * 0 + u[0] >= 0 else np.array([u[1], -u[0]])
down = nrm if nrm[1] > 0 else -nrm                   # the side of the arm that faces the floor
drape = np.array([sh + down * 30, sh + (el - sh) * 0.85 + down * 40, sh + (el - sh) * 0.55 + down * 85, sh + down * 95])
cv2.fillPoly(tmpl, [drape.astype(np.int32)], 1)      # the sleeve fabric hanging under the raised arm
tmpl = tmpl > 0
shx, shy = sh
t = np.zeros((CAN, CAN, 4), np.uint8); t[tmpl] = (200, 200, 200, 255)
Image.fromarray(t).save("armext/template.png")
json.dump(dict(pose=POSE, shoulder=sh.tolist(), elbow=el.tolist(), wrist=wr.tolist(), grip=grip.tolist(), canvas=CAN), open("armext/pose.json", "w"), indent=1)
prev = ctx.copy(); prev[tmpl] = (prev[tmpl] * 0.3 + np.array([255, 60, 60]) * 0.7).astype(np.uint8)
Image.fromarray(prev).save("armext/preview.png")
print("template px", int(tmpl.sum()), "shoulder", round(shx), round(shy))
