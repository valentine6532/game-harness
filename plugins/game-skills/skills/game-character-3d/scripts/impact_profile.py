"""Blender: impact profile of attack windows -- does the striking part stop at the hit, or sweep on through?

Usage: blender -b --factory-startup -P impact_profile.py -- <SK_Name.fbx> --clip <clip>=s:k:h:e[,s:k:h:e...] [--clip ...]
       [--bone R_Hand] [--fps 30] [--json out.json]

<clip> matches the end of the action name (as hand_speed.py). s:k:h:e = start, strike, hit, end frames (07_animation.md).
--bone is the striking part: weapon hand (R_Hand), or a claw/tail/foot bone for creatures. World speed of its head.

Per window:
  windup_avg    mean speed s..k-1                  peak / ratio   top speed near the hit, peak / windup_avg
  accel_f       frames from <30% of peak up to peak (short = snappy strike)
  stop_f        frames from peak down to <30% of peak (short = the blow lands and stops)
  after_hit     speed at h+1..h+3 as a fraction of peak (near 1.0 = still sweeping after the hit)
  reaccel       speeds up again before it has stopped (flows into the next move without a settle)
There is no universal pass value: compare before/after of the same clip and judge in the game camera (07 "타격감").
"""
import json
import sys

import bpy

argv = sys.argv[sys.argv.index('--') + 1:]
fbx, rest = argv[0], argv[1:]
bone, fps, out_json, clips = 'R_Hand', 30.0, None, {}
i = 0
while i < len(rest):
    k, v = rest[i], rest[i + 1]
    if k == '--bone':
        bone = v
    elif k == '--fps':
        fps = float(v)
    elif k == '--json':
        out_json = v
    elif k == '--clip':
        name, wins = v.split('=', 1)
        clips[name] = [tuple(int(x) for x in w.split(':')) for w in wins.split(',')]
    i += 2

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=fbx)
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
results = []
for clip, windows in clips.items():
    act = next((a for a in bpy.data.actions if a.name.endswith(clip)), None)
    if act is None:
        print('MISSING action', clip, flush=True)
        continue
    arm.animation_data.action = act
    f0, f1 = (int(v) for v in act.frame_range)
    speed, prev = {}, None
    for f in range(f0, f1 + 1):
        bpy.context.scene.frame_set(f)
        p = arm.matrix_world @ arm.pose.bones[bone].head
        speed[f] = (p - prev).length * fps if prev is not None else 0.0
        prev = p.copy()
    for s, k, h, e in windows:
        pk = max(range(k, min(h + 6, f1) + 1), key=lambda f: speed[f])
        peak = speed[pk]
        windup = sum(speed[f] for f in range(s, k)) / max(k - s, 1)
        accel = next((pk - f for f in range(pk - 1, f0 - 1, -1) if speed[f] < 0.3 * peak), None)
        stop = next((f - pk for f in range(pk + 1, f1 + 1) if speed[f] < 0.3 * peak), None)
        reaccel = False
        for f in range(pk + 2, (pk + stop if stop else f1) + 1):
            if speed[f] > speed[f - 1] * 1.1 and speed[f] > 0.3 * peak:
                reaccel = True
                break
        row = {'clip': clip, 'window': [s, k, h, e], 'windup_avg': round(windup, 2), 'peak': round(peak, 2),
               'peak_frame': pk, 'ratio': round(peak / windup, 1) if windup else None,
               'accel_f': accel, 'stop_f': stop, 'stop_s': round(stop / fps, 2) if stop else None,
               'after_hit': [round(speed[f] / peak, 2) for f in range(h + 1, min(h + 3, f1) + 1)],
               'reaccel': reaccel}
        results.append(row)
        print('IMPACT', json.dumps(row), flush=True)

if out_json:
    with open(out_json, 'w', encoding='utf-8') as fh:
        json.dump({'fbx': fbx, 'bone': bone, 'fps': fps, 'windows': results}, fh, indent=1)
