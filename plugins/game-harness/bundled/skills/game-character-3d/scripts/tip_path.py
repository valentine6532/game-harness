"""hero FBX: sword tip path per attack window (rest-pose grip axis carried by the hand), height/forward in % of height"""
import bpy, sys, json
from mathutils import Vector
fbx, js = sys.argv[sys.argv.index('--') + 1:]
g = json.load(open(js, encoding='utf-8'))['grip']['R']
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=fbx)
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
H = (arm.matrix_world @ arm.data.bones['Head'].head_local).z
hand_rest = (arm.matrix_world @ arm.data.bones['R_Hand'].matrix_local).to_3x3().normalized()
axis_local = hand_rest.inverted() @ Vector(g['hole_axis']).normalized()
L = 0.45 * H
WINS = {'onehand': [(16, 26, 31, 40), (45, 56, 61, 68), (75, 86, 91, 98)], 'power': [(18, 38, 41, 50)]}
for clip, wins in WINS.items():
    arm.animation_data.action = next(a for a in bpy.data.actions if a.name.endswith(clip))
    for s, k, h, e in wins:
        bpy.context.scene.frame_set(s)
        hip0 = arm.matrix_world @ arm.pose.bones['Hip'].head
        rows = []
        prev = None
        for f in range(k - 2, e + 1):
            bpy.context.scene.frame_set(f)
            m = arm.matrix_world @ arm.pose.bones['R_Hand'].matrix
            tip = m.translation + m.to_3x3().normalized() @ axis_local * L
            hip = arm.matrix_world @ arm.pose.bones['Hip'].head
            rel = tip - Vector((hip.x, hip.y, 0))
            v = (tip - prev) if prev else Vector()
            prev = tip.copy()
            rows.append(f'{f}{"*" if f == h else ""}:z{tip.z / H * 100:.0f} fwd{rel.x / H * 100:.0f} side{rel.y / H * 100:.0f} vz{v.z / H * 100:+.0f}')
        print('TIP', clip, s, ' | '.join(rows), flush=True)
