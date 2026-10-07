import sys,bpy,math,json
from mathutils import Vector
a=sys.argv[sys.argv.index('--')+1:]
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.fbx(filepath=a[0])
arm=next(o for o in bpy.data.objects if o.type=='ARMATURE')
act=next(x for x in bpy.data.actions if x.name.endswith(a[1])); arm.animation_data.action=act
W=arm.matrix_world; rest=(W@arm.data.bones['R_Hand'].matrix_local).to_3x3()
AX=rest.inverted()@Vector((0.88009888,0.29352322,-0.37318894)).normalized()
ED=rest.inverted()@Vector((-0.42228377,0.84321147,-0.33267167)).normalized()
H=(W@arm.data.bones['Head'].head_local).z; sc=bpy.context.scene
def st(f):
    sc.frame_set(f); M=W@arm.pose.bones['R_Hand'].matrix; R=M.to_3x3().normalized()
    ax=(R@AX).normalized(); ed=(R@ED).normalized(); tip=M.translation+ax*0.75*H
    return tip, ax.cross(ed).normalized()
for w in a[2:]:
    f0,f1=map(int,w.split('-')); num=den=0; worst=0
    for f in range(f0,f1):
        p0,n=st(f); p1,_=st(f+1); v=p1-p0; s=v.length
        if s<1e-6: continue
        t=math.degrees(math.asin(min(1,abs(v.normalized().dot(n))))); num+=t*s; den+=s; worst=max(worst,t) if s>0.02*H else worst
    print('TILT',a[1],w,round(num/den,1),'worst_fast',round(worst,1),flush=True)
