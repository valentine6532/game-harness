"""Blender: whole-body swing metrics for Mixamo (Y Bot) or Hero clips.
-- <fbx> <out.json> [action-substring]
Per frame: shoulder-line yaw, hip-line yaw, pelvis height (/ standing height), trunk lean,
right-hand speed, virtual blade tip speed (Mixamo: pinky1->index1 knuckle line, 0.45*height),
forearm-blade angle. Segments = tip-speed peaks."""
import sys, bpy, json, math
from mathutils import Vector
a = sys.argv[sys.argv.index('--') + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=a[0])
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
names = [b.name for b in arm.data.bones]
MX = any(n.startswith('mixamorig:') for n in names)
if MX:
    B = {k: 'mixamorig:' + v for k, v in dict(hip='Hips', chest='Spine2', neck='Neck', head='Head', ls='LeftArm', rs='RightArm',
         lu='LeftUpLeg', ru='RightUpLeg', rf='RightForeArm', rh='RightHand', idx='RightHandIndex1', pky='RightHandPinky1',
         lfoot='LeftFoot', rfoot='RightFoot').items()}
else:
    B = dict(hip='Pelvis', chest='Spine02', neck='NeckTwist01', head='Head', ls='L_Upperarm', rs='R_Upperarm', lu='L_Thigh',
             ru='R_Thigh', rf='R_Forearm', rh='R_Hand', lfoot='L_Foot', rfoot='R_Foot')
acts = [x for x in bpy.data.actions if (len(a) < 3 or a[2] in x.name)]
P = arm.pose.bones
if not MX:
    rest = (arm.matrix_world @ arm.data.bones[B['rh']].matrix_local).to_3x3()
    AX = rest.inverted() @ Vector((0.88009888, 0.29352322, -0.37318894)).normalized()
def w(n, tail=False):
    b = P[n]; return arm.matrix_world @ (b.tail if tail else b.head)
def yaw(v): return math.degrees(math.atan2(v.y, v.x))
out = {}
for ac in acts:
    arm.animation_data.action = ac
    f0, f1 = (int(v) for v in ac.frame_range)
    bpy.context.scene.frame_set(f0)
    ground = min(w(B['lfoot']).z, w(B['rfoot']).z)
    H = w(B['head']).z - ground
    hip0 = w(B['hip']).z
    rows = []; prev = None
    for f in range(f0, f1 + 1):
        bpy.context.scene.frame_set(f)
        sh = w(B['rs']) - w(B['ls']); hp = w(B['ru']) - w(B['lu'])
        trunk = w(B['neck']) - w(B['hip'])
        lean = math.degrees(trunk.angle(Vector((0, 0, 1))))
        hand = w(B['rh'])
        fore = (hand - w(B['rf'])).normalized()
        if MX:
            bd = (w(B['idx']) - w(B['pky'])).normalized()
        else:
            bd = (arm.matrix_world.to_3x3() @ P[B['rh']].matrix.to_3x3() @ AX).normalized()
        tip = hand + bd * 0.45 * H
        r = dict(f=f, sh=yaw(sh), hp=yaw(hp), hipz=(w(B['hip']).z - hip0) / H, lean=lean,
                 fb=math.degrees(fore.angle(bd)))
        if prev:
            r['hv'] = (hand - prev[0]).length * 30 / H; r['tv'] = (tip - prev[1]).length * 30 / H
        else:
            r['hv'] = r['tv'] = 0.
        prev = (hand.copy(), tip.copy()); rows.append(r)
    # unwrap yaw
    for key in ('sh', 'hp'):
        off = 0; last = rows[0][key]
        for r in rows:
            v = r[key] + off
            while v - last > 180: v -= 360; off -= 360
            while v - last < -180: v += 360; off += 360
            r[key] = v; last = v
    # swing peaks: local maxima of tip speed above 40% of max, separated by 8 frames
    tv = [r['tv'] for r in rows]; m = max(tv)
    peaks = []
    for i in range(2, len(rows) - 2):
        if tv[i] >= 0.4 * m and tv[i] == max(tv[max(0, i - 6):i + 7]):
            if not peaks or i - peaks[-1] > 8: peaks.append(i)
    segs = []
    for i in peaks:
        lo, hi = max(0, i - 15), min(len(rows), i + 10)
        win = rows[lo:hi]
        hvp = max(range(lo, hi), key=lambda k: rows[k]['hv'])
        segs.append(dict(tip_peak=rows[i]['f'], hand_peak=rows[hvp]['f'], lag=rows[i]['f'] - rows[hvp]['f'],
                         tip_speed=round(rows[i]['tv'], 2), hand_speed=round(rows[i]['hv'], 2),
                         tip_over_hand=round(rows[i]['tv'] / max(rows[i]['hv'], 1e-6), 2),
                         sh_yaw_range=round(max(r['sh'] for r in win) - min(r['sh'] for r in win), 1),
                         hip_yaw_range=round(max(r['hp'] for r in win) - min(r['hp'] for r in win), 1),
                         hip_drop=round(-min(r['hipz'] for r in win) * 100, 1),
                         lean_max=round(max(r['lean'] for r in win), 1),
                         fb_range=(round(min(r['fb'] for r in win)), round(max(r['fb'] for r in win)))))
    out[ac.name.split('|')[-1]] = dict(frames=(f0, f1), H=round(H, 3), segs=segs,
        sh_yaw_total=round(max(r['sh'] for r in rows) - min(r['sh'] for r in rows), 1),
        hip_drop_total=round(-min(r['hipz'] for r in rows) * 100, 1), rows=rows)
    print('CLIP', ac.name, json.dumps(segs), flush=True)
json.dump(out, open(a[1], 'w'))
