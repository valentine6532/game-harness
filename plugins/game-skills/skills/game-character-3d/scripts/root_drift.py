"""Blender: per action, Root/Hip world XY displacement (first->last frame) and max excursion."""
import sys, bpy
path = sys.argv[sys.argv.index('--') + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=path)
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
for ac in bpy.data.actions:
    arm.animation_data.action = ac
    f0, f1 = (int(v) for v in ac.frame_range)
    pts = {}
    for b in ('Root', 'Hip'):
        seq = []
        for f in range(f0, f1 + 1, 2):
            bpy.context.scene.frame_set(f)
            p = arm.matrix_world @ arm.pose.bones[b].head
            seq.append((p.x, p.y, p.z))
        d = ((seq[-1][0] - seq[0][0]) ** 2 + (seq[-1][1] - seq[0][1]) ** 2) ** 0.5
        mx = max(((q[0] - seq[0][0]) ** 2 + (q[1] - seq[0][1]) ** 2) ** 0.5 for q in seq)
        pts[b] = f'{b}: end-start {d:.2f}m max {mx:.2f}m'
    print('DRIFT', ac.name.split('|')[-1], f0, f1, pts['Root'], '|', pts['Hip'])
