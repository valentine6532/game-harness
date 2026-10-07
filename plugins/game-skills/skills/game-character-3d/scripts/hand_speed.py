"""Blender: per-frame right-hand height / speed of chosen actions (combo segment frames).  -- <fbx> <clip> [<clip>...]"""
import sys, bpy
a = sys.argv[sys.argv.index('--') + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=a[0])
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
for ac in bpy.data.actions:
    if not any(ac.name.endswith(c) for c in a[1:]):
        continue
    arm.animation_data.action = ac
    f0, f1 = (int(v) for v in ac.frame_range)
    prev = None; row = []
    for f in range(f0, f1 + 1):
        bpy.context.scene.frame_set(f)
        p = arm.matrix_world @ arm.pose.bones['R_Hand'].head
        sp = (p - prev).length * 30 if prev else 0.0
        prev = p.copy(); row.append(f'{f}:{p.z:.2f}/{sp:.1f}')
    print('SPEED', ac.name.split('|')[-1], ' '.join(row), flush=True)
