"""Attack body exaggeration for retargeted clips (4-28), Blender side.

Mixamo sword clips are motion capture: the torso already turns 130-150 deg and the arm is fully out at the hit, but
the body swings upright (hip ~2 % of height ABOVE the crouched combat idle) and steps in only 16-35 % of height, so
from the 21 m quarter view the swing reads as an arm waving in place. Per attack window (start, strike, hit, end):
  step   : the hip's horizontal travel from the window start is scaled (continuous at the start, lunge grows)
  crouch : the hip dips by CROUCH x height, smoothstep in from the start to the hit, back out by the window end
  lean   : Spine01 pitches toward the target (hip -> sword tip at the hit) by LEAN deg, same envelope
Legs follow by an analytic two-bone solve: a planted foot keeps its world spot, a moving foot drifts to the extra
step, the knee keeps its original bend plane, the foot keeps its original world rotation; keyed on thigh / calf / foot. Returns per-window hip travel (for Hero.json lunges) and checks.
"""
import bpy
from math import radians, degrees, pi, sin
from mathutils import Matrix, Vector, Quaternion


def _smooth(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def _bump(f, s, h, e):
    """0 at s, 1 at h, 0 at e (smoothstep both sides)"""
    if f <= h:
        return _smooth((f - s) / max(h - s, 1))
    return 1.0 - _smooth((f - h) / max(e - h, 1))


def _envelope(f, keys):
    for (a, va), (b, vb) in zip(keys, keys[1:]):
        if f <= b:
            return va + (vb - va) * _smooth((f - a) / max(b - a, 1e-6))
    return keys[-1][1]


def _body_lead(f, s, k, h, e):
    """Load upright, start the chest before the arm, then settle onto the front leg.

    All times are source frames. Separate chest/hip envelopes keep the body from
    spending most of its downward travel while the sword is still being raised.
    Both corrections are zero at the clip boundaries for the existing crossfade.
    """
    load = max(s + 1, k - 3)
    chest_peak = max(k + 1, h - 1)
    settle = min(h + 1, e - 2)
    dip = _envelope(f, [(s, 0), (load, .18), (k, .3), (settle, 1), (e, 0)])
    lean = _envelope(f, [(s, 0), (load, -.35), (k, .35),
                         (chest_peak, 1.3), (min(h + 2, e - 1), .9), (e, 0)])
    return dip, lean


def _set(arm, name, M):
    pb = arm.pose.bones[name]
    pb.matrix = M
    bpy.context.view_layer.update()


def _key(arm, names, f, loc=False):
    for n in names:
        pb = arm.pose.bones[n]
        pb.keyframe_insert('rotation_quaternion', frame=f)
        if loc:
            pb.keyframe_insert('location', frame=f)


def apply(arm, action, windows, step=2.0, crouch=0.10, lean=12.0, log=print, body_lead=False, body_drive=False, drive_scale=1.0):
    """windows: [(s, k, h, e)] frames. Edits `action` in place (it must be arm's active action)."""
    arm.animation_data.action = action
    scene = bpy.context.scene
    Wm = arm.matrix_world
    Wi = Wm.inverted()
    A3 = Wi.to_3x3()                       # world vector -> armature space
    H = (Wm @ arm.data.bones['Head'].head_local).z - (Wm @ arm.data.bones['L_Foot'].head_local).z
    legs = {'L': ('L_Thigh', 'L_Calf', 'L_Foot'), 'R': ('R_Thigh', 'R_Calf', 'R_Foot')}
    leg_len = {s: (arm.data.bones[t].head_local - arm.data.bones[c].head_local).length * Wm.to_scale().x
               + (arm.data.bones[c].head_local - arm.data.bones[fo].head_local).length * Wm.to_scale().x
               for s, (t, c, fo) in legs.items()}
    f0 = min(w[0] for w in windows)
    f1 = int(action.frame_range[1])        # to the clip end: the frames after a window keep its extra travel
    for pb in arm.pose.bones:
        pb.rotation_mode = 'QUATERNION'

    # 1. original world data
    orig = {}
    for f in range(f0, f1 + 1):
        scene.frame_set(f)
        P = lambda n: Wm @ arm.pose.bones[n].head
        orig[f] = {'hip': P('Hip').copy(),
                   'foot': {s: (Wm @ arm.pose.bones[fo].matrix).copy() for s, (_, _, fo) in legs.items()},
                   'knee': {s: P(c).copy() for s, (_, c, _) in legs.items()},
                   'thigh': {s: P(t).copy() for s, (t, _, _) in legs.items()}}

    # 2. per-frame offsets
    plan = {}
    travel = {}
    for wi, (s, k, h, e) in enumerate(windows):
        scene.frame_set(h)
        tipdir = (Wm @ arm.pose.bones['R_Hand'].head - orig[h]['hip'])
        tipdir.z = 0.0
        fwd = tipdir.normalized() if tipdir.length > 1e-6 else Vector((1, 0, 0))
        if body_drive:
            fwd = Vector((1, 0, 0))
        shift = {sd: Vector() for sd in legs}
        for f in range(s, e + 1):
            d = orig[f]['hip'] - orig[s]['hip']
            E = Vector((d.x, d.y, 0.0)) * (step - 1.0)
            b = _bump(f, s, h, e)
            dip_weight, lean_weight = _body_lead(f, s, k, h, e) if body_lead else (b, b)
            dip = crouch * H * dip_weight
            hip_new = orig[f]['hip'] + E - Vector((0, 0, dip))
            hip_yaw = chest_yaw = transfer = 0.0
            if body_drive:
                sign = -1 if wi == 1 else 1
                load = s + (k-s)*.5
                ds = float(drive_scale)
                hip_yaw = ds * sign * _envelope(f, [(s,0),(load,-8),(k,8),(h-2,12),(h+1,8),(e,0)])
                chest_yaw = ds * sign * _envelope(f, [(s,0),(load,-14),(k,-8),(h-1,12),(h+1,8),(e,0)])
                transfer = ds * H * _envelope(f, [(s,0),(load,-.025),(k,0),(h,.035),(e,0)])
                hip_new += fwd*transfer
            # Keep the accepted foot path when retiming the body. Otherwise a
            # higher loading pose makes the reach limiter drag the rear foot.
            foot_plan_hip = orig[f]['hip'] + E - Vector((0, 0, crouch * H * b)) if body_lead else hip_new
            feet = {}
            for sd in legs:
                if f > s:
                    moved = (orig[f]['foot'][sd].translation - orig[f - 1]['foot'][sd].translation).length
                    if moved > 0.004 * H:                       # swinging foot: drift toward the extra step
                        shift[sd] = shift[sd].lerp(E, 0.35)
                tgt = orig[f]['foot'][sd].translation + shift[sd]
                th = orig[f]['thigh'][sd] + (foot_plan_hip - orig[f]['hip'])
                reach = (tgt - th).length
                if reach > 0.985 * leg_len[sd]:               # out of reach: let the foot follow (drag) instead of popping
                    pull = (th - tgt)
                    pull.z = 0.0
                    if pull.length > 1e-6:
                        need = reach - 0.985 * leg_len[sd]
                        shift[sd] += pull.normalized() * min(need, pull.length)
                        tgt = orig[f]['foot'][sd].translation + shift[sd]
                feet[sd] = tgt
            if body_lead:
                # If a planted leg cannot reach the higher preparation pose,
                # soften the knee by lowering the pelvis, never slide its foot.
                for sd in legs:
                    offset = orig[f]['thigh'][sd] - orig[f]['hip']
                    th = hip_new + Quaternion(Vector((0,0,1)), radians(hip_yaw)) @ offset
                    horizontal = (th - feet[sd]).xy.length
                    limit = max((0.985 * leg_len[sd]) ** 2 - horizontal ** 2, 0.0) ** .5
                    hip_new.z -= max(0.0, th.z - feet[sd].z - limit)
                dip = orig[f]['hip'].z - hip_new.z
            plan[f] = {'E': E+fwd*transfer, 'dip': dip, 'lean': lean * lean_weight, 'fwd': fwd, 'feet': feet,
                       'hip_yaw':hip_yaw, 'chest_yaw':chest_yaw}
        travel[s] = (orig[e]['hip'] - orig[s]['hip']) * step
        travel[s].z = 0.0
        # after the window, up to the next one (or the clip end): keep the window's extra travel. The game keeps playing
        # the old clip past the window end while it crossfades; dropping the extra there snapped the hip back by it
        nxt = min([w[0] for w in windows if w[0] > e] + [f1 + 1])
        Ee = plan[e]['E']
        for f in range(e + 1, nxt):
            feet = {}
            for sd in legs:
                moved = (orig[f]['foot'][sd].translation - orig[f - 1]['foot'][sd].translation).length
                if moved > 0.004 * H:
                    shift[sd] = shift[sd].lerp(Ee, 0.35)
                feet[sd] = orig[f]['foot'][sd].translation + shift[sd]
            plan[f] = {'E': Ee, 'dip': 0.0, 'lean': 0.0, 'fwd': fwd, 'feet': feet}

    # 3. per frame: hip, lean, then both legs by an analytic two-bone solve (Blender's IK constraint cannot be used:
    #    thigh / calf are half-length bones with twist bones filling the gap, not connected to the next joint, and the
    #    constraint missed the ankle by 3.5 % and moved the knee by 10 % even with the target on the original ankle)
    seg = {sd: ((arm.data.bones[c].head_local - arm.data.bones[t].head_local).length * Wm.to_scale().x,
                (arm.data.bones[fo].head_local - arm.data.bones[c].head_local).length * Wm.to_scale().x)
           for sd, (t, c, fo) in legs.items()}

    def turn_about(M, pivot, q):
        return Matrix.Translation(pivot) @ q.to_matrix().to_4x4() @ Matrix.Translation(-pivot) @ M

    for f in sorted(plan):
        scene.frame_set(f)
        p = plan[f]
        hip = arm.pose.bones['Hip']
        M = hip.matrix.copy()
        M.translation += A3 @ (p['E'] - Vector((0, 0, p['dip'])))
        _set(arm, 'Hip', M)
        if body_drive:
            axis_up = (A3 @ Vector((0,0,1))).normalized()
            _set(arm,'Hip',turn_about(hip.matrix,hip.matrix.translation,Quaternion(axis_up,radians(p.get('hip_yaw',0)))))
            for name, weight in [('Waist',.25),('Spine01',.4),('Spine02',.35)]:
                sp=arm.pose.bones[name]
                _set(arm,name,turn_about(sp.matrix,sp.matrix.translation,Quaternion(axis_up,radians(p.get('chest_yaw',0)*weight))))
            head=arm.pose.bones['Head']
            _set(arm,'Head',turn_about(head.matrix,head.matrix.translation,Quaternion(axis_up,radians(-.45*(p.get('hip_yaw',0)+p.get('chest_yaw',0))))))
        axis_w = Vector((0, 0, 1)).cross(p['fwd'])
        if axis_w.length > 1e-6 and abs(p['lean']) > 1e-3:
            axis_a = (A3 @ axis_w).normalized()
            spine_weights = [('Waist', .3), ('Spine01', .45), ('Spine02', .25)] if body_lead else [('Spine01', 1)]
            for name, weight in spine_weights:
                sp = arm.pose.bones[name]
                R = Quaternion(axis_a, radians(p['lean'] * weight)).to_matrix().to_4x4()
                head = sp.matrix.translation.copy()
                _set(arm, name, Matrix.Translation(head) @ R @ Matrix.Translation(-head) @ sp.matrix)
        for sd, (t, c, fo) in legs.items():
            a, b = seg[sd]
            Hw = Wm @ arm.pose.bones[t].head
            want = p['feet'][sd]
            Ko, Ao, Ho = orig[f]['knee'][sd], orig[f]['foot'][sd].translation, orig[f]['thigh'][sd]
            u = want - Hw
            d = min(max(u.length, abs(a - b) + 1e-5), a + b - 1e-5)
            u.normalize()
            bend = Ko - (Ho + (Ao - Ho).normalized() * (Ko - Ho).dot((Ao - Ho).normalized()))
            n = bend - u * bend.dot(u)
            if n.length < 1e-6:
                n = p['fwd'] - u * p['fwd'].dot(u)
            n.normalize()
            x = (a * a - b * b + d * d) / (2 * d)
            K = Hw + u * x + n * (max(a * a - x * x, 0.0) ** 0.5)
            A = Hw + u * d
            tw = Wm @ arm.pose.bones[t].matrix
            Kc = Wm @ arm.pose.bones[c].head
            _set(arm, t, Wi @ turn_about(tw, Hw, (Kc - Hw).rotation_difference(K - Hw)))
            cw = Wm @ arm.pose.bones[c].matrix
            Ac = Wm @ arm.pose.bones[fo].head
            _set(arm, c, Wi @ turn_about(cw, K, (Ac - K).rotation_difference(A - K)))
            fw = orig[f]['foot'][sd]
            _set(arm, fo, Wi @ (Matrix.Translation(Wm @ arm.pose.bones[fo].head) @ fw.to_quaternion().to_matrix().to_4x4()))
        _key(arm, ['Hip'], f, loc=True)
        spine_keys = ['Waist', 'Spine01', 'Spine02'] if body_lead else ['Spine01']
        _key(arm, spine_keys + [n for leg in legs.values() for n in leg], f)
        if body_drive:
            _key(arm,['Head'],f)

    # 5. checks on the final keys
    slide = miss = 0.0
    hyper = 180.0
    floor_drop = 0.0
    for s, k, h, e in windows:
        for f in range(s + 1, e + 1):
            scene.frame_set(f)
            for sd, (t, c, fo) in legs.items():
                fw = Wm @ arm.pose.bones[fo].head
                miss = max(miss, (fw - plan[f]['feet'][sd]).length)
                floor_drop = max(floor_drop, orig[f]['foot'][sd].translation.z - fw.z)
                a = (Wm @ arm.pose.bones[t].head - Wm @ arm.pose.bones[c].head)
                b2 = (Wm @ arm.pose.bones[fo].head - Wm @ arm.pose.bones[c].head)
                hyper = min(hyper, 180.0 - degrees(a.angle(b2)) if a.length and b2.length else 180.0)
                was = orig[f]['foot'][sd].translation - orig[f - 1]['foot'][sd].translation
                if was.length < 0.002 * H:                     # planted in the source: how far does it slide now
                    scene.frame_set(f - 1)
                    prev = Wm @ arm.pose.bones[fo].head
                    scene.frame_set(f)
                    slide = max(slide, (fw - prev).length)
    log(f'EXAG_CHECK {action.name}: planted-foot slide max {slide / H * 100:.2f}%/frame, foot target miss max '
        f'{miss / H * 100:.2f}%, foot below source max {floor_drop / H * 100:.2f}%, straightest knee {180 - hyper:.0f}deg bend')
    if body_drive:
        assert miss/H < .002, f'Body drive lost foot contact: {miss/H}'
        log(f'BODY_DRIVE {action.name}: pelvis leads chest; yaw {12*float(drive_scale):.0f}/{12*float(drive_scale):.0f}deg x{drive_scale}, transfer -2.5/+3.5%H, lean peak {lean*1.3:.1f}deg')
    return {s: travel[s] for s, _, _, _ in windows}
