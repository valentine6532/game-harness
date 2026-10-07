"""Check whether a Mixamo clip FBX really has a T-pose rest (process_character.py --mixamo assumes it does).

Usage: blender -b --factory-startup -P mixamo_rest_check.py -- <clip.fbx> [<clip.fbx> ...] [--json out.json]

Imports each clip the way process_character.py does (use_anim, ignore_leaf_bones) and measures the REST pose
(data.bones, what the retarget uses as "Mixamo rest") and the first animation frame:
  arm_drop   upper arm below horizontal (T-pose ~0, A-pose ~35-45)
  elbow      bend between upper arm and forearm (T-pose ~0)
  spine_fwd  Hips->Neck lean toward the facing direction -Y (+ forward, - back; T-pose ~0)
  knee       bend between thigh and shin (T-pose ~0)
A rest that matches the first frame instead of a T-pose means the file stores an animation frame as rest,
and every retarget that takes this rest as T-pose is offset (World of Oldcraft: 25-30 deg lean back).
"""
import json
import math
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
out_json = None
if '--json' in argv:
    i = argv.index('--json')
    out_json = argv[i + 1]
    argv = argv[:i] + argv[i + 2:]


def angle(a, b):
    return math.degrees(a.angle(b)) if a.length and b.length else float('nan')


def measure(head):
    """head(name) -> world position of that bone's head."""
    r = {}
    for side in ('Left', 'Right'):
        up = head(side + 'ForeArm') - head(side + 'Arm')
        fore = head(side + 'Hand') - head(side + 'ForeArm')
        r[side[0] + '_arm_drop'] = math.degrees(math.asin(max(-1, min(1, -up.normalized().z))))
        r[side[0] + '_elbow'] = angle(up, fore)
        thigh = head(side + 'Leg') - head(side + 'UpLeg')
        shin = head(side + 'Foot') - head(side + 'Leg')
        r[side[0] + '_knee'] = angle(thigh, shin)
    spine = head('Neck') - head('Hips')
    r['spine_fwd'] = math.degrees(math.atan2(-spine.y, spine.z))
    return {k: round(v, 1) for k, v in r.items()}


results = []
for path in argv:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path, use_anim=True, ignore_leaf_bones=True)
    arm = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
    prefix = next(b.name.split(':')[0] + ':' for b in arm.data.bones if ':' in b.name)
    mw = arm.matrix_world
    rest = measure(lambda n: mw @ arm.data.bones[prefix + n].head_local)
    act = arm.animation_data.action if arm.animation_data else None
    f0 = int(act.frame_range[0]) if act else bpy.context.scene.frame_start
    bpy.context.scene.frame_set(f0)
    first = measure(lambda n: mw @ arm.pose.bones[prefix + n].head)
    diff = max(abs(rest[k] - first[k]) for k in rest)
    tpose = max(abs(rest['L_arm_drop']), abs(rest['R_arm_drop'])) < 10 and abs(rest['spine_fwd']) < 5 \
        and max(rest['L_elbow'], rest['R_elbow']) < 15
    results.append({'file': path, 'rest': rest, 'first_frame': first, 'first_frame_minus_rest_max_deg': round(diff, 1),
                    'rest_is_tpose': tpose})
    print(f"{path}\n  rest  {rest}\n  frame{f0} {first}\n  rest is T-pose: {tpose}  (max rest/first-frame gap {diff:.1f} deg)")

if out_json:
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=1)
