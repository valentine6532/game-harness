"""Blender: per-frame right-hand height/speed for each action (find the active part of long clips)."""
import sys, bpy
from mathutils import Vector
path = sys.argv[sys.argv.index('--') + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=path)
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
for ac in bpy.data.actions:
    arm.animation_data.action = ac
    f0, f1 = (int(v) for v in ac.frame_range)
    prev = None; rows = []
    for f in range(f0, f1 + 1, 6):
        bpy.context.scene.frame_set(f)
        p = arm.matrix_world @ arm.pose.bones['R_Hand'].head
        sp = (p - prev).length / 6 * 30 if prev else 0
        prev = p.copy()
        rows.append(f'{f}:{p.z:.2f}/{sp:.1f}')
    print('MOTION', ac.name.split('|')[-1], f0, f1, ' '.join(rows))
