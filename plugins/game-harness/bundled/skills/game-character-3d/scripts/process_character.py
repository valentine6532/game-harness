"""Blender: clean a Tripo rigged/animated character for Unreal.

blender -b --python process_character.py -- --name Hero --glb gen.glb --fbx anim1.fbx [--fbx anim2.fbx] --out dir
- keeps only the armature + skinned mesh (Tripo FBX also carries Camera/Cube/Light)
- merges actions from every FBX onto the first armature, renames them <Name>_<clip>
- moves the root bone to the world origin (Tripo leaves the body off-centre)
- extracts BaseColor / Normal (converted GL->DirectX for Unreal) / ORM from the generation GLB
- --baked dir: swap in the high->low baked mesh (bake_highpoly.py), auto-aligned to the rigged mesh, weights transferred
- --mixamo clip=file.fbx: retargets a Mixamo clip onto the Tripo skeleton (see retarget_mixamo)
- writes SK_<Name>.fbx (mesh + skeleton + all clips) and <Name>.json (height, clips, textures)
"""
import argparse, json, sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))   # exaggerate_attack.py next to this file
from mathutils import Vector

p = argparse.ArgumentParser()
p.add_argument('--name', required=True)
p.add_argument('--glb', required=True)
p.add_argument('--fbx', action='append', required=True)
p.add_argument('--out', required=True)
p.add_argument('--baked', help='bake_highpoly.py output dir: replaces the Tripo mesh + textures, skin weights transferred from the rig mesh')
p.add_argument('--cloth-classes', help='T_<Name>_Classes.png from smart_texture.py: red-cloth faces go to material slot M_<Name>_Cloth (Unreal cloth sim)')
p.add_argument('--parts', help='Tripo segmentation GLB (mesh segment v2) + --parts-json from classify_parts.py: cloth / tail faces from the part labels')
p.add_argument('--parts-json')
p.add_argument('--fur-shells', type=int, default=0, help='shell-fur layers over fur faces (needs --parts), slot M_<Name>_Fur, shell height in UV1.x')
p.add_argument('--fur-length', type=float, default=0.012, help='fur length as a fraction of the character height')
p.add_argument('--normal', help='replacement DirectX normal map (e.g. bake_normal_onto.py 4K) instead of the source normal')
p.add_argument('--uv', help='reuv_bake.py output dir: its uv_new.npy replaces the rig mesh UV (4-21)')
p.add_argument('--tex-dir', help='take T_<Name>_{BaseColor,ORM,Normal}.png from here (e.g. reuv_bake.py output) instead of extracting them')
p.add_argument('--texfix', default='', help="extra fix_textures.py arguments, e.g. '--steel-f0 keep --steel-chroma 1' (deathknight)")
p.add_argument('--mixamo', action='append', help='clip=path.fbx: Mixamo clip (any mixamorig skeleton, no skin) retargeted onto the Tripo rig')
p.add_argument('--rezero', action='append', help='clip=f0-f1,f0-f1: attack windows the game plays (4-27): hip travel restarts at 0 '
               'at each window start, the travel over each window goes to Hero.json lunges (the game moves the capsule by it)')
p.add_argument('--exaggerate', action='append', help='clip=K (4-28): inside the clip --rezero windows, the upper spine '
               '(Waist, Spine01, Spine02) turns K times as far from the window-start pose, faded in and out over the window '
               '(sin envelope: 0 at both ends, so combo cuts do not pop). Quarter-view readability of the twist')
p.add_argument('--attack-body-lead', action='append', default=[], help='clip: load/open chest, lead into the cut, settle hips separately (4-35)')
p.add_argument('--attack-body-drive', action='append', default=[], help='clip: pelvis-first turn, delayed chest release and weight transfer; use with body-lead (4-37)')
p.add_argument('--attack-drive-scale', action='append', default=[], help='clip=K: scale the body-drive pelvis/chest yaw (12 deg x K) and weight transfer (10-01; quick blade used 1.6)')
p.add_argument('--attack-body', action='append', help='clip=STEP:CROUCH:LEAN@s:k:h:e,s:k:h:e (4-28, exaggerate_attack.py): '
               'per attack window (start, strike, hit, end) the hip travel is scaled by STEP, the hip dips CROUCH x height '
               'and the chest leans LEAN deg toward the target at the hit; legs re-solved so planted feet stay put. '
               'Hero.json lunges then carry the scaled travel')
p.add_argument('--attack-edge-roll', action='append', default=[], help='clip=DEG (4-44): constant right-hand roll about the '
               'equipped sword axis so the edge, not the flat, leads the unmodified mocap arm; needs --attack-sword-axis')
p.add_argument('--attack-sword-axis', help='x:y:z: equipped sword axis in Blender world rest pose (measure on the engine attachment)')
p.add_argument('--fist-hole', action='append', help="SIDE:RADIUS (fraction of rest height, e.g. R:0.00955): open the modelled fist's grip tunnel "
               "along the Mixamo clips' grip line (needs --mixamo) to RADIUS; grip.SIDE = tunnel centre + axis (4-26)")
a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)

# ---------------------------------------------------------------- textures from the generation GLB
# (or from a Tripo retopology FBX: textures linked to the Principled BSDF -> BaseColor / Normal / separate
#  roughness + metallic maps, packed here into ORM with AO = 1)
if a.glb.lower().endswith('.fbx'):
    bpy.ops.import_scene.fbx(filepath=a.glb)
else:
    bpy.ops.import_scene.gltf(filepath=a.glb)
tex = {}


def save_tex(role, px):
    h, w = px.shape[:2]
    dst = bpy.data.images.new(f'T_{a.name}_{role}', w, h, alpha=False)
    dst.colorspace_settings.name = 'sRGB' if role == 'BaseColor' else 'Non-Color'
    dst.pixels = px.ravel()
    path = out / f'T_{a.name}_{role}.png'
    dst.filepath_raw = str(path)
    dst.file_format = 'PNG'
    dst.save()
    tex[role] = path.name


if a.tex_dir:
    import shutil
    for role in ('BaseColor', 'ORM', 'Normal'):
        shutil.copyfile(Path(a.tex_dir) / f'T_{a.name}_{role}.png', out / f'T_{a.name}_{role}.png')
        tex[role] = f'T_{a.name}_{role}.png'
elif a.glb.lower().endswith('.fbx') and not a.baked:
    linked = {}
    for m in bpy.data.materials:
        if m.use_nodes:
            for l in m.node_tree.links:
                if l.from_node.type == 'TEX_IMAGE' and l.from_node.image:
                    linked[l.to_socket.name if l.to_node.type == 'BSDF_PRINCIPLED' else l.to_node.type] = l.from_node.image

    def pixels(img, size=None):
        if size and img.size[0] != size:
            img.scale(size, size)
        w, h = img.size
        return np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)

    base = pixels(linked['Base Color'])
    save_tex('BaseColor', base)
    if a.normal:
        import shutil
        shutil.copyfile(a.normal, out / f'T_{a.name}_Normal.png')
        tex['Normal'] = f'T_{a.name}_Normal.png'
    else:
        nrm = pixels(linked['NORMAL_MAP'])
        nrm[..., 1] = 1.0 - nrm[..., 1]            # Blender / glTF OpenGL -> DirectX
        save_tex('Normal', nrm)
    size = max(linked['Roughness'].size[0], linked['Metallic'].size[0])
    rough, metal = pixels(linked['Roughness'], size), pixels(linked['Metallic'], size)
    orm = np.ones_like(rough)
    orm[..., 1], orm[..., 2] = rough[..., 0], metal[..., 0]
    save_tex('ORM', orm)
if a.baked:
    import shutil
    baked_info = json.loads((Path(a.baked) / f'{a.name}_bake.json').read_text(encoding='utf-8'))
    for role, fname in baked_info['textures'].items():
        shutil.copyfile(Path(a.baked) / fname, out / fname)
        tex[role] = fname
for img in ([] if a.baked or a.tex_dir or a.glb.lower().endswith('.fbx') else list(bpy.data.images)):
    kind = next((k for k in ('Color', 'NormalGL', 'ORM') if img.name.startswith(k)), None)
    if not kind or not img.size[0]:
        continue
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    if kind == 'NormalGL':
        px[..., 1] = 1.0 - px[..., 1]          # OpenGL -> DirectX green channel
    role = {'Color': 'BaseColor', 'NormalGL': 'Normal', 'ORM': 'ORM'}[kind]
    dst = bpy.data.images.new(f'T_{a.name}_{role}', w, h, alpha=False)
    dst.colorspace_settings.name = 'sRGB' if role == 'BaseColor' else 'Non-Color'
    dst.pixels = px.ravel()
    path = out / f'T_{a.name}_{role}.png'
    dst.filepath_raw = str(path)
    dst.file_format = 'PNG'
    dst.save()
    tex[role] = path.name
gen_tris = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == 'MESH')
bpy.ops.wm.read_factory_settings(use_empty=True)

# ---------------------------------------------------------------- rig + clips
def import_fbx(path):
    before = set(bpy.data.objects)
    acts_before = set(bpy.data.actions)
    bpy.ops.import_scene.fbx(filepath=path, use_anim=True, ignore_leaf_bones=False)
    new = [o for o in bpy.data.objects if o not in before]
    return new, [ac for ac in bpy.data.actions if ac not in acts_before]

objs, actions = import_fbx(a.fbx[0])
arm = next(o for o in objs if o.type == 'ARMATURE')
mesh = next(o for o in objs if o.type == 'MESH' and o.parent == arm)
for o in objs:
    if o not in (arm, mesh):
        bpy.data.objects.remove(o, do_unlink=True)
if a.uv:
    # clean layout from reuv_bake.py (same FBX, same import options -> same loop order; checked)
    lv = np.zeros(len(mesh.data.loops), dtype=np.int32)
    mesh.data.loops.foreach_get('vertex_index', lv)
    assert np.array_equal(lv, np.load(Path(a.uv) / 'loop_verts.npy')), 'reuv mesh does not match the rig mesh'
    assert len(mesh.data.uv_layers) == 1
    mesh.data.uv_layers.active.data.foreach_set('uv', np.load(Path(a.uv) / 'uv_new.npy').ravel())
    print('UV_REPLACED', len(lv), flush=True)
for extra in a.fbx[1:]:
    new, acts = import_fbx(extra)
    actions += acts
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
def remove_hip_drift(action):
    """Tripo 'in place' clips only pin Root; Hip still travels forward (run 2.5 m / cycle) and snaps back
    when the loop restarts -> visible teleport in game. Subtract the linear XY drift of Hip over the clip
    (keeps the natural sway/bob) and return the removed ground speed in armature units per second."""
    arm.animation_data.action = action
    f0, f1 = (int(v) for v in action.frame_range)
    pb = arm.pose.bones['Hip']
    scene = bpy.context.scene
    frames = list(range(f0, f1 + 1))
    mats = []
    for f in frames:
        scene.frame_set(f)
        mats.append(pb.matrix.copy())           # armature space
    drift = mats[-1].translation - mats[0].translation
    drift.z = 0.0
    fps = scene.render.fps / scene.render.fps_base
    speed = drift.length / max((f1 - f0) / fps, 1e-6)
    if drift.length < 0.05:
        return 0.0
    # the whole clip is also shifted forward (run starts ~0.5 units ahead of the rest-pose hip):
    # centre the de-trended XY path on the rest-pose hip so switching idle <-> run does not pop
    n = len(frames)
    mean = sum(((m.translation - drift * ((f - f0) / max(f1 - f0, 1))) for f, m in zip(frames, mats)), mats[0].translation * 0) / n
    rest = pb.bone.head_local
    shift = mean - rest
    shift.z = 0.0
    for f, m in zip(frames, mats):
        t = (f - f0) / max(f1 - f0, 1)
        scene.frame_set(f)
        corrected = m.copy()
        corrected.translation = m.translation - drift * t - shift
        pb.matrix = corrected
        bpy.context.view_layer.update()
        pb.keyframe_insert('location', frame=f)
    return speed


# Mixamo bone -> Tripo bone. Limbs are matched by bone direction (Mixamo rest = T-pose, Tripo rest = arms down);
# torso bones copy the rotation change only.
MIXAMO_MAP = {
    'Hips': 'Hip', 'Spine': 'Waist', 'Spine1': 'Spine01', 'Spine2': 'Spine02', 'Neck': 'NeckTwist01', 'Head': 'Head',
    'LeftShoulder': 'L_Clavicle', 'LeftArm': 'L_Upperarm', 'LeftForeArm': 'L_Forearm', 'LeftHand': 'L_Hand',
    'RightShoulder': 'R_Clavicle', 'RightArm': 'R_Upperarm', 'RightForeArm': 'R_Forearm', 'RightHand': 'R_Hand',
    'LeftUpLeg': 'L_Thigh', 'LeftLeg': 'L_Calf', 'LeftFoot': 'L_Foot', 'LeftToeBase': 'L_ToeBase',
    'RightUpLeg': 'R_Thigh', 'RightLeg': 'R_Calf', 'RightFoot': 'R_Foot', 'RightToeBase': 'R_ToeBase',
}
DIRECTION_MATCHED = {'Clavicle', 'Upperarm', 'Forearm', 'Hand', 'Thigh', 'Calf', 'Foot', 'ToeBase'}
MIXAMO_GRIP = {}   # side -> [grip line of the Mixamo hand in the Tripo rest pose (world), one per clip]
REZERO = {c: [tuple(map(int, w.split('-'))) for w in ws.split(',')] for c, ws in (r.split('=') for r in (a.rezero or []))}
LUNGES = {}   # clip -> [{start, end, travel_m: [x forward, y left]}] (rest-pose world, character units)
EXAGGERATE = {c: float(k) for c, k in (e.split('=') for e in (a.exaggerate or []))}
ATTACK_BODY = {}
for spec_ in a.attack_body or []:
    c_, rest_ = spec_.split('=', 1)
    prm_, wins_ = rest_.split('@', 1)
    ATTACK_BODY[c_] = (tuple(float(x) for x in prm_.split(':')), [tuple(int(x) for x in w.split(':')) for w in wins_.split(',')])
EXAGGERATE_BONES = ('Waist', 'Spine01', 'Spine02')
EXAG_STATS = {}   # (bone, window start) -> (max turn from window start, exaggerated) degrees, printed per clip


def retarget_mixamo(path, action_name):
    """World-space retarget: for each mapped bone, target_world = G * S * Rs^-1 * G^-1 * C * Rt
    (S/Rs = Mixamo posed/rest world rotation, Rt = Tripo rest, G = Mixamo facing (-Y) -> Tripo facing (+X),
    C = swing from the Tripo rest bone direction to the Mixamo rest bone direction for limbs, identity for the torso).
    Hip height change is scaled by leg length. Horizontal hip travel (4-27; it used to be dropped for every clip, which
    pinned the pelvis while the feet stepped - attacks looked like a post swinging its arms):
      locomotion (clip name has run / walk): the steady forward travel is removed (clip plays in place, the game
      matches its speed), the sway around it stays on the hip;
      --rezero clips (attacks): the hip carries the travel, restarting at 0 at each game window's start frame; the
      travel over each window is written to Hero.json lunges and the game moves the capsule by it when the swing
      ends (Unreal root motion was tried first: in the single-node player one swing threw the hero 63 m);
      everything else (idles): the whole travel stays on the hip (weight shift)."""
    from mathutils import Matrix, Quaternion
    before = set(bpy.data.objects)
    acts_before = set(bpy.data.actions)
    bpy.ops.import_scene.fbx(filepath=path, use_anim=True, ignore_leaf_bones=True)
    src = next(o for o in bpy.data.objects if o not in before and o.type == 'ARMATURE')
    src_action = next(ac for ac in bpy.data.actions if ac not in acts_before)
    prefix = next(b.name.split(':')[0] + ':' for b in src.data.bones if ':' in b.name)
    G = Matrix.Rotation(np.pi / 2, 3, 'Z')
    tw = arm.matrix_world.to_3x3().normalized()
    sw = src.matrix_world.to_3x3().normalized()

    def rot(m):
        return m.to_3x3().normalized()

    src.animation_data.action = None
    bpy.context.view_layer.update()
    rs = {m: sw @ rot(src.data.bones[prefix + m].matrix_local) for m in MIXAMO_MAP}
    swing = {}
    for m, t in MIXAMO_MAP.items():
        rt = tw @ rot(arm.data.bones[t].matrix_local)
        if any(k in t for k in DIRECTION_MATCHED):
            d_src = G @ (rs[m] @ Vector((0, 1, 0)))
            d_tgt = rt @ Vector((0, 1, 0))
            swing[t] = d_tgt.rotation_difference(d_src).to_matrix()
        else:
            swing[t] = Matrix.Identity(3)
    src_hip_rest = src.matrix_world @ src.data.bones[prefix + 'Hips'].head_local
    tgt_hip_bone = arm.data.bones['Hip']
    scale = (arm.matrix_world @ tgt_hip_bone.head_local).z / max(src_hip_rest.z, 1e-6)
    inv_map = {t: m for m, t in MIXAMO_MAP.items()}

    src.animation_data.action = src_action
    f0, f1 = (int(v) for v in src_action.frame_range)
    # ground speed of the clip (horizontal hip travel, target units per second) -> anim play rate in game
    scene_ = bpy.context.scene
    scene_.frame_set(f0)
    h0 = src.matrix_world @ src.pose.bones[prefix + 'Hips'].head
    scene_.frame_set(f1)
    h1 = src.matrix_world @ src.pose.bones[prefix + 'Hips'].head
    travel = (h1 - h0)
    travel.z = 0.0
    fps = scene_.render.fps / scene_.render.fps_base
    ground_speed = travel.length * scale / max((f1 - f0) / fps, 1e-6)
    locomotion = any(k in action_name.lower() for k in ('run', 'walk'))
    windows = REZERO.get(action_name.split('_', 1)[-1], [])
    hz = {}
    for f in range(f0, f1 + 1):
        scene_.frame_set(f)
        d = G @ (src.matrix_world @ src.pose.bones[prefix + 'Hips'].head - src_hip_rest) * scale
        hz[f] = Vector((d.x, d.y, 0.0))
    ramp = (hz[f1] - hz[f0]) / max(f1 - f0, 1)
    hip_extra, root_extra = {}, {}
    for f in range(f0, f1 + 1):
        rel = hz[f] - hz[f0]
        if locomotion:
            hip_extra[f], root_extra[f] = rel - ramp * (f - f0), Vector()
        else:   # attack windows re-zeroed at their start frame; idles keep the whole travel (weight shift)
            base = max((w0 for w0, _ in windows if w0 <= f), default=f0)
            hip_extra[f], root_extra[f] = hz[f] - hz[base], Vector()
    if windows:
        LUNGES[action_name.split('_', 1)[-1]] = [{'start': w0, 'end': w1, 'travel_m': [round((hz[w1] - hz[w0]).x, 4), round((hz[w1] - hz[w0]).y, 4)]}
                                                 for w0, w1 in windows]
    new = bpy.data.actions.new(action_name)
    new.use_fake_user = True
    arm.animation_data.action = new
    scene = bpy.context.scene
    bones = list(arm.data.bones)          # parents come before children
    for side, mside in (('R', 'Right'), ('L', 'Left')):
        # 4-26: the Mixamo hand's grip line (index knuckle - pinky knuckle, sword clips curl the fingers round the
        # handle) carried into the Tripo rest hand -> the direction a held weapon's handle must run in this rig
        if prefix + f'{mside}HandIndex1' not in src.data.bones or f'{side}_Hand' not in arm.data.bones:
            continue
        scene.frame_set(f0)
        S = sw @ rot(src.pose.bones[prefix + f'{mside}Hand'].matrix)
        rt = tw @ rot(arm.data.bones[f'{side}_Hand'].matrix_local)
        T = G @ S @ rs[f'{mside}Hand'].inverted() @ G.inverted() @ swing[f'{side}_Hand'] @ rt     # posed hand, world
        pos = lambda n: src.matrix_world @ src.pose.bones[prefix + n].head
        k = G @ (pos(f'{mside}HandIndex1') - pos(f'{mside}HandPinky1')).normalized()
        MIXAMO_GRIP.setdefault(side, []).append(rt @ T.inverted() @ k)
    exag_k = EXAGGERATE.get(action_name.split('_', 1)[-1], 1.0)
    raw_q = {}                             # (bone, frame) -> unexaggerated basis rotation
    for f in range(f0, f1 + 1):
        scene.frame_set(f)
        world = {}                         # target bone -> armature-space 4x4
        for b in bones:
            L = b.matrix_local
            if b.parent:
                M = world[b.parent.name] @ b.parent.matrix_local.inverted() @ L
            else:
                M = L.copy()
                M.translation += root_extra[f]
            m = inv_map.get(b.name)
            if m:
                S = sw @ rot(src.pose.bones[prefix + m].matrix)
                rt = tw @ rot(L)
                T = G @ S @ rs[m].inverted() @ G.inverted() @ swing[b.name] @ rt
                T = tw.inverted() @ T
                M = Matrix.Translation(M.translation) @ T.to_4x4()
                if m == 'Hips':
                    d = src.matrix_world @ src.pose.bones[prefix + 'Hips'].head - src_hip_rest
                    M.translation.z += d.z * scale
                    M.translation += hip_extra[f]
            world[b.name] = M
            pb = arm.pose.bones[b.name]
            basis = (L.inverted() @ b.parent.matrix_local @ world[b.parent.name].inverted() @ M) if b.parent else L.inverted() @ M
            loc, q, _ = basis.decompose()
            if exag_k != 1.0 and b.name in EXAGGERATE_BONES and windows:
                # children were solved against the unexaggerated parent, so they keep their local pose and ride along
                raw_q[b.name, f] = q.copy()
                win = next(((w0, w1) for w0, w1 in windows if w0 <= f <= w1), None)
                if win:
                    q0 = raw_q.get((b.name, win[0]), q)
                    delta = q0.inverted() @ q
                    if delta.w < 0:
                        delta.negate()
                    axis, angle = delta.to_axis_angle()
                    env = np.sin(np.pi * (f - win[0]) / max(win[1] - win[0], 1))
                    q = q0 @ Quaternion(axis, angle * (1.0 + (exag_k - 1.0) * env))
                    key = (b.name, win[0])
                    EXAG_STATS[key] = max(EXAG_STATS.get(key, (0, 0)), (np.degrees(angle), np.degrees(angle * (1.0 + (exag_k - 1.0) * env))))
            pb.rotation_mode = 'QUATERNION'
            pb.rotation_quaternion = q
            pb.location = loc
            pb.keyframe_insert('rotation_quaternion', frame=f)
            pb.keyframe_insert('location', frame=f)
    for (bn, w0), (d0, d1) in sorted(EXAG_STATS.items()):
        if exag_k != 1.0:
            print(f'EXAGGERATE {action_name} {bn} window {w0}: max turn {d0:.1f} -> {d1:.1f} deg', flush=True)
    EXAG_STATS.clear()
    for o in list(bpy.data.objects):
        if o not in before:
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.actions.remove(src_action)
    new['ground_speed'] = ground_speed
    return new


clips = []
for ac in actions:
    clip = ac.name.split('|')[-1]
    ac.name = f'{a.name}_{clip}'
    ac.use_fake_user = True
    speed = remove_hip_drift(ac) if clip in ('run', 'walk') else 0.0
    clips.append({'name': ac.name, 'frames': [int(v) for v in ac.frame_range],
                  'removed_ground_speed_units_per_s': round(speed, 4)})

for spec in a.mixamo or []:
    clip, path = spec.split('=', 1)
    ac = retarget_mixamo(path, f'{a.name}_{clip}')
    if clip in ATTACK_BODY:
        import exaggerate_attack
        (st, cr, le), wins = ATTACK_BODY[clip]
        travel = exaggerate_attack.apply(arm, ac, wins, step=st, crouch=cr, lean=le,
                                        body_lead=clip in a.attack_body_lead, body_drive=clip in a.attack_body_drive,
                                        drive_scale=dict(e.split('=') for e in a.attack_drive_scale).get(clip, 1.0),
                                        log=lambda m: print(m, flush=True))
        for w in LUNGES.get(clip, []):
            if w['start'] in travel:
                w['travel_m'] = [round(travel[w['start']].x, 4), round(travel[w['start']].y, 4)]
        print('ATTACK_BODY', clip, LUNGES.get(clip), flush=True)
    clips.append({'name': ac.name, 'frames': [int(v) for v in ac.frame_range], 'source': f'mixamo:{Path(path).name}',
                  'removed_ground_speed_units_per_s': round(float(ac.get('ground_speed', 0.0)), 4)})

arm.name = 'Armature'           # Unreal drops a root node named Armature
mesh.name = f'SK_{a.name}'
mesh.data.name = f'SK_{a.name}'


def swap_in_baked_mesh(rig_mesh):
    """Replace the rigged Tripo mesh by the baked low-poly (different generation of the same design):
    fit scale/position to the rest-pose bounds, try the 4 yaw turns and keep the one closest to the rig mesh,
    then copy skin weights from the nearest rig-mesh face and bind to the same armature."""
    from mathutils import Matrix, kdtree
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(Path(a.baked) / baked_info['glb']))
    new = next(o for o in bpy.data.objects if o not in before and o.type == 'MESH')
    for o in bpy.data.objects:
        if o not in before and o is not new:
            bpy.data.objects.remove(o, do_unlink=True)
    new.parent = None
    ref_pts = np.array([rig_mesh.matrix_world @ v.co for v in rig_mesh.data.vertices])   # undeformed rest shape
    tree = kdtree.KDTree(len(ref_pts))
    for i, pt in enumerate(ref_pts):
        tree.insert(pt, i)
    tree.balance()
    base = np.array([new.matrix_world @ v.co for v in new.data.vertices])
    rlo, rhi = ref_pts.min(0), ref_pts.max(0)
    best = None
    for k in range(4):
        rz = np.array(Matrix.Rotation(k * np.pi / 2, 3, 'Z'))
        pts = base @ rz.T
        lo, hi = pts.min(0), pts.max(0)
        sc = (rhi[2] - rlo[2]) / max(hi[2] - lo[2], 1e-6)
        off = np.array([(rlo[0] + rhi[0]) / 2 - sc * (lo[0] + hi[0]) / 2, (rlo[1] + rhi[1]) / 2 - sc * (lo[1] + hi[1]) / 2, rlo[2] - sc * lo[2]])
        sample = pts[:: max(1, len(pts) // 4000)] * sc + off
        err = float(np.mean([tree.find(pt)[2] for pt in sample]))
        if best is None or err < best[0]:
            best = (err, k, sc, off)
    err, k, sc, off = best
    new.matrix_world = Matrix.Translation(off) @ Matrix.Scale(sc, 4) @ Matrix.Rotation(k * np.pi / 2, 4, 'Z') @ new.matrix_world
    for o in bpy.context.view_layer.objects:
        o.select_set(o == new)
    bpy.context.view_layer.objects.active = new
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    height = rhi[2] - rlo[2]
    print(f'BAKED_FIT yaw={k * 90} scale={sc:.4f} mean_dist={err:.4f} ({err / height * 100:.2f}% of height)', flush=True)
    arm.data.pose_position = 'REST'                 # the source mesh is sampled deformed otherwise
    bpy.context.view_layer.update()
    dt = new.modifiers.new('Weights', 'DATA_TRANSFER')
    dt.object = rig_mesh
    dt.use_vert_data = True
    dt.data_types_verts = {'VGROUP_WEIGHTS'}
    dt.vert_mapping = 'POLYINTERP_NEAREST'
    dt.layers_vgroup_select_src = 'ALL'
    dt.layers_vgroup_select_dst = 'NAME'
    bpy.ops.object.datalayout_transfer(modifier=dt.name)
    bpy.ops.object.modifier_apply(modifier=dt.name)
    arm.data.pose_position = 'POSE'
    unweighted = sum(1 for v in new.data.vertices if not any(g.weight > 0 for g in v.groups))
    print(f'BAKED_WEIGHTS unweighted_vertices={unweighted}/{len(new.data.vertices)}', flush=True)
    new.parent = arm
    am = new.modifiers.new('Armature', 'ARMATURE')
    am.object = arm
    bpy.data.objects.remove(rig_mesh, do_unlink=True)
    return new, float(err / height)


if a.baked:
    mesh, fit_error = swap_in_baked_mesh(mesh)     # keeps the baked smooth-by-angle normals
    mesh.name = f'SK_{a.name}'
    mesh.data.name = f'SK_{a.name}'
else:
    # Tripo FBX carries flat custom split normals -> faceted in Unreal. Drop them and shade smooth.
    bpy.context.view_layer.objects.active = mesh
    for o in bpy.context.view_layer.objects:
        o.select_set(o == mesh)
    if mesh.data.has_custom_normals:
        bpy.ops.mesh.customdata_custom_splitnormals_clear()
    for poly in mesh.data.polygons:
        poly.use_smooth = True
mat = bpy.data.materials.new(f'M_{a.name}')
mesh.data.materials.clear()
mesh.data.materials.append(mat)


def face_classes_from_parts(glb, json_path):
    """Per-face class of `mesh` from a Tripo segmentation (other mesh of the same model, different topology):
    fit the part point cloud onto the rest-pose mesh (4 yaw turns, height scale, bounds), nearest part per face."""
    from mathutils import Matrix, kdtree
    labels = json.loads(Path(json_path).read_text(encoding='utf-8'))
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=glb)
    pts, cls = [], []
    for o in [o for o in bpy.data.objects if o not in before and o.type == 'MESH']:
        c = labels.get(o.name, {}).get('class', 'fur')
        vs = list(o.data.vertices)
        for v in vs[::max(1, len(vs) // 3000)]:
            pts.append(o.matrix_world @ v.co)
            cls.append(c)
    for o in list(bpy.data.objects):
        if o not in before:
            bpy.data.objects.remove(o, do_unlink=True)
    P = np.array(pts)
    M = np.array([mesh.matrix_world @ v.co for v in mesh.data.vertices])
    mtree = kdtree.KDTree(len(M))
    for i, x in enumerate(M):
        mtree.insert(x, i)
    mtree.balance()
    mlo, mhi = M.min(0), M.max(0)
    best = None
    for k in range(4):
        rz = np.array(Matrix.Rotation(k * np.pi / 2, 3, 'Z'))
        Q = P @ rz.T
        lo, hi = Q.min(0), Q.max(0)
        sc = (mhi[2] - mlo[2]) / max(hi[2] - lo[2], 1e-6)
        off = (mlo + mhi) / 2 - sc * (lo + hi) / 2
        off[2] = mlo[2] - sc * lo[2]
        Q = Q * sc + off
        err = float(np.mean([mtree.find(q)[2] for q in Q[::max(1, len(Q) // 3000)]]))
        if best is None or err < best[0]:
            best = (err, k, Q)
    err, k, Q = best
    print(f'PARTS_FIT yaw={k * 90} mean_dist={err / (mhi[2] - mlo[2]) * 100:.2f}% of height', flush=True)
    ptree = kdtree.KDTree(len(Q))
    for i, q in enumerate(Q):
        ptree.insert(q, i)
    ptree.balance()
    return [cls[ptree.find(mesh.matrix_world @ poly.center)[1]] for poly in mesh.data.polygons]


cloth_faces = 0
face_cls = face_classes_from_parts(a.parts, a.parts_json) if a.parts else None


def texel_class(r, g, b, metal):
    mx, mn = max(r, g, b), min(r, g, b)
    s = (mx - mn) / mx if mx > 1e-4 else 0.0
    d = max(mx - mn, 1e-4)
    hue = (((g - b) / d) % 6 if mx == r else ((b - r) / d + 2 if mx == g else (r - g) / d + 4)) / 6.0
    if metal > 0.45:
        return 'metal'
    if (hue < 0.035 or hue > 0.95) and s > 0.38 and mx > 0.18:
        return 'cloth'
    if 0.02 <= hue < 0.14 and s > 0.38 and 0.08 < mx < 0.6:
        return 'leather'
    if s < 0.38 and mx < 0.16:
        return 'darkcloth'
    if 0.02 <= hue < 0.16 and 0.15 <= s <= 0.38 and mx < 0.5:
        return 'fabric'            # brown-grey trousers / gambeson: warm but muted (grey fur is near-neutral)
    return 'fur'


def refine_with_texture(classes):
    """Coarse segmentations lump trousers / chest plates into 'fur' or 'cloth' parts. Per face, vote the texture
    class over its loops; soft parts (cloth / fur / tail) whose texels clearly say metal / leather / dark cloth
    (or cloth faces whose texels are not red) take the texture class (4-19)."""
    bimg = bpy.data.images.load(str(out / tex['BaseColor']))
    w, h = bimg.size
    base_px = np.array(bimg.pixels[:], dtype=np.float32).reshape(h, w, 4)
    oimg = bpy.data.images.load(str(out / tex['ORM']))
    oimg.colorspace_settings.name = 'Non-Color'
    ow, oh = oimg.size
    orm_px = np.array(oimg.pixels[:], dtype=np.float32).reshape(oh, ow, 4)
    uvl = mesh.data.uv_layers.active.data
    mw_ = mesh.matrix_world
    zz = [(mw_ @ v.co).z for v in mesh.data.vertices]
    z0_, zh_ = min(zz), max(zz) - min(zz)
    from collections import Counter
    changed = Counter()
    outc = list(classes)
    for i, poly in enumerate(mesh.data.polygons):
        c = classes[i]
        if c not in ('cloth', 'fur'):     # the tail keeps its label: its dark stripes read as dark cloth
            continue
        votes = Counter()
        for li in poly.loop_indices:
            u, v = uvl[li].uv
            r, g, b, _ = base_px[min(h - 1, max(0, int(v * h))), min(w - 1, max(0, int(u * w)))]
            m = orm_px[min(oh - 1, max(0, int(v * oh))), min(ow - 1, max(0, int(u * ow))), 2]
            votes[texel_class(r, g, b, m)] += 1
        t, n = votes.most_common(1)[0]
        if n * 2 <= len(poly.loop_indices):
            continue
        # fur: dark tabby stripes stay fur; trousers (fabric) / plates / straps leave it
        if t == 'fabric' and not (0.08 < ((mw_ @ poly.center).z - z0_) / zh_ < 0.55):
            continue                   # 'fabric' (muted brown) only means trousers below the waist; head fur is warm too
        if (c == 'fur' and t in ('metal', 'leather', 'fabric')) or (c == 'cloth' and t != 'cloth'):
            outc[i] = 'darkcloth' if t == 'fabric' else t
            changed[f'{c}->{t}'] += 1
    print('REFINED', dict(changed), flush=True)
    return outc


if face_cls:
    face_cls = refine_with_texture(face_cls)


def fix_orm_by_class(classes):
    """Tripo's metallic / roughness maps bleed metal into fur and cloth (fur metallic ~0.23, roughness ~0.65 ->
    it mirrors the blue sky in Unreal). Bake the per-face part class into UV space (Cycles emission, 16 px margin)
    and clamp: fur / tail / cloth / leather -> metallic 0 and a roughness floor; metal keeps its values (4-13)."""
    orm_path = out / tex['ORM']
    oimg = bpy.data.images.load(str(orm_path))
    oimg.colorspace_settings.name = 'Non-Color'
    w, h = oimg.size
    orm = np.array(oimg.pixels[:], dtype=np.float32).reshape(h, w, 4)
    tmp = mesh.copy()
    tmp.data = mesh.data.copy()
    tmp.modifiers.clear()
    tmp.parent = None
    for c in mesh.users_collection:
        c.objects.link(tmp)
    colours = {'metal': (1, 0, 0), 'leather': (0, 1, 0), 'cloth': (0, 0, 1), 'darkcloth': (0, 0, 1), 'fur': (0, 0, 0), 'tail': (0, 0, 0)}
    tmp.data.materials.clear()
    order = list(colours)
    for k in order:
        m = bpy.data.materials.new(f'cls_{k}')
        m.use_nodes = True
        nt = m.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        em = nt.nodes.new('ShaderNodeEmission')
        em.inputs[0].default_value = (*colours[k], 1)
        outn = nt.nodes.new('ShaderNodeOutputMaterial')
        nt.links.new(em.outputs[0], outn.inputs[0])
        timg = nt.nodes.new('ShaderNodeTexImage')
        nt.nodes.active = timg
        tmp.data.materials.append(m)
    for poly, c in zip(tmp.data.polygons, classes):
        poly.material_index = order.index(c if c in colours else 'fur')
    mask = bpy.data.images.new('cls_mask', w, h, alpha=False, float_buffer=True)
    mask.colorspace_settings.name = 'Non-Color'
    for m in tmp.data.materials:
        m.node_tree.nodes.active.image = mask
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 1
    scene.render.bake.margin = 16
    scene.render.bake.use_selected_to_active = False
    bpy.ops.object.select_all(action='DESELECT')
    tmp.select_set(True)
    bpy.context.view_layer.objects.active = tmp
    bpy.ops.object.bake(type='EMIT')
    mk = np.array(mask.pixels[:], dtype=np.float32).reshape(h, w, 4)
    # keep the part map for fix_textures.py (R metal, G leather, B cloth, black fur / tail); not an engine texture
    cls_img = bpy.data.images.new(f'T_{a.name}_Classes', w, h, alpha=False)
    cls_img.colorspace_settings.name = 'Non-Color'
    cls_img.pixels = np.concatenate([mk[..., :3], np.ones_like(mk[..., :1])], -1).ravel()
    cls_img.filepath_raw = str(out / f'T_{a.name}_Classes.png')
    cls_img.file_format = 'PNG'
    cls_img.save()
    metal_m, leather_m, cloth_m = mk[..., 0], mk[..., 1], mk[..., 2]
    fur_m = np.clip(1 - metal_m - leather_m - cloth_m, 0, 1)
    rough, metal = orm[..., 1].copy(), orm[..., 2].copy()
    floor = fur_m * 0.85 + cloth_m * 0.9 + leather_m * 0.65 + metal_m * 0.35
    orm[..., 1] = np.maximum(rough, floor)
    orm[..., 2] = metal * metal_m
    save_tex('ORM', orm)
    bpy.data.objects.remove(tmp, do_unlink=True)
    print('ORM_FIXED', {k: round(float(v.mean()), 3) for k, v in (('metal', metal_m), ('leather', leather_m), ('cloth', cloth_m), ('fur', fur_m))},
          'metallic mean', round(float(metal.mean()), 3), '->', round(float(orm[..., 2].mean()), 3), flush=True)


if face_cls:
    fix_orm_by_class(face_cls)
if a.cloth_classes or face_cls:
    # scarf / cape / waist cloth -> own section so Unreal can turn it into a Chaos cloth asset (4-12)
    mesh.data.materials.append(bpy.data.materials.new(f'M_{a.name}_Cloth'))
    if face_cls:
        for poly, c in zip(mesh.data.polygons, face_cls):
            if c == 'cloth':
                poly.material_index = 1
    else:
        cimg = bpy.data.images.load(str(Path(a.cloth_classes).resolve()))
        cw, ch = cimg.size
        cpx = np.array(cimg.pixels[:], dtype=np.float32).reshape(ch, cw, 4)
        uvl = mesh.data.uv_layers.active.data
        for poly in mesh.data.polygons:
            votes = 0
            for li in poly.loop_indices:
                u, v = uvl[li].uv
                r, g, b, _ = cpx[min(ch - 1, max(0, int(v * ch))), min(cw - 1, max(0, int(u * cw)))]
                votes += (r > 0.5 and g < 0.3 and b < 0.3)
            if votes * 2 > len(poly.loop_indices):
                poly.material_index = 1
    # close holes: texel classification leaves streaks of body faces inside the cape -> the cloth would tear there
    from collections import defaultdict
    edge_faces = defaultdict(list)
    for poly in mesh.data.polygons:
        for ek in poly.edge_keys:
            edge_faces[ek].append(poly.index)
    neighbours = [set() for _ in mesh.data.polygons]
    for fs in edge_faces.values():
        for f in fs:
            neighbours[f].update(x for x in fs if x != f)
    for _ in range(4):
        flip = [p.index for p in mesh.data.polygons if p.material_index == 0 and neighbours[p.index]
                and sum(mesh.data.polygons[n].material_index == 1 for n in neighbours[p.index]) * 3 >= len(neighbours[p.index]) * 2]
        for f in flip:
            mesh.data.polygons[f].material_index = 1
    cloth_faces = sum(p.material_index == 1 for p in mesh.data.polygons)
    print(f'CLOTH_FACES {cloth_faces}/{len(mesh.data.polygons)}', flush=True)

    # tail: fur behind the body below the waist (rest pose faces +X) -> its own section, simulated like the cape
    mw = mesh.matrix_world
    zs = [(mw @ v.co).z for v in mesh.data.vertices]
    z0, hgt = min(zs), max(zs) - min(zs)
    mesh.data.materials.append(bpy.data.materials.new(f'M_{a.name}_Tail'))
    tail_idx = len(mesh.data.materials) - 1
    tail_faces = 0
    for i, poly in enumerate(mesh.data.polygons):
        c = mw @ poly.center
        is_tail = face_cls[i] == 'tail' if face_cls else (c.x < -0.102 * hgt and c.z - z0 < 0.6 * hgt)
        if poly.material_index == 0 and is_tail:
            poly.material_index = tail_idx
            tail_faces += 1
    print(f'TAIL_FACES {tail_faces}', flush=True)

    def make_sim_proxy(src_idx, slot_name, target_faces):
        """Welded, seam-free, low-res copy of the faces in slot src_idx, in a new slot. Unreal builds the cloth from it
        (render vertices are split at every UV seam -> the sim would tear); the visible section is skinned to it."""
        import bmesh
        mesh.data.materials.append(bpy.data.materials.new(slot_name))
        sim_idx = len(mesh.data.materials) - 1
        sim = mesh.copy()
        sim.data = mesh.data.copy()
        sim.name = slot_name
        for c in mesh.users_collection:
            c.objects.link(sim)
        bm = bmesh.new()
        bm.from_mesh(sim.data)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index != src_idx], context='FACES')
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.004)
        bm.to_mesh(sim.data)
        bm.free()
        bpy.ops.object.select_all(action='DESELECT')
        sim.select_set(True)
        bpy.context.view_layer.objects.active = sim
        dec = sim.modifiers.new('Decimate', 'DECIMATE')
        dec.ratio = min(1.0, target_faces / max(len(sim.data.polygons), 1))
        bpy.ops.object.modifier_apply(modifier=dec.name)
        if sim.data.has_custom_normals:
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
        for poly in sim.data.polygons:
            poly.use_smooth = True
            poly.material_index = sim_idx
        for loop_uv in sim.data.uv_layers.active.data:
            loop_uv.uv = (0.5, 0.5)
        bpy.ops.object.select_all(action='DESELECT')
        mesh.select_set(True)
        sim.select_set(True)
        bpy.context.view_layer.objects.active = mesh
        bpy.ops.object.join()
        print(f'CLOTH_SIM {slot_name} faces={sum(p.material_index == sim_idx for p in mesh.data.polygons)}', flush=True)

    if cloth_faces:                  # no cape on the body (deathknight: the cape is a separate mesh) -> no empty sim section
        make_sim_proxy(1, f'M_{a.name}_ClothSim', 3000)
    make_sim_proxy(tail_idx, f'M_{a.name}_TailSim', 600)

if face_cls and a.fur_shells > 0:
    # shell fur (4-14): N offset copies of the fur faces (not the cloth-simulated tail: shells could not follow
    # the sim), same skin weights / UV0, shell height 0..1 in UV1.x -> Unreal masks strands per shell.
    # Alembic groom from Blender carries no per-strand colour, shells keep the tabby texture.
    import bmesh
    mw = mesh.matrix_world
    zs = [(mw @ v.co).z for v in mesh.data.vertices]
    hgt = max(zs) - min(zs)
    if 'ShellH' not in mesh.data.uv_layers:
        mesh.data.uv_layers.new(name='ShellH')
    mesh.data.uv_layers.active_index = 0
    for loop_uv in mesh.data.uv_layers['ShellH'].data:
        loop_uv.uv = (0.0, 0.0)
    mesh.data.materials.append(bpy.data.materials.new(f'M_{a.name}_Fur'))
    fur_idx = len(mesh.data.materials) - 1
    base = mesh.copy()
    base.data = mesh.data.copy()
    for c in mesh.users_collection:
        c.objects.link(base)
    bm = bmesh.new()
    bm.from_mesh(base.data)
    fur_faces = {i for i, c in enumerate(face_cls) if c == 'fur'}
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in fur_faces or f.material_index != 0], context='FACES')
    bm.to_mesh(base.data)
    bm.free()
    base.data.shade_smooth()
    length = a.fur_length * hgt
    shells = []
    for i in range(1, a.fur_shells + 1):
        h = i / a.fur_shells
        sh = base.copy()
        sh.data = base.data.copy()
        for c in mesh.users_collection:
            c.objects.link(sh)
        normals = [v.normal.copy() for v in sh.data.vertices]
        for v, nrm in zip(sh.data.vertices, normals):
            v.co = v.co + nrm * (length * h) / max(mw.to_scale().x, 1e-6)
        for poly in sh.data.polygons:
            poly.material_index = fur_idx
        for loop_uv in sh.data.uv_layers['ShellH'].data:
            loop_uv.uv = (h, 0.0)
        shells.append(sh)
    bpy.data.objects.remove(base, do_unlink=True)
    bpy.ops.object.select_all(action='DESELECT')
    mesh.select_set(True)
    for sh in shells:
        sh.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    bpy.ops.object.join()
    print(f'FUR_SHELLS layers={a.fur_shells} faces_per_layer={len(fur_faces)} length={length:.4f}', flush=True)

# centre the root bone on the origin (rest pose); bone-local animation is unaffected
root = arm.data.bones[0]
offset = arm.matrix_world @ root.head_local
arm.location.x -= offset.x
arm.location.y -= offset.y
bpy.context.view_layer.update()
for o in bpy.context.view_layer.objects:
    o.select_set(o in (arm, mesh))
bpy.context.view_layer.objects.active = arm
bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)

# rest-pose height of the skinned mesh
arm.animation_data.action = None
bpy.context.view_layer.update()
# (shell-fur and cloth-sim proxy layers are excluded: fur on the head must not shrink the character in Unreal)
skip = {i for i, m in enumerate(mesh.data.materials) if m and m.name.endswith(('_Fur', 'Sim'))}
body_verts = {vi for pl in mesh.data.polygons if pl.material_index not in skip for vi in pl.vertices}
zs = [(mesh.matrix_world @ mesh.data.vertices[i].co).z for i in body_verts]
height = max(zs) - min(zs)
tris = sum(len(p.vertices) - 2 for p in mesh.data.polygons)


def widen_fist_hole(side, radius):
    """Modelled fist with a weapon hole (deathknight, 4-26): open the grip tunnel to the handle radius.
    Grip direction = the Mixamo hand's index-pinky knuckle line carried into this rest pose (MIXAMO_GRIP, from the
    sword clips), so the weapon also swings the way the clips were animated. Rest pose, hand faces only (hand weight
    >= 0.5; the A-pose thigh must not count as wall). Within 40 deg of that direction, find the axis whose
    axis-parallel rays leave the widest free region that is closed all round (flood fill from the scan border:
    a slot open on one side does not count - 4-26 first try put the sword in the thumb slot, 53 deg off).
    Then inflate the fist about the tunnel: r in [r_tunnel, r_tunnel + 3% of height] maps linearly onto
    [radius, same outer end] (monotonic, no folds; fingers keep most of their thickness, the fist grows a little)."""
    import bmesh, math
    from collections import deque
    from mathutils import Matrix
    from mathutils.bvhtree import BVHTree
    mw = mesh.matrix_world
    mwi = mw.inverted()
    gi = mesh.vertex_groups[f'{side}_Hand'].index
    wts = np.zeros(len(mesh.data.vertices))
    for v in mesh.data.vertices:
        for x in v.groups:
            if x.group == gi:
                wts[v.index] = x.weight
    bm = bmesh.new()
    bm.from_mesh(mesh.data)
    bm.transform(mw)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index in skip or min(wts[v.index] for v in f.verts) < 0.5],
                     context='FACES')
    tree = BVHTree.FromBMesh(bm)
    live = [v.co.copy() for v in bm.verts if v.link_faces]
    hc = sum(live, Vector()) / max(1, len(live))
    bm.free()
    hh = arm.matrix_world @ arm.data.bones[f'{side}_Hand'].head_local
    fh = arm.matrix_world @ arm.data.bones[f'{side}_Forearm'].head_local
    d = (hh - fh).normalized()
    fl = (hh - fh).length
    if not MIXAMO_GRIP.get(side):
        raise SystemExit(f'FIST_HOLE {side}: needs --mixamo clips with finger bones (grip direction)')
    want = sum(MIXAMO_GRIP[side], Vector()).normalized()
    R, depth = 0.032 * height, 0.055 * height      # scan window half-width / ray half-length

    def scan(ax, centre, n):
        step = 2 * R / (n - 1)
        u = d - ax * d.dot(ax)
        u = u.normalized() if u.length > 1e-4 else ax.orthogonal().normalized()
        v = ax.cross(u)
        free = np.array([[tree.ray_cast(centre + u * (-R + i * step) + v * (-R + j * step) - ax * depth, ax, 2 * depth)[0] is None
                          for j in range(n)] for i in range(n)])
        outside = np.zeros_like(free)
        q = deque((i, j) for i in range(n) for j in range(n) if (i in (0, n - 1) or j in (0, n - 1)) and free[i, j])
        for i, j in q:
            outside[i, j] = True
        while q:
            i, j = q.popleft()
            for a_, b_ in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if 0 <= a_ < n and 0 <= b_ < n and free[a_, b_] and not outside[a_, b_]:
                    outside[a_, b_] = True
                    q.append((a_, b_))
        closed = free & ~outside
        if not closed.any():
            return 0.0, None
        wall = np.argwhere(~closed)
        best, at = -1.0, None
        for i, j in np.argwhere(closed):
            r = np.sqrt(((wall - (i, j)) ** 2).sum(1)).min()
            if r > best:
                best, at = r, (i, j)
        return (best - 0.5) * step, centre + u * (-R + at[0] * step) + v * (-R + at[1] * step)

    cands = []
    for el in range(-90, 91, 10):
        for az in range(0, 360, 10 if abs(el) < 90 else 360):
            e, z = math.radians(el), math.radians(az)
            ax = Vector((math.cos(e) * math.cos(z), math.cos(e) * math.sin(z), math.sin(e)))
            if math.degrees(ax.angle(want)) > 40:
                continue
            r, c = scan(ax, hc, 29)
            if c is not None:
                cands.append((r, -math.degrees(ax.angle(want)), ax, c))
    if not cands:
        raise SystemExit(f'FIST_HOLE {side}: no closed grip tunnel within 40 deg of the Mixamo grip line')
    _, _, ax, c = max(cands, key=lambda t: (round(t[0] / (0.001 * height)), t[1]))
    r0, c = scan(ax, c, 57)
    for _ in range(2):                             # refine the axis +-4 deg
        for da in (-4, 0, 4):
            for db in (-4, 0, 4):
                ax2 = (Matrix.Rotation(math.radians(da), 3, ax.orthogonal()) @
                       Matrix.Rotation(math.radians(db), 3, ax.cross(ax.orthogonal())) @ ax).normalized()
                r2, c2 = scan(ax2, c, 57)
                if c2 is not None and r2 > r0 and math.degrees(ax2.angle(want)) <= 40:
                    r0, ax, c = r2, ax2, c2
    outer = r0 + 0.03 * height
    moved = 0
    if radius > r0:
        for v in mesh.data.vertices:
            wgt = min(1.0, max(0.0, (wts[v.index] - 0.3) / 0.4))
            if wgt <= 0:
                continue
            p = mw @ v.co
            rv = (p - c) - ax * (p - c).dot(ax)
            r = rv.length
            if r < 1e-7 or r >= outer:
                continue
            r_new = radius + (max(r, r0) - r0) * (outer - radius) / (outer - r0)
            v.co = mwi @ (p + rv / r * (r_new - r) * wgt)
            moved += 1
        mesh.data.update()
    along = (c - hh).dot(d)
    perp = (c - hh) - d * along
    print(f'FIST_HOLE {side} tunnel_radius={r0 / height:.4f}H -> {max(radius, r0) / height:.4f}H moved_verts={moved} '
          f'axis={tuple(round(x, 3) for x in ax)} vs_mixamo_grip={math.degrees(ax.angle(want)):.0f}deg '
          f'mixamo_grip={tuple(round(x, 3) for x in want)} axis_vs_forearm={math.degrees(ax.angle(d)):.0f}deg', flush=True)
    return {'along_ratio': round(along / fl, 4), 'perp_m': [round(x, 4) for x in perp], 'hole_axis': [round(x, 4) for x in ax],
            'hole_radius_of_height': round(max(radius, r0) / height, 5), 'hole_radius_before_of_height': round(r0 / height, 5),
            'mixamo_grip_axis': [round(x, 4) for x in want]}


# fist centre relative to the wrist (hand bone head), rest pose: Unreal puts the weapon grip there (4-18).
# along = distance along forearm->hand in units of forearm length; perp = the rest of the offset in metres
# (Blender world: character faces +X, left = +Y).
grip = {}
for side in ('R', 'L'):
    g = mesh.vertex_groups.get(f'{side}_Hand')
    if not g or f'{side}_Forearm' not in arm.data.bones:
        continue
    pts = [mesh.matrix_world @ v.co for v in mesh.data.vertices if any(x.group == g.index and x.weight > 0.6 for x in v.groups)]
    if not pts:
        continue
    c = sum(pts, Vector()) / len(pts)
    hh = arm.matrix_world @ arm.data.bones[f'{side}_Hand'].head_local
    fh = arm.matrix_world @ arm.data.bones[f'{side}_Forearm'].head_local
    fl = (hh - fh).length
    d = (hh - fh).normalized()
    along = (c - hh).dot(d)
    perp = (c - hh) - d * along
    grip[side] = {'along_ratio': round(along / fl, 4), 'perp_m': [round(x, 4) for x in perp]}
def align_hand_to_grip(side, tunnel, want):
    """The fist tunnel (where the weapon sits) is not exactly the Mixamo grip line (deathknight: 28 deg). Turn the
    hand in every Mixamo clip by the constant rotation that carries the tunnel onto that line, so the weapon swings
    as animated (4-26). World rest C: tunnel -> want; bone-local Cl = L^-1 C L; pose basis' = basis @ Cl."""
    import math
    from mathutils import Quaternion
    tw = arm.matrix_world.to_3x3().normalized()
    L = arm.data.bones[f'{side}_Hand'].matrix_local.to_3x3().normalized()
    C = tunnel.rotation_difference(want).to_matrix()
    Cl = (L.inverted() @ tw.inverted() @ C @ tw @ L).to_quaternion()
    path = f'pose.bones["{side}_Hand"].rotation_quaternion'
    names = {c['name'] for c in clips if str(c.get('source', '')).startswith('mixamo:')}
    for ac in bpy.data.actions:
        if ac.name not in names:
            continue
        fcs = sorted((fc for fc in (ac.fcurves if hasattr(ac, 'fcurves') else []) if fc.data_path == path), key=lambda fc: fc.array_index)
        if len(fcs) != 4:
            fcs = sorted((fc for layer in ac.layers for strip in layer.strips for bag in strip.channelbags
                          for fc in bag.fcurves if fc.data_path == path), key=lambda fc: fc.array_index)
        for k in range(len(fcs[0].keyframe_points)):
            q = Quaternion([fc.keyframe_points[k].co[1] for fc in fcs]) @ Cl
            for i, fc in enumerate(fcs):
                fc.keyframe_points[k].co[1] = q[i]
        for fc in fcs:
            fc.update()
    print(f'ALIGN_HAND {side} rotated {math.degrees(tunnel.angle(want)):.1f}deg in {len(names)} mixamo clips', flush=True)
    return round(math.degrees(tunnel.angle(want)), 1)


for spec in a.fist_hole or []:
    side, frac = spec.split(':')
    grip[side] = widen_fist_hole(side, float(frac) * height)
    grip[side]['hand_turned_to_mixamo_deg'] = align_hand_to_grip(side, Vector(grip[side]['hole_axis']).normalized(),
                                                                 Vector(grip[side]['mixamo_grip_axis']).normalized())

def roll_hand_about_sword(action_name, deg, axis_world):
    """4-44: turn R_Hand by a constant angle about the equipped blade axis in every key of one clip. The mocap arm
    (hand leads, wrist releases the blade late) is kept; only the fixed grip-to-edge offset changes."""
    import math
    from mathutils import Quaternion
    tw = arm.matrix_world.to_3x3().normalized()
    L = arm.data.bones['R_Hand'].matrix_local.to_3x3().normalized()
    ax = ((tw @ L).inverted() @ Vector(axis_world)).normalized()
    Cl = Quaternion(ax, math.radians(deg))
    path = 'pose.bones["R_Hand"].rotation_quaternion'
    ac = bpy.data.actions[action_name]
    fcs = sorted((fc for fc in (ac.fcurves if hasattr(ac, 'fcurves') else []) if fc.data_path == path), key=lambda fc: fc.array_index)
    if len(fcs) != 4:
        fcs = sorted((fc for layer in ac.layers for strip in layer.strips for bag in strip.channelbags
                      for fc in bag.fcurves if fc.data_path == path), key=lambda fc: fc.array_index)
    for k in range(len(fcs[0].keyframe_points)):
        q = Quaternion([fc.keyframe_points[k].co[1] for fc in fcs]) @ Cl
        for i, fc in enumerate(fcs):
            fc.keyframe_points[k].co[1] = q[i]
    for fc in fcs:
        fc.update()
    print(f'EDGE_ROLL {action_name} {deg}deg about the sword axis', flush=True)

for spec in a.attack_edge_roll:
    if not a.attack_sword_axis:
        raise SystemExit('--attack-edge-roll requires the equipped --attack-sword-axis')
    clip, deg = spec.split('=')
    roll_hand_about_sword(f'{a.name}_{clip}', float(deg), [float(v) for v in a.attack_sword_axis.split(':')])

arm.animation_data.action = actions[0]
fbx = out / f'SK_{a.name}.fbx'
bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True, object_types={'ARMATURE', 'MESH'},
                         apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS', add_leaf_bones=False,
                         bake_anim=True, bake_anim_use_all_actions=True, bake_anim_use_nla_strips=False,
                         bake_anim_force_startend_keying=True, bake_anim_simplify_factor=0.0,
                         path_mode='STRIP', mesh_smooth_type='OFF', use_tspace=True,   # normals + MikkTSpace tangents -> UE (4-11)
                         armature_nodetype='NULL')
for c in clips:   # ground speed in "body heights per second" -> multiply by in-game height
    c['ground_speed_heights_per_s'] = round(c['removed_ground_speed_units_per_s'] / height, 4) if height else 0.0
info = {'name': a.name, 'fbx': fbx.name, 'rest_height_m': round(height, 4), 'triangles': tris,
        'generation_triangles_check': gen_tris, 'bones': len(arm.data.bones),
        'bone_names': [b.name for b in arm.data.bones], 'clips': clips, 'textures': tex,
        'root_offset_removed_m': [round(offset.x, 4), round(offset.y, 4)], 'grip': grip, 'lunges': LUNGES}
if a.baked:
    info['baked'] = {**baked_info, 'fit_mean_dist_of_height': round(fit_error, 4)}
(out / f'{a.name}.json').write_text(json.dumps(info, indent=1), encoding='utf-8')
if face_cls:
    # painted light / blobby metal -> clean metal F0 + roughness detail (4-20); system Python (cv2), not Blender's
    import subprocess
    subprocess.run(['python', str(Path(__file__).resolve().with_name('fix_textures.py')), str(out), a.name]
                   + (['--charts', str(Path(a.uv).resolve())] if a.uv else []) + a.texfix.split(), check=True)   # per-chart delight (4-22)
print('CHAR_DONE', json.dumps({k: v for k, v in info.items() if k != 'bone_names'}))
