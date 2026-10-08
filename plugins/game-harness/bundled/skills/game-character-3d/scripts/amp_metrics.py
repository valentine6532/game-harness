"""hero FBX: how big each attack window is (step, crouch, torso turn, arm reach, sword arc), % of height / deg"""
import bpy, sys, json
from math import degrees, acos
from mathutils import Vector
fbx, js = sys.argv[sys.argv.index('--') + 1:]
g = json.load(open(js, encoding='utf-8'))['grip']['R']
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=fbx)
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
W = arm.matrix_world
H = (W @ arm.data.bones['Head'].head_local).z
hand_rest = (W @ arm.data.bones['R_Hand'].matrix_local).to_3x3().normalized()
axis_local = hand_rest.inverted() @ Vector(g['hole_axis']).normalized()
arm_len = ((W @ arm.data.bones['R_Upperarm'].head_local) - (W @ arm.data.bones['R_Hand'].head_local)).length
def P(b): return W @ arm.pose.bones[b].head
def tip():
    m = W @ arm.pose.bones['R_Hand'].matrix
    return m.translation + m.to_3x3().normalized() @ axis_local * 0.45 * H
arm.animation_data.action = next(a for a in bpy.data.actions if a.name.endswith('ssidle'))
bpy.context.scene.frame_set(1); stand_hip = P('Hip').z
WINS = {'onehand': [(16, 26, 34, 40), (45, 56, 63, 68), (75, 86, 92, 98)], 'power': [(18, 38, 42, 50)]}
for clip, wins in WINS.items():
    arm.animation_data.action = next(a for a in bpy.data.actions if a.name.endswith(clip))
    for s, k, h, e in wins:
        rows = {}
        for f in range(s, e + 1):
            bpy.context.scene.frame_set(f)
            fw = (W @ arm.pose.bones['Spine02'].matrix).to_3x3() @ Vector((1, 0, 0))
            rows[f] = dict(hip=P('Hip').copy(), yaw=degrees(Vector((fw.x, fw.y)).angle_signed(Vector((1, 0))) if fw.xy.length > 1e-6 else 0),
                           reach=(P('R_Hand') - P('R_Upperarm')).length / arm_len, tip=tip())
        yaws = [r['yaw'] for r in rows.values()]
        step = (rows[e]['hip'] - rows[s]['hip']).xy.length / H * 100
        drop = (stand_hip - min(r['hip'].z for r in rows.values())) / H * 100
        tz = [r['tip'].z / H * 100 for r in rows.values()]
        print(f'AMP {clip} {s}-{e}: step {step:.0f}%  crouch(hip drop vs idle) {drop:.1f}%  torso yaw range {max(yaws)-min(yaws):.0f}deg  '
              f'reach at hit {rows[h]["reach"]:.2f} (max {max(r["reach"] for r in rows.values()):.2f})  tip height {min(tz):.0f}..{max(tz):.0f}%', flush=True)
