import sys,bpy,math
from mathutils import Vector, Matrix
a=sys.argv[sys.argv.index('--')+1:]
bpy.ops.wm.read_factory_settings(use_empty=True); bpy.ops.import_scene.fbx(filepath=a[0])
arm=next(o for o in bpy.data.objects if o.type=='ARMATURE')
act=next(x for x in bpy.data.actions if x.name.endswith(a[1])); arm.animation_data.action=act
W=arm.matrix_world; rest=(W@arm.data.bones['R_Hand'].matrix_local).to_3x3()
AX=rest.inverted()@Vector((0.88009888,0.29352322,-0.37318894)).normalized()
ED=rest.inverted()@Vector((-0.42228377,0.84321147,-0.33267167)).normalized()
H=(W@arm.data.bones['Head'].head_local).z; sc=bpy.context.scene
for w in a[2:]:
    f0,f1=map(int,w.split('-')); fr=[]
    for f in range(f0,f1+1):
        sc.frame_set(f); M=W@arm.pose.bones['R_Hand'].matrix; fr.append((M.translation.copy(),M.to_3x3().normalized()))
    res=[]
    for th in range(-90,91,5):
        Rl=Matrix.Rotation(math.radians(th),3,AX); ed=Rl@ED
        num=den=0
        for i in range(len(fr)-1):
            (p0,R0),(p1,R1)=fr[i],fr[i+1]
            t0=p0+R0@AX*0.75*H; t1=p1+R1@AX*0.75*H; v=t1-t0; s=v.length
            n=(R0@AX).cross(R0@ed).normalized()
            if s>1e-6: num+=math.degrees(math.asin(min(1,abs(v.normalized().dot(n)))))*s; den+=s
        res.append((round(num/den,1),th))
    print('SCAN',w,sorted(res)[:3],'at0',[r for r in res if r[1]==0],flush=True)
