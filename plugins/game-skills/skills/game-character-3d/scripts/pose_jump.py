"""hero FBX: pose jump (mean joint distance, % of height, hip-relative) at the clip cuts the game makes vs one normal frame"""
import bpy, sys
path = sys.argv[sys.argv.index('--') + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=path)
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
J = ['Head', 'R_Hand', 'L_Hand', 'R_Forearm', 'L_Forearm', 'R_Foot', 'L_Foot', 'R_Calf', 'L_Calf', 'Spine02']
H = (arm.matrix_world @ arm.data.bones['Head'].head_local).z
def pose(clip, f):
    arm.animation_data.action = next(a for a in bpy.data.actions if a.name.endswith(clip))
    bpy.context.scene.frame_set(f)
    hip = arm.matrix_world @ arm.pose.bones['Hip'].head
    return [arm.matrix_world @ arm.pose.bones[j].head - hip for j in J]
def d(a, b):
    return sum((x - y).length for x, y in zip(a, b)) / len(a) / H * 100
cuts = [('1->2 combo', ('onehand', 40), ('onehand', 45)), ('2->3 combo', ('onehand', 68), ('onehand', 75)),
        ('3->finisher', ('onehand', 98), ('power', 18)), ('finisher->1', ('power', 50), ('onehand', 16)),
        ('1 end->idle', ('onehand', 40), ('ssidle', 1)), ('2 end->idle', ('onehand', 68), ('ssidle', 1)),
        ('3 end->idle', ('onehand', 98), ('ssidle', 1)), ('fin end->idle', ('power', 50), ('ssidle', 1)),
        ('idle->1', ('ssidle', 1), ('onehand', 16)), ('run->1', ('runintent', 10), ('onehand', 16))]
for name, a, b in cuts:
    print('JUMP', f'{name:14s}', f'{d(pose(*a), pose(*b)):.1f}% of height', flush=True)
for clip, f in (('onehand', 20), ('onehand', 29), ('onehand', 35), ('ssidle', 10)):
    print('NORMAL', clip, f, f'{d(pose(clip, f), pose(clip, f + 2)):.1f}% per game frame (2 src frames)', flush=True)
