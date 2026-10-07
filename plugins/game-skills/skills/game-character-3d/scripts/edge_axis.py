"""Blade roll so the cutting edge, not the flat, leads each strike (4-30).

blender -b -P edge_axis.py -- <SK_Hero.fbx> <Hero.json> [--win clip=strike:hit,...]... [--write]

The sword is attached with its blade (+Z) along grip.R.hole_axis; the roll about that axis was free and
ue_build_plaza.py put the blade's THICKNESS axis (+X) along the forearm, so the tip moved 53-65 deg toward the flat
normal in every strike ("칼등으로 치는 느낌"). Per strike frame (strike-1 .. hit+2) this takes the tip velocity in hand
space, finds the roll whose edge line (sword +Y, the 6 cm width; thickness is 4.3 cm) minimises the speed-weighted angle
between velocity and edge, and writes the edge line as grip.R.edge_axis (rest pose, Blender +X forward / +Y left / +Z up,
same frame as hole_axis). The result depends on the attack clips: re-run after changing them (run_dk_process.sh does).
"""
import bpy, sys, json, math
from mathutils import Vector

argv = sys.argv[sys.argv.index('--') + 1:]
fbx, js = argv[0], argv[1]
WINS = {}
for i, a in enumerate(argv):
    if a == '--win':
        clip, spec = argv[i + 1].split('=')
        WINS[clip] = [tuple(int(v) for v in w.split(':')) for w in spec.split(',')]
if not WINS:
    WINS = {'onehand': [(26, 33), (56, 62), (86, 91)], 'power': [(38, 42)]}

info = json.load(open(js, encoding='utf-8'))
g = info['grip']['R']
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=fbx)
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
W = arm.matrix_world
H = (W @ arm.data.bones['Head'].head_local).z
hand_rest = (W @ arm.data.bones['R_Hand'].matrix_local).to_3x3().normalized()
z = Vector(g['hole_axis']).normalized()
d = ((W @ arm.data.bones['R_Hand'].head_local) - (W @ arm.data.bones['R_Forearm'].head_local)).normalized()
x = (d - z * d.dot(z)).normalized()          # old attachment: sword +X (thickness) along the forearm
y = z.cross(x)                                # old edge line
inv = hand_rest.inverted()
zl, xl, yl = inv @ z, inv @ x, inv @ y
L = 0.42 * H                                  # ~80 % of the blade (tip 0.79 m from the grip on a 1.5 m hero)

samples = []                                  # (clip, window, v along old edge, v along old flat normal)
for clip, wins in WINS.items():
    arm.animation_data.action = next(a for a in bpy.data.actions if a.name.endswith(clip))
    for k, h in wins:
        prev = None
        for f in range(k - 1, h + 3):
            bpy.context.scene.frame_set(f)
            m = W @ arm.pose.bones['R_Hand'].matrix
            r = m.to_3x3().normalized()
            tip = m.translation + (r @ zl) * L
            if prev is not None:
                v = r.inverted() @ (tip - prev)
                samples.append((clip, k, v.dot(yl), v.dot(xl)))
            prev = tip


def flat_angle(t, key=None):
    """speed-weighted mean angle between tip velocity and the edge line rolled by t (0 = old attachment)"""
    tot = w = 0.0
    for clip, k, ve, vn in samples:
        if key and (clip, k) != key:
            continue
        e = math.cos(t) * ve + math.sin(t) * vn
        n = -math.sin(t) * ve + math.cos(t) * vn
        sp = math.hypot(ve, vn)
        tot += sp * math.degrees(math.atan2(abs(n), abs(e)))
        w += sp
    return tot / max(w, 1e-9)


best = min((math.radians(a) for a in range(-90, 90)), key=flat_angle)
edge = (y * math.cos(best) + x * math.sin(best)).normalized()
print('EDGE_AXIS roll', round(math.degrees(best)), 'deg from old, flat angle', round(flat_angle(0), 1), '->', round(flat_angle(best), 1))
for key in dict.fromkeys((c, k) for c, k, _, _ in samples):
    print('EDGE_AXIS', key, round(flat_angle(0, key)), '->', round(flat_angle(best, key)))
if '--write' in argv:
    g['edge_axis'] = [round(v, 4) for v in edge]
    g['edge_flat_angle_deg'] = round(flat_angle(best), 1)
    json.dump(info, open(js, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print('EDGE_AXIS written', g['edge_axis'])
