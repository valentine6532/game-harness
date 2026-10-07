"""Build /Game/Maps/Plaza from the exported plaza_v2 assets (run with UnrealEditor-Cmd -run=pythonscript).

Steps: textures -> master materials -> env/prop static meshes -> characters (skeletal + clips)
-> level layout (workspace/plaza_v2/export/env/layout.json) -> lighting -> characters + weapons -> camera.
Re-runnable: assets are re-imported in place, the map is rebuilt from scratch.
"""
import json
import math
import os
import sys

import unreal

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from ue_common import (EAL, MEL, ASSET_TOOLS, SKIP_IMPORT, blender_to_ue, ensure_dir, import_file, log,
                       material_instance)

EXPORT = 'D:/HarnessPrograming/diablo/workspace/plaza_v2/export'

# An open editor keeps the map / materials / meshes loaded: this build then fails half-way (deletes refused,
# "Error saving ..."). Stop before touching anything.
import subprocess
_editors = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq UnrealEditor.exe', '/FO', 'CSV', '/NH'],
                          capture_output=True, text=True).stdout
if 'UnrealEditor.exe' in _editors:
    unreal.log_error('NYABLO BUILD_ABORTED: close the Unreal Editor first (UnrealEditor.exe is running)')
    raise SystemExit('editor open')
TEX_NORMAL = unreal.TextureCompressionSettings.TC_NORMALMAP
TEX_MASKS = unreal.TextureCompressionSettings.TC_MASKS

# ------------------------------------------------------------------ helpers
def import_texture(path, dest):
    name = os.path.splitext(os.path.basename(path))[0]
    obj_path = f'{dest}/{name}'
    import_file(path, dest)
    tex = EAL.load_asset(obj_path)
    if name.endswith('_Normal'):
        tex.set_editor_property('compression_settings', TEX_NORMAL)
        tex.set_editor_property('srgb', False)
    elif name.endswith(('_ORM', '_Height', '_Mask')):
        tex.set_editor_property('compression_settings', TEX_MASKS)
        tex.set_editor_property('srgb', False)
    EAL.save_asset(obj_path)
    return tex


def tex_param(mat, name, x, y, sampler=None, default=None):
    t = MEL.create_material_expression(mat, unreal.MaterialExpressionTextureSampleParameter2D, x, y)
    t.set_editor_property('parameter_name', name)
    if sampler is not None:
        t.set_editor_property('sampler_type', sampler)
    if default is not None:
        t.set_editor_property('texture', default)
    return t


def scalar(mat, name, val, x, y):
    s = MEL.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, x, y)
    s.set_editor_property('parameter_name', name)
    s.set_editor_property('default_value', val)
    return s


def vector(mat, name, val, x, y):
    v = MEL.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, x, y)
    v.set_editor_property('parameter_name', name)
    v.set_editor_property('default_value', unreal.LinearColor(*val))
    return v


def new_material(path):
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    pkg, name = path.rsplit('/', 1)
    return ASSET_TOOLS.create_asset(name, pkg, unreal.Material, unreal.MaterialFactoryNew())


def build_masters(defaults):
    """M_Env: tiled colour+normal (+tint, roughness/metallic scalars).
    M_Char: Tripo PBR (BaseColor, Normal, ORM = AO/Roughness/Metallic).
    M_Flat: plain colour. M_Banner: masked two-sided card."""
    ensure_dir('/Game/Materials')
    NORMAL = unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL
    MASKS = unreal.MaterialSamplerType.SAMPLERTYPE_MASKS
    P = unreal.MaterialProperty

    m = new_material('/Game/Materials/M_Env')
    bc = tex_param(m, 'BaseColor', -700, -100, default=defaults['color'])
    tint = vector(m, 'Tint', (1, 1, 1, 1), -700, 150)
    mul = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -350, -50)
    MEL.connect_material_expressions(bc, 'RGB', mul, 'A')
    MEL.connect_material_expressions(tint, '', mul, 'B')
    MEL.connect_material_property(mul, '', P.MP_BASE_COLOR)
    nrm = tex_param(m, 'Normal', -700, 300, NORMAL, defaults['normal'])
    MEL.connect_material_property(nrm, 'RGB', P.MP_NORMAL)
    MEL.connect_material_property(scalar(m, 'Roughness', 0.85, -700, 550), '', P.MP_ROUGHNESS)
    MEL.connect_material_property(scalar(m, 'Metallic', 0.0, -700, 650), '', P.MP_METALLIC)
    MEL.recompile_material(m)
    EAL.save_asset('/Game/Materials/M_Env')

    m = new_material('/Game/Materials/M_Char')
    # without the saved usage flag, -game (uncooked) swaps in the default grey material on skinned bodies
    m.set_editor_property('used_with_skeletal_mesh', True)
    bc = tex_param(m, 'BaseColor', -700, -150, default=defaults['color'])
    tint = vector(m, 'Tint', (1, 1, 1, 1), -700, 100)
    mul = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -350, -100)
    MEL.connect_material_expressions(bc, 'RGB', mul, 'A')
    MEL.connect_material_expressions(tint, '', mul, 'B')
    # hit flash driven per mesh by Custom Primitive Data[0] (no dynamic material copies needed)
    flash = scalar(m, 'Flash', 0.0, -700, 700)
    flash.set_editor_property('use_custom_primitive_data', True)
    flash.set_editor_property('primitive_data_index', 0)
    boost = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -250, 700)
    MEL.connect_material_expressions(mul, '', boost, 'A')
    MEL.connect_material_expressions(flash, '', boost, 'B')
    base = MEL.create_material_expression(m, unreal.MaterialExpressionAdd, -150, -100)
    MEL.connect_material_expressions(mul, '', base, 'A')
    MEL.connect_material_expressions(boost, '', base, 'B')
    MEL.connect_material_property(base, '', P.MP_BASE_COLOR)
    # glow mask (deathknight rune sword): Emissive texture x EmissiveColor (HDR), black / 0 on everything else
    glow_tex = tex_param(m, 'Emissive', -700, 1000, default=unreal.load_asset('/Engine/EngineResources/Black'))
    glow = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -350, 1000)
    MEL.connect_material_expressions(glow_tex, 'RGB', glow, 'A')
    MEL.connect_material_expressions(vector(m, 'EmissiveColor', (0, 0, 0, 1), -700, 1250), '', glow, 'B')
    emis = MEL.create_material_expression(m, unreal.MaterialExpressionAdd, -150, 800)
    MEL.connect_material_expressions(boost, '', emis, 'A')
    MEL.connect_material_expressions(glow, '', emis, 'B')
    MEL.connect_material_property(emis, '', P.MP_EMISSIVE_COLOR)
    nrm = tex_param(m, 'Normal', -700, 250, NORMAL, defaults['normal'])
    MEL.connect_material_property(nrm, 'RGB', P.MP_NORMAL)
    orm = tex_param(m, 'ORM', -700, 500, MASKS, defaults['orm'])
    MEL.connect_material_property(orm, 'R', P.MP_AMBIENT_OCCLUSION)
    MEL.connect_material_property(orm, 'G', P.MP_ROUGHNESS)
    MEL.connect_material_property(orm, 'B', P.MP_METALLIC)
    # fur / cloth read as wet plastic under the blue sky light at the default 0.5 specular (4-11). Non-metal
    # specular is scaled by roughness: rough fur / cloth (>= 0.85, ORM fixed per part in 4-13) get almost none,
    # smoother leather keeps a little; metal is driven by metallic and unaffected.
    spec_rough = MEL.create_material_expression(m, unreal.MaterialExpressionOneMinus, -500, 850)
    MEL.connect_material_expressions(orm, 'G', spec_rough, '')
    spec = MEL.create_material_expression(m, unreal.MaterialExpressionMultiply, -350, 850)
    MEL.connect_material_expressions(spec_rough, '', spec, 'A')
    MEL.connect_material_expressions(scalar(m, 'Specular', 1.0, -700, 850), '', spec, 'B')
    MEL.connect_material_property(spec, '', P.MP_SPECULAR)
    MEL.recompile_material(m)
    EAL.save_asset('/Game/Materials/M_Char')

    m = new_material('/Game/Materials/M_Flat')
    MEL.connect_material_property(vector(m, 'Color', (0.5, 0.5, 0.5, 1), -500, 0), '', P.MP_BASE_COLOR)
    MEL.connect_material_property(scalar(m, 'Roughness', 0.6, -500, 200), '', P.MP_ROUGHNESS)
    MEL.connect_material_property(scalar(m, 'Metallic', 0.0, -500, 300), '', P.MP_METALLIC)
    MEL.recompile_material(m)
    EAL.save_asset('/Game/Materials/M_Flat')

    m = new_material('/Game/Materials/M_Banner')
    m.set_editor_property('blend_mode', unreal.BlendMode.BLEND_MASKED)
    m.set_editor_property('two_sided', True)
    bc = tex_param(m, 'BaseColor', -600, 0, default=defaults['color'])
    MEL.connect_material_property(bc, 'RGB', P.MP_BASE_COLOR)
    MEL.connect_material_property(bc, 'A', P.MP_OPACITY_MASK)
    MEL.connect_material_property(scalar(m, 'Roughness', 0.85, -600, 300), '', P.MP_ROUGHNESS)
    MEL.recompile_material(m)
    EAL.save_asset('/Game/Materials/M_Banner')
    return {k: EAL.load_asset(f'/Game/Materials/{k}') for k in ('M_Env', 'M_Char', 'M_Flat', 'M_Banner')}


def build_fur_master(d):
    """M_FurShell (4-14): masked shell-fur layer. UV0 = the character atlas (colour, normal), UV1.x = shell height
    0..1 (process_character.py --fur-shells). A strand is visible on a shell while its height in T_FurStrands
    (tiled over UV0) is above the shell height, so strands taper toward the tips; roots are darkened."""
    P = unreal.MaterialProperty
    m = new_material('/Game/Materials/M_FurShell')
    m.set_editor_property('used_with_skeletal_mesh', True)
    m.set_editor_property('blend_mode', unreal.BlendMode.BLEND_MASKED)
    m.set_editor_property('opacity_mask_clip_value', 0.5)
    C = MEL.connect_material_expressions

    def E(cls, x, y):
        return MEL.create_material_expression(m, getattr(unreal, 'MaterialExpression' + cls), x, y)

    uv0 = E('TextureCoordinate', -1400, 0)
    uv1 = E('TextureCoordinate', -1400, 400)
    uv1.set_editor_property('coordinate_index', 1)
    h = E('ComponentMask', -1200, 400)
    h.set_editor_property('r', True)
    C(uv1, '', h, '')
    tiled = E('Multiply', -1200, 200)
    C(uv0, '', tiled, 'A')
    C(scalar(m, 'FurTiling', 8.0, -1400, 250), '', tiled, 'B')
    strands = tex_param(m, 'Strands', -1000, 200, unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR, d['strands'])
    C(tiled, '', strands, 'UVs')
    diff = E('Subtract', -700, 300)
    C(strands, 'R', diff, 'A')
    C(h, '', diff, 'B')
    sharp = E('Multiply', -550, 300)
    C(diff, '', sharp, 'A')
    C(scalar(m, 'StrandSharpness', 12.0, -700, 420), '', sharp, 'B')
    mask = E('Add', -400, 300)
    C(sharp, '', mask, 'A')
    C(scalar(m, 'MaskBias', 0.5, -550, 420), '', mask, 'B')
    MEL.connect_material_property(mask, '', P.MP_OPACITY_MASK)
    bc = tex_param(m, 'BaseColor', -1000, -250, default=d['color'])
    C(uv0, '', bc, 'UVs')
    root = E('LinearInterpolate', -700, -100)
    C(scalar(m, 'RootDarkness', 0.55, -900, -50), '', root, 'A')
    one = E('Constant', -900, 0)
    one.set_editor_property('r', 1.0)
    C(one, '', root, 'B')
    C(h, '', root, 'Alpha')
    col = E('Multiply', -500, -200)
    C(bc, 'RGB', col, 'A')
    C(root, '', col, 'B')
    tint = E('Multiply', -350, -200)
    C(col, '', tint, 'A')
    C(vector(m, 'Tint', (1, 1, 1, 1), -500, -80), '', tint, 'B')
    MEL.connect_material_property(tint, '', P.MP_BASE_COLOR)
    nrm = tex_param(m, 'Normal', -1000, 700, unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL, d['normal'])
    C(uv0, '', nrm, 'UVs')
    MEL.connect_material_property(nrm, 'RGB', P.MP_NORMAL)
    MEL.connect_material_property(scalar(m, 'Roughness', 0.9, -500, 700), '', P.MP_ROUGHNESS)
    MEL.connect_material_property(scalar(m, 'Specular', 0.1, -500, 800), '', P.MP_SPECULAR)
    MEL.recompile_material(m)
    EAL.save_asset('/Game/Materials/M_FurShell')
    return m


def build_ground_master(d):
    """M_Ground (4-10): realistic layered floor. World-aligned scanned PBR layers (Poly Haven, CC0):
    stone detail, dirt and grass. A 'Macro' texture on UV0 keeps a painted layout (the plaza rings / compass):
    its dark joints and the detail layer's own height grooves become the dirt mask, noise breaks it up.
    Stone colour = macro colour x detail luminance, so the layout colours survive while the surface gets real
    cracks, pores and roughness variation (the sparkle)."""
    P = unreal.MaterialProperty
    NORMAL = unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL
    MASKS = unreal.MaterialSamplerType.SAMPLERTYPE_MASKS
    m = new_material('/Game/Materials/M_Ground')
    C = MEL.connect_material_expressions

    def E(cls, x, y):
        return MEL.create_material_expression(m, getattr(unreal, 'MaterialExpression' + cls), x, y)

    def op(cls, a, b, x, y, a_out='', b_out=''):
        n = E(cls, x, y)
        C(a, a_out, n, 'A')
        C(b, b_out, n, 'B')
        return n

    def lerp(a, b, alpha, x, y, a_out='', b_out=''):
        n = E('LinearInterpolate', x, y)
        C(a, a_out, n, 'A')
        C(b, b_out, n, 'B')
        C(alpha, '', n, 'Alpha')
        return n

    def sat(a, x, y):
        n = E('Saturate', x, y)
        C(a, '', n, '')
        return n

    def mask(src, channel, x, y):
        n = E('ComponentMask', x, y)
        n.set_editor_property(channel, True)
        C(src, '', n, '')
        return n

    wp = E('WorldPosition', -2600, 0)
    xy = E('ComponentMask', -2400, 0)
    xy.set_editor_property('r', True)
    xy.set_editor_property('g', True)
    C(wp, '', xy, '')

    def world_uv(tile_name, tile_cm, y):
        return op('Divide', xy, scalar(m, tile_name, tile_cm, -2400, y), -2200, y)

    uv_d = world_uv('DetailTile', 200.0, 200)
    uv_dirt = world_uv('DirtTile', 180.0, 400)
    uv_grass = world_uv('GrassTile', 150.0, 600)
    uv_n1 = world_uv('NoiseTile', 1800.0, 800)
    uv_n2 = world_uv('Noise2Tile', 700.0, 1000)

    def sample(name, uv, y, sampler=None, default=None):
        t = tex_param(m, name, -1900, y, sampler, default)
        if uv is not None:
            C(uv, '', t, 'UVs')
        return t

    macro = sample('Macro', None, -600, default=d['white'])
    det_c = sample('DetailColor', uv_d, -300, default=d['white'])
    det_n = sample('DetailNormal', uv_d, 0, NORMAL, d['normal'])
    det_a = sample('DetailORM', uv_d, 300, MASKS, d['mask'])
    det_h = sample('DetailHeight', uv_d, 600, MASKS, d['mask'])
    dirt_c = sample('DirtColor', uv_dirt, 900, default=d['white'])
    dirt_n = sample('DirtNormal', uv_dirt, 1200, NORMAL, d['normal'])
    dirt_a = sample('DirtORM', uv_dirt, 1500, MASKS, d['mask'])
    gr_c = sample('GrassColor', uv_grass, 1800, default=d['white'])
    gr_n = sample('GrassNormal', uv_grass, 2100, NORMAL, d['normal'])
    gr_a = sample('GrassORM', uv_grass, 2400, MASKS, d['mask'])
    nz1 = sample('NoiseMask', uv_n1, 2700, MASKS, d['mask'])
    nz2 = sample('NoiseMask2', uv_n2, 3000, MASKS, d['mask'])
    jmask = sample('JointMask', None, 3300, MASKS, d['black'])   # UV0: R = joint lines, G = soft band around them

    lum_w = E('Constant3Vector', -1600, -800)
    lum_w.set_editor_property('constant', unreal.LinearColor(0.2126, 0.7152, 0.0722, 1))
    macro_lum = op('DotProduct', macro, lum_w, -1500, -700, 'RGB')
    det_lum = op('DotProduct', det_c, lum_w, -1500, -400, 'RGB')

    # joints: macro darker than MacroJointLevel, detail height below DetailJointLevel (weighted)
    mj = op('Subtract', scalar(m, 'MacroJointLevel', 0.5, -1500, -600), macro_lum, -1300, -650)
    mj = sat(op('Multiply', mj, scalar(m, 'MacroJointSharp', 6.0, -1300, -550), -1150, -650), -1000, -650)
    dj = op('Subtract', scalar(m, 'DetailJointLevel', 0.35, -1500, 500), det_h, -1300, 550, '', 'R')
    dj = sat(op('Multiply', dj, scalar(m, 'DetailJointSharp', 8.0, -1300, 650), -1150, 550), -1000, 550)
    dj = op('Multiply', dj, scalar(m, 'DetailJointWeight', 0.0, -1000, 650), -850, 550)
    joint = op('Max', mj, dj, -700, 0)
    band = op('Multiply', mask(jmask, 'g', -1150, 3300), scalar(m, 'JointBandWeight', 0.0, -1150, 3400), -1000, 3300)
    joint = op('Max', joint, band, -600, 0)

    # dirt: joints + worn patches from low-frequency noise
    patches = op('Subtract', nz1, scalar(m, 'DirtPatchLevel', 0.62, -1500, 2800), -1300, 2750, 'R')
    patches = op('Multiply', patches, scalar(m, 'DirtPatchAmount', 3.0, -1300, 2850), -1150, 2750)
    joint_dirt = op('Multiply', joint, scalar(m, 'JointDirt', 1.0, -900, 100), -700, 100)
    dirt_mask = sat(op('Add', joint_dirt, patches, -550, 100), -400, 100)

    # grass only inside joints, in clumps
    clumps = op('Subtract', nz2, scalar(m, 'GrassLevel', 0.55, -1500, 3100), -1300, 3050, 'G')
    clumps = sat(op('Multiply', clumps, scalar(m, 'GrassAmount', 4.0, -1300, 3150), -1150, 3050), -1000, 3050)
    grass_mask = sat(op('Multiply', joint, clumps, -550, 300), -400, 300)

    one = E('Constant', -1200, -300)
    one.set_editor_property('r', 1.0)
    det_scaled = op('Multiply', det_lum, scalar(m, 'DetailGain', 2.4, -1300, -250), -1100, -350)
    det_factor = lerp(one, det_scaled, scalar(m, 'DetailStrength', 1.0, -1200, -200), -950, -300)
    stone = op('Multiply', macro, det_factor, -800, -500, 'RGB')
    # DetailColorMix 1 = use the scan's own colour (outer ground), 0 = macro colour with scan luminance (plaza)
    stone = lerp(stone, det_c, scalar(m, 'DetailColorMix', 0.0, -800, -400), -700, -450, '', 'RGB')
    stone = op('Multiply', stone, vector(m, 'StoneTint', (1, 1, 1, 1), -900, -420), -650, -500)
    dirt_col = op('Multiply', dirt_c, vector(m, 'DirtTint', (1, 1, 1, 1), -900, 950), -650, 950, 'RGB')
    base = lerp(lerp(stone, dirt_col, dirt_mask, -300, -300), gr_c, grass_mask, -150, -300, '', 'RGB')
    nrm = lerp(lerp(det_n, dirt_n, dirt_mask, -300, 0, 'RGB', 'RGB'), gr_n, grass_mask, -150, 0, '', 'RGB')
    arm = lerp(lerp(det_a, dirt_a, dirt_mask, -300, 400, 'RGB', 'RGB'), gr_a, grass_mask, -150, 400, '', 'RGB')
    ao = mask(arm, 'r', 0, 350)
    rough = op('Multiply', mask(arm, 'g', 0, 450), scalar(m, 'RoughnessScale', 1.0, 0, 550), 150, 450)
    MEL.connect_material_property(base, '', P.MP_BASE_COLOR)
    MEL.connect_material_property(nrm, '', P.MP_NORMAL)
    MEL.connect_material_property(ao, '', P.MP_AMBIENT_OCCLUSION)
    MEL.connect_material_property(rough, '', P.MP_ROUGHNESS)
    MEL.recompile_material(m)
    EAL.save_asset('/Game/Materials/M_Ground')
    return m


def assign_by_slot(mesh, table):
    """table: slot-name -> MaterialInterface. Works for static and skeletal meshes.
    (Replacing the whole static_materials array does not stick; set per index instead.)"""
    def key_for(name):
        return next((k for k in table if name == k or name.startswith(k + '_') or name.endswith(k)), None)
    names = []
    if isinstance(mesh, unreal.StaticMesh):
        for i, m in enumerate(mesh.get_editor_property('static_materials')):
            name = str(m.get_editor_property('material_slot_name'))
            names.append(name)
            if key_for(name):
                mesh.set_material(i, table[key_for(name)])
    else:
        new = []
        for m in mesh.get_editor_property('materials'):
            name = str(m.get_editor_property('material_slot_name'))
            names.append(name)
            mat = table[key_for(name)] if key_for(name) else m.get_editor_property('material_interface')
            new.append(unreal.SkeletalMaterial(material_interface=mat, material_slot_name=name))
        mesh.set_editor_property('materials', new)
    EAL.save_asset(mesh.get_path_name(), only_if_is_dirty=False)
    return names




def delete_map(path='/Game/Maps/Plaza'):
    """EAL.delete_asset sometimes leaves the .umap on disk ("asset already exists" on new_level) -> remove the file too."""
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)
    f = os.path.join(unreal.Paths.project_content_dir(), path.replace('/Game/', '') + '.umap')
    f = unreal.Paths.convert_relative_path_to_full(f)
    if os.path.exists(f):
        os.remove(f)
        log('removed stale map file', f)

# ------------------------------------------------------------------ 0. clean re-import
# FBX re-import replaces meshes but silently keeps existing AnimSequences (and never creates new ones),
# so edited/added clips never reached the game. Delete the map (it references them) and the character
# folder first; both are recreated below.
if not SKIP_IMPORT and EAL.does_asset_exist('/Game/Maps/Plaza'):
    # full import deletes /Game/Characters, which the map references: empty the map first (never delete it -
    # a deleted map package lingers and new_level then fails / silently saves nothing)
    _les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    _eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    _les.load_level('/Game/Maps/Plaza')
    for _a in _eas.get_all_level_actors():
        if not isinstance(_a, (unreal.WorldSettings, unreal.Brush)):
            _eas.destroy_actor(_a)
    _les.save_current_level()
    _les.new_level('/Temp/Untitled_Build')   # unload it so the character folder can be deleted
# Re-importing onto an existing skeletal mesh also skips creating clips, so start the folder fresh.
if not SKIP_IMPORT and EAL.does_directory_exist('/Game/Characters'):
    EAL.delete_directory('/Game/Characters')
    log('deleted /Game/Characters for a clean skeletal + animation import')

# ------------------------------------------------------------------ 1. textures + materials
for d in ('/Game/Env/Textures', '/Game/Env/Meshes', '/Game/Props', '/Game/Characters', '/Game/Maps'):
    ensure_dir(d)
env_tex = {}
for f in sorted(os.listdir(f'{EXPORT}/env_textures')):
    if f.endswith('.png'):
        env_tex[f[:-4]] = import_texture(f'{EXPORT}/env_textures/{f}', '/Game/Env/Textures')
if SKIP_IMPORT and EAL.does_asset_exist('/Game/Materials/M_Char'):
    masters = {k: EAL.load_asset(f'/Game/Materials/{k}') for k in ('M_Env', 'M_Char', 'M_Flat', 'M_Banner')}
else:
    masters = build_masters({'color': env_tex['T_Stone_BaseColor'], 'normal': env_tex['T_Stone_Normal'],
                             'orm': env_tex['T_Stone_Normal']})
MI = '/Game/Env/Materials'
ensure_dir(MI)
# realistic floor (4-10): Poly Haven CC0 scans, world-aligned, layered in M_Ground
GROUND = f'{EXPORT}/ground_textures'
gtex = {os.path.splitext(f)[0]: import_texture(f'{GROUND}/{f}', '/Game/Env/Ground')
        for f in sorted(os.listdir(GROUND)) if f.endswith(('.png', '.jpg'))}
m_ground = build_ground_master({'white': gtex['T_White_BaseColor'], 'normal': gtex['T_Sandstone_Normal'],
                                'mask': gtex['T_Ground_Mask'], 'black': gtex['T_Black_Mask']})


def ground_mi(path, macro, detail, scalars, vectors=None, joint_mask=None):
    t = {'Macro': gtex[macro] if macro in gtex else env_tex[macro],
         'DetailColor': gtex[f'T_{detail}_BaseColor'], 'DetailNormal': gtex[f'T_{detail}_Normal'],
         'DetailORM': gtex[f'T_{detail}_ORM'], 'DetailHeight': gtex[f'T_{detail}_Height'],
         'DirtColor': gtex['T_DirtRocks_BaseColor'], 'DirtNormal': gtex['T_DirtRocks_Normal'], 'DirtORM': gtex['T_DirtRocks_ORM'],
         'GrassColor': gtex['T_LeafyGrass_BaseColor'], 'GrassNormal': gtex['T_LeafyGrass_Normal'], 'GrassORM': gtex['T_LeafyGrass_ORM'],
         'NoiseMask': gtex['T_Ground_Mask'], 'NoiseMask2': gtex['T_Ground_Mask'],
         'JointMask': gtex[joint_mask] if joint_mask else gtex['T_Black_Mask']}
    return material_instance(path, m_ground, t, scalars, vectors)


env_mats = {
    'M_Stone': material_instance(f'{MI}/MI_Stone', masters['M_Env'], {'BaseColor': env_tex['T_Stone_BaseColor'], 'Normal': env_tex['T_Stone_Normal']}, {'Roughness': 0.9}, vectors={'Tint': (1.07, 0.97, 0.84, 1)}),
    # plaza disc: painted ring layout (macro) x cracked sandstone scan; joints fill with dirt / grass clumps
    'M_Plaza': ground_mi(f'{MI}/MI_PlazaReal', 'T_Plaza_BaseColor', 'Sandstone',
                         {'DetailGain': 1 / 0.4092, 'DetailStrength': 0.85, 'DetailTile': 200.0, 'MacroJointLevel': 0.3, 'MacroJointSharp': 8.0,
                          'DetailJointWeight': 0.0, 'JointBandWeight': 1.0, 'JointDirt': 1.0, 'GrassLevel': 0.42, 'GrassAmount': 6.0,
                          'DirtPatchLevel': 0.56, 'DirtPatchAmount': 2.5, 'RoughnessScale': 0.72, 'Noise2Tile': 400.0},
                         vectors={'StoneTint': (1.08, 0.98, 0.84, 1), 'DirtTint': (0.55, 0.5, 0.45, 1)},
                         joint_mask='T_Plaza_JointMask'),
    # outer ground: granite block scan, its own grooves are the joints
    'M_Paving': ground_mi(f'{MI}/MI_GroundReal', 'T_White_BaseColor', 'RockTile',
                          {'DetailGain': 1 / 0.29, 'DetailStrength': 1.0, 'DetailColorMix': 1.0, 'DetailTile': 250.0, 'MacroJointLevel': 0.0,
                           'DetailJointWeight': 1.0, 'DetailJointLevel': 0.3, 'GrassLevel': 0.5, 'GrassAmount': 5.0, 'RoughnessScale': 0.85},
                          vectors={'StoneTint': (1.12, 1.0, 0.82, 1), 'DirtTint': (0.6, 0.55, 0.5, 1)}),
    'M_Roof': material_instance(f'{MI}/MI_Roof', masters['M_Env'], {'BaseColor': env_tex['T_Roof_BaseColor'], 'Normal': env_tex['T_Roof_Normal']}, {'Roughness': 0.55}),
    'M_Banner': material_instance(f'{MI}/MI_Banner', masters['M_Banner'], {'BaseColor': env_tex['T_Banner_BaseColor']}),
    'M_Gold': material_instance(f'{MI}/MI_Gold', masters['M_Flat'], vectors={'Color': (0.83, 0.58, 0.2, 1)}, scalars={'Roughness': 0.35, 'Metallic': 1.0}),
    'M_Wood': material_instance(f'{MI}/MI_Wood', masters['M_Flat'], vectors={'Color': (0.22, 0.12, 0.06, 1)}, scalars={'Roughness': 0.8}),
    'M_BarrelWood': material_instance(f'{MI}/MI_BarrelWood', masters['M_Flat'], vectors={'Color': (0.5, 0.28, 0.11, 1)}, scalars={'Roughness': 0.75}),
    'M_Iron': material_instance(f'{MI}/MI_Iron', masters['M_Flat'], vectors={'Color': (0.1, 0.1, 0.11, 1)}, scalars={'Roughness': 0.45, 'Metallic': 1.0}),
    'M_WindowDark': material_instance(f'{MI}/MI_WindowDark', masters['M_Flat'], vectors={'Color': (0.04, 0.06, 0.1, 1)}, scalars={'Roughness': 0.3}),
}

# ------------------------------------------------------------------ 2. environment kit meshes
meshes = {}
for f in sorted(os.listdir(f'{EXPORT}/env')):
    if f.endswith('.fbx'):
        name = f[:-4]
        import_file(f'{EXPORT}/env/{f}', '/Game/Env/Meshes')
        sm = EAL.load_asset(f'/Game/Env/Meshes/{name}')
        log('slots', name, assign_by_slot(sm, env_mats))
        meshes[name] = sm

# ------------------------------------------------------------------ 3. Tripo props (static)
props = json.load(open(f'{EXPORT}/props/props.json', encoding='utf-8'))
PROP_GLOW = {'HeroSword': (0.08, 0.4, 1.3, 1)}   # rune glow (HDR frost blue) x T_<base>_Emissive mask
prop_tex = {}
for p in props:
    base = p['material'][2:]          # M_Weapons -> Weapons
    if base not in prop_tex:
        prop_tex[base] = {role: import_texture(f'{EXPORT}/props/{fname}', '/Game/Props/Textures')
                          for role, fname in p['textures'].items()}
        glow = PROP_GLOW.get(base)
        if glow and os.path.exists(f'{EXPORT}/props/T_{base}_Emissive.png'):   # made by make_glow_mask.py
            prop_tex[base]['Emissive'] = import_texture(f'{EXPORT}/props/T_{base}_Emissive.png', '/Game/Props/Textures')
        material_instance(f'/Game/Props/Materials/MI_{base}', masters['M_Char'], prop_tex[base],
                          vectors={'EmissiveColor': glow} if glow and 'Emissive' in prop_tex[base] else None)
    import_file(f'{EXPORT}/props/{p["name"]}.fbx', '/Game/Props')
    sm = EAL.load_asset(f'/Game/Props/{p["name"]}')
    assign_by_slot(sm, {p['material']: EAL.load_asset(f'/Game/Props/Materials/MI_{base}')})
    meshes[p['name']] = sm

# ------------------------------------------------------------------ 4. characters
CHAR_GRIP = {}
CHAR_TINT = {'Hero': (1.0, 1.0, 1.0, 1)}   # baked HD hero (4-8) has darker fur than the P1 draft; keep it readable on the pale plaza
CHAR_HEIGHT_M = {'Hero': 2.2, 'Brute': 3.0, 'Rogue': 2.05, 'Archer': 2.05}   # stylised: hero ~1/9 of the plaza diameter like the reference
chars = {}
CLIP_SPEED_CM = {}
# Mixamo attack clips whose Root bone carries the step / lunge (process_character.py, 4-27): root motion on
ROOT_MOTION_CLIPS = {}   # none: attacks step in via FNyabloAttackClip.Lunge (4-27; root motion threw the hero 63 m)
CHAR_LUNGES = {}   # name -> {clip: [{start, end, travel_m}]} from process_character.py --rezero
RAGDOLL_CHARS = ('Brute', 'Rogue', 'Archer')   # enemies get an auto physics asset -> ragdoll death (4-28)
for name, height in CHAR_HEIGHT_M.items():
    info = json.load(open(f'{EXPORT}/characters/{name}/{name}.json', encoding='utf-8'))
    CHAR_GRIP[name] = (info.get('grip', {}), CHAR_HEIGHT_M[name] / info['rest_height_m'] * 100.0)   # (fist data, m -> cm)
    CHAR_LUNGES[name] = info.get('lunges', {})
    dest = f'/Game/Characters/{name}'
    ensure_dir(dest)
    tex = {role: import_texture(f'{EXPORT}/characters/{name}/{fname}', dest) for role, fname in info['textures'].items()}
    mi = material_instance(f'{dest}/MI_{name}', masters['M_Char'], tex, vectors={'Tint': CHAR_TINT.get(name, (1.1, 1.06, 1.02, 1))})   # slight lift of dark fur/armour
    task = unreal.AssetImportTask()
    task.filename = f'{EXPORT}/characters/{name}/{info["fbx"]}'
    task.destination_path = dest
    task.automated = True
    task.replace_existing = True
    task.save = True
    opt = unreal.FbxImportUI()
    opt.import_as_skeletal = True
    opt.mesh_type_to_import = unreal.FBXImportType.FBXIT_SKELETAL_MESH
    opt.import_mesh = True
    opt.import_animations = True
    opt.import_materials = False
    opt.import_textures = False
    opt.create_physics_asset = True
    scale = height / info['rest_height_m']
    opt.skeletal_mesh_import_data.set_editor_property('import_uniform_scale', scale)
    # keep Blender's split normals and MikkTSpace tangents: the baked normal maps were made against them (4-11)
    opt.skeletal_mesh_import_data.set_editor_property('normal_import_method', unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS_AND_TANGENTS)
    opt.skeletal_mesh_import_data.set_editor_property('normal_generation_method', unreal.FBXNormalGenerationMethod.MIKK_T_SPACE)
    opt.anim_sequence_import_data.set_editor_property('import_uniform_scale', scale)
    opt.anim_sequence_import_data.set_editor_property('animation_length', unreal.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME)
    task.options = opt
    if SKIP_IMPORT and EAL.does_asset_exist(f'{dest}/SK_{name}'):
        paths = [f'{dest}/SK_{name}']
    else:
        ASSET_TOOLS.import_asset_tasks([task])
        paths = list(task.imported_object_paths)
    log('char import', name, paths)
    sk = next(EAL.load_asset(p) for p in paths if isinstance(EAL.load_asset(p), unreal.SkeletalMesh))
    if name in RAGDOLL_CHARS and not sk.get_editor_property('physics_asset'):
        # 4-28: FbxImportUI.create_physics_asset does nothing in this commandlet build -> enemies had no ragdoll.
        # Not the hero: a body physics asset would start colliding with its Chaos cloth (cape / tail).
        pa = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem).create_physics_asset(sk, True)
        log('physics asset', name, pa.get_path_name() if pa else None)
        if pa:
            EAL.save_loaded_asset(pa)
            EAL.save_loaded_asset(sk)
    slot_names = [str(m.get_editor_property('material_slot_name')) for m in sk.get_editor_property('materials')]
    table = {}
    if f'M_{name}_Fur' in slot_names:
        # shell fur (4-14): exact key first, so the generic M_<name> prefix match does not grab it
        strands = import_texture(f'{EXPORT}/characters/_shared/T_FurStrands.png', '/Game/Characters/_Shared')
        fur_master = build_fur_master({'strands': strands, 'color': tex['BaseColor'], 'normal': tex['Normal']})
        table[f'M_{name}_Fur'] = material_instance(f'{dest}/MI_{name}_Fur', fur_master,
                                                   {'BaseColor': tex['BaseColor'], 'Normal': tex['Normal'], 'Strands': strands},
                                                   {'FurTiling': 8.0}, vectors={'Tint': CHAR_TINT.get(name, (1, 1, 1, 1))})
    table[f'M_{name}'] = mi
    assign_by_slot(sk, table)   # also M_<name>_Cloth / _ClothSim (prefix match)
    slots = [str(m.get_editor_property('material_slot_name')) for m in sk.get_editor_property('materials')]
    if not (SKIP_IMPORT and sk.get_editor_property('mesh_clothing_assets')):
        # Chaos cloth (4-12): each part is simulated on its welded low-res proxy section, the visible section follows it.
        # cape: pinned at the top, hem free; tail: pinned at the root (toward the body, +X in the ref pose), kept in shape
        # by anim drive. Body collision from the physics asset.
        sms = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
        # cape (4-15): more freedom, lighter, catches air (drag / lift) so the hero's wind gusts lift it off the back
        cape_cfg = {'GravityScale': 0.7, 'Drag': 0.3, 'Lift': 0.3, 'LinearVelocityScale': 1.0, 'AngularVelocityScale': 1.0}
        for part, sim_part, pin_dir, band, slope, cap, drive, cfg in (
                ('Cloth', 'ClothSim', unreal.Vector(0, 0, 1), 4.0, 3.0, 90.0, 0.0, cape_cfg),   # 4-16: only the neck band pinned, shoulders free
                ('Tail', 'TailSim', unreal.Vector(1, 0, 0), 6.0, 0.3, 18.0, 0.25, {})):
            if f'M_{name}_{part}' not in slots or f'M_{name}_{sim_part}' not in slots:
                continue
            by_slot = {sms.get_lod_material_slot(sk, 0, i): i for i in range(sms.get_num_sections(sk, 0))}
            render_sec, sim_sec = by_slot[slots.index(f'M_{name}_{part}')], by_slot[slots.index(f'M_{name}_{sim_part}')]
            free = unreal.NyabloClothTools.setup_section_cloth(sk, render_sec, sim_sec, pin_dir, band, slope, cap, drive, cfg)
            log('cloth', name, part, 'render', render_sec, 'sim', sim_sec, 'free verts', free)
        EAL.save_asset(sk.get_path_name(), only_if_is_dirty=False)
    anims = {}
    for p in EAL.list_assets(dest, recursive=False):
        a = EAL.load_asset(p)
        if isinstance(a, unreal.AnimSequence):
            clip = a.get_name().split('_')[-1]
            anims[clip] = a
            # 4-27: Mixamo attacks carry their step / lunge on the Root bone -> the capsule follows it while attacking
            rm = clip in ROOT_MOTION_CLIPS.get(name, ())
            if a.get_editor_property('enable_root_motion') != rm:
                a.set_editor_property('enable_root_motion', rm)
                EAL.save_asset(a.get_path_name(), only_if_is_dirty=False)
    log('clips', name, sorted(anims))
    chars[name] = (sk, anims)
    # ground speed removed from in-place loops (process_character.py) -> anim play rate matches movement
    CLIP_SPEED_CM[name] = {c['name'].split('_')[-1]: c.get('ground_speed_heights_per_s', 0.0) * height * 100.0
                           for c in info['clips']}

# ------------------------------------------------------------------ 4b. detachable cape (deathknight, step 6)
# Own skeletal mesh on the hero skeleton (workspace/deathknight/cape/build_cape.py): the hero actor shows it on a
# leader-pose component and toggles it with C (cloth suspended while off). Masked two-sided cloth, black lining on the
# back faces, Chaos cloth on the coarse proxy section, collision from the hero's physics asset.
HERO_CAPE = None
CAPE_DIR = f'{EXPORT}/characters/HeroCape'
if 'Hero' in chars and os.path.exists(f'{CAPE_DIR}/HeroCape.json'):
    cinfo = json.load(open(f'{CAPE_DIR}/HeroCape.json', encoding='utf-8'))
    cdest = '/Game/Characters/HeroCape'
    ensure_dir(cdest)
    if SKIP_IMPORT and EAL.does_asset_exist(f'{cdest}/MI_HeroCape'):      # --layout: keep the imported cape material
        cmi = EAL.load_asset(f'{cdest}/MI_HeroCape')
    else:
        ctex = import_texture(f'{CAPE_DIR}/{cinfo["texture"]}', cdest)
        cm = new_material('/Game/Materials/M_Cape')
        cm.set_editor_property('blend_mode', unreal.BlendMode.BLEND_MASKED)
        cm.set_editor_property('two_sided', True)
        cm.set_editor_property('used_with_skeletal_mesh', True)
        cm.set_editor_property('used_with_clothing', True)
        P_ = unreal.MaterialProperty
        cbc = tex_param(cm, 'BaseColor', -700, 0, default=ctex)
        side = MEL.create_material_expression(cm, unreal.MaterialExpressionTwoSidedSign, -700, 300)
        sat = MEL.create_material_expression(cm, unreal.MaterialExpressionSaturate, -500, 300)
        MEL.connect_material_expressions(side, '', sat, '')
        lerp = MEL.create_material_expression(cm, unreal.MaterialExpressionLinearInterpolate, -300, 100)
        MEL.connect_material_expressions(vector(cm, 'Lining', (0.02, 0.018, 0.02, 1), -700, 450), '', lerp, 'A')
        MEL.connect_material_expressions(cbc, 'RGB', lerp, 'B')
        MEL.connect_material_expressions(sat, '', lerp, 'Alpha')
        MEL.connect_material_property(lerp, '', P_.MP_BASE_COLOR)
        MEL.connect_material_property(cbc, 'A', P_.MP_OPACITY_MASK)
        MEL.connect_material_property(scalar(cm, 'Roughness', 0.9, -700, 650), '', P_.MP_ROUGHNESS)
        MEL.connect_material_property(scalar(cm, 'Specular', 0.2, -700, 750), '', P_.MP_SPECULAR)
        MEL.recompile_material(cm)
        EAL.save_asset('/Game/Materials/M_Cape')
        cmi = material_instance(f'{cdest}/MI_HeroCape', cm, {'BaseColor': ctex})
    hero_sk = chars['Hero'][0]
    hero_info = json.load(open(f'{EXPORT}/characters/Hero/Hero.json', encoding='utf-8'))
    task = unreal.AssetImportTask()
    task.filename = f'{CAPE_DIR}/{cinfo["fbx"]}'
    task.destination_path = cdest
    task.automated = True
    task.replace_existing = True
    task.save = True
    opt = unreal.FbxImportUI()
    opt.import_as_skeletal = True
    opt.mesh_type_to_import = unreal.FBXImportType.FBXIT_SKELETAL_MESH
    opt.import_mesh = True
    opt.import_animations = False
    opt.import_materials = False
    opt.import_textures = False
    opt.create_physics_asset = False
    opt.skeleton = hero_sk.get_editor_property('skeleton')          # same skeleton -> leader pose
    opt.skeletal_mesh_import_data.set_editor_property('import_uniform_scale', CHAR_HEIGHT_M['Hero'] / hero_info['rest_height_m'])
    opt.skeletal_mesh_import_data.set_editor_property('normal_import_method', unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS_AND_TANGENTS)
    task.options = opt
    if SKIP_IMPORT and EAL.does_asset_exist(f'{cdest}/SK_HeroCape'):
        cpaths = [f'{cdest}/SK_HeroCape']
    else:
        ASSET_TOOLS.import_asset_tasks([task])
        cpaths = list(task.imported_object_paths)
    log('cape import', cpaths)
    HERO_CAPE = next((EAL.load_asset(p) for p in cpaths if isinstance(EAL.load_asset(p), unreal.SkeletalMesh)), None)
    if HERO_CAPE:
        HERO_CAPE.set_editor_property('physics_asset', hero_sk.get_editor_property('physics_asset'))
        assign_by_slot(HERO_CAPE, {'M_HeroCape_Cloth': cmi, 'M_HeroCape_ClothSim': cmi})
        if not (SKIP_IMPORT and HERO_CAPE.get_editor_property('mesh_clothing_assets')):
            sms = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
            cslots = [str(m.get_editor_property('material_slot_name')) for m in HERO_CAPE.get_editor_property('materials')]
            by_slot = {sms.get_lod_material_slot(HERO_CAPE, 0, i): i for i in range(sms.get_num_sections(HERO_CAPE, 0))}
            rsec, ssec = by_slot[cslots.index('M_HeroCape_Cloth')], by_slot[cslots.index('M_HeroCape_ClothSim')]
            cape_cfg = {'GravityScale': 0.7, 'Drag': 0.3, 'Lift': 0.3, 'LinearVelocityScale': 1.0, 'AngularVelocityScale': 1.0}
            free = unreal.NyabloClothTools.setup_section_cloth(HERO_CAPE, rsec, ssec, unreal.Vector(0, 0, 1), 4.0, 3.0, 90.0, 0.0, cape_cfg)
            log('cloth', 'HeroCape', 'render', rsec, 'sim', ssec, 'free verts', free)
        EAL.save_asset(HERO_CAPE.get_path_name(), only_if_is_dirty=False)

# ------------------------------------------------------------------ 5. level
LEVEL = '/Game/Maps/Plaza'
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
# Deleting + recreating the map is unreliable (the deleted package lingers: "asset already exists").
# Reuse it instead: open it and remove every actor, or create it the first time.
if EAL.does_asset_exist(LEVEL):
    les.load_level(LEVEL)
    for a in eas.get_all_level_actors():
        # Volumes (PostProcessVolume, ...) are Brush subclasses: keep only the default builder brush,
        # otherwise every rebuild stacked another unbound post-process volume with the old grade (4-7)
        keep = isinstance(a, unreal.WorldSettings) or (isinstance(a, unreal.Brush) and not isinstance(a, unreal.Volume))
        if not keep:
            eas.destroy_actor(a)
elif not les.new_level(LEVEL):
    raise RuntimeError('new_level failed - map was not rebuilt')


def spawn_mesh(sm, loc, rot, scale=1.0, label=None, folder='Env'):
    a = eas.spawn_actor_from_class(unreal.StaticMeshActor, loc, rot)
    a.static_mesh_component.set_static_mesh(sm)
    a.set_actor_scale3d(unreal.Vector(scale, scale, scale))
    if label:
        a.set_actor_label(label)
    a.set_folder_path(folder)
    return a


import plaza_dressing
layout = json.load(open(f'{EXPORT}/env/layout.json', encoding='utf-8'))
for i, e in enumerate(layout):
    if e['piece'] in plaza_dressing.REPLACED_PIECES:
        continue
    sm = meshes.get(e['piece'])
    if not sm:
        log('missing piece', e['piece'])
        continue
    loc, rot = blender_to_ue(e['loc'], e['yaw'])
    folder = 'Props' if e['piece'] in ('SM_CypressPlanter', 'SM_Bell', 'SM_Crate', 'SM_Barrel', 'SM_Banner') else 'Env'
    spawn_mesh(sm, loc, rot, e.get('scale', 1.0), f'{e["piece"]}_{i:02d}', folder)

EXPOSURE_BIAS = 0.75   # D4-day grade (4-22): mean 121 at 0.4 vs the D4 reference 140; 0.65 still read dark to the user; +0.4 stop after the 4-7 contrast fix read too dark (4-9); manual exposure, physical camera off (scene captures have no eye adaptation); sun 10 lux
# Fab pack dressing (buildings, trees, props) + pack brick material on our terraces / stairs / balustrade
plaza_dressing.dress(eas, spawn_mesh)
kit_bricks = plaza_dressing.kit_stone_material()
for piece in ('SM_Wall4m', 'SM_Pillar', 'SM_Stairs', 'SM_Terrace'):
    sm = meshes[piece]
    for idx, m in enumerate(sm.get_editor_property('static_materials')):
        if str(m.get_editor_property('material_slot_name')) == 'M_Stone':
            sm.set_material(idx, kit_bricks)
    EAL.save_asset(sm.get_path_name(), only_if_is_dirty=False)

# lighting: warm sun from the camera side, upper right (shadows still fall toward the lower left like the reference).
# yaw 135 lit the plaza from behind -> the camera only saw the characters' shadow side (4-9)
# D4 daytime (4-22): lower, warmer sun (pitch -40, was -55) -> longer shadows toward the lower left (-32 buried half the plaza)
sun = eas.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 3000), unreal.Rotator(0, -40, -135))
sun.set_actor_label('Sun')
sc = sun.get_component_by_class(unreal.DirectionalLightComponent)
sc.set_editor_property('intensity', 13.0)
sc.set_editor_property('light_source_angle', 1.0)       # crisp contact shadows (4.0 read as haze, 4-7)
sc.set_editor_property('light_color', unreal.Color(255, 170, 100, 255))
sc.set_editor_property('atmosphere_sun_light', True)
sc.set_mobility(unreal.ComponentMobility.MOVABLE)      # Lumen, no baked lighting ("lighting needs rebuild" otherwise)
sky = eas.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 500), unreal.Rotator(0, 0, 0))
skc = sky.get_component_by_class(unreal.SkyLightComponent)
skc.set_mobility(unreal.ComponentMobility.MOVABLE)
skc.set_editor_property('real_time_capture', True)
skc.set_editor_property('intensity', 2.5)      # D4 day (4-22): shadows stay warm mid-tones (2.8 in 4-9 flattened them, 1.1-1.6 went black, 2.2 read dark)
skc.set_editor_property('light_color', unreal.Color(255, 185, 130, 255))
atmo = eas.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
# paler, less saturated sky -> the sky light stops tinting every shadow deep blue
atmo.get_component_by_class(unreal.SkyAtmosphereComponent).set_rayleigh_scattering(unreal.LinearColor(0.22, 0.26, 0.34, 1.0))
# light breeze so the hero's cape moves even when standing (4-12)
wind = eas.spawn_actor_from_class(unreal.WindDirectionalSource, unreal.Vector(0, 0, 600), unreal.Rotator(0, 0, 60))
wind.get_component_by_class(unreal.WindDirectionalSourceComponent).set_editor_property('strength', 0.35)
wind.get_component_by_class(unreal.WindDirectionalSourceComponent).set_editor_property('speed', 0.6)
fog = eas.spawn_actor_from_class(unreal.ExponentialHeightFog, unreal.Vector(0, 0, -200), unreal.Rotator(0, 0, 0))
fogc = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
fogc.set_editor_property('fog_density', 0.0035)         # golden D4 haze (4-22); with the low sky fill it no longer reads as 뿌연
fogc.set_editor_property('fog_inscattering_luminance', unreal.LinearColor(1.0, 0.66, 0.38, 1.0))
ppv = eas.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
ppv.set_editor_property('unbound', True)
s = ppv.get_editor_property('settings')
# warm grade from 4-3 with the contrast restored in 4-7 (default film curve, stronger AO, no motion blur)
PP = {
    'auto_exposure_method': unreal.AutoExposureMethod.AEM_MANUAL,
    'auto_exposure_apply_physical_camera_exposure': False,
    'auto_exposure_bias': EXPOSURE_BIAS,
    'film_slope': 0.88, 'film_toe': 0.5, 'film_shoulder': 0.26,
    # D4 daytime grade (4-22, look-dev shots F in design/plaza_unreal_results/look_d4day_compare.png)
    'white_temp': 7500.0,
    'color_saturation': unreal.Vector4(1.0, 1.0, 1.0, 1.0),
    'color_contrast': unreal.Vector4(1.2, 1.2, 1.2, 1.0),
    'color_gain': unreal.Vector4(1.3, 1.0, 0.66, 1.0),
    'color_gain_shadows': unreal.Vector4(1.1, 0.9, 0.7, 1.0),
    'scene_color_tint': unreal.LinearColor(1.0, 0.87, 0.68, 1.0),   # ochre: the 2.2 sky fill turned the F grade khaki
    'ambient_occlusion_intensity': 0.8,
    'motion_blur_amount': 0.0,
    # local exposure: lift dark areas and boost surface detail instead of flattening the whole curve (4-9)
    'local_exposure_shadow_contrast_scale': 0.6,    # 0.5 lifted every shadow flat (4-9), 0.85 left 8 % near-black
    'local_exposure_highlight_contrast_scale': 0.85,
    'local_exposure_detail_strength': 1.2,   # 1.6 made fur/armour contrast harsh on the HD hero (4-11)
    'bloom_intensity': 0.6,
    'vignette_intensity': 0.35,   # 0.55 made most of the near-black corners ("좀 어두워", 4-22)
}
for k, v in PP.items():
    s.set_editor_property('override_' + k, True)
    s.set_editor_property(k, v)
ppv.set_editor_property('settings', s)

# ------------------------------------------------------------------ 6. characters + weapons (reference composition)
ML = unreal.MathLibrary
# prop, hand side, grip style. Weapon meshes were modelled for base heights (process_props.py sizes)
GRIP = {
    'Hero': [('SM_Sword', 'R', 'blade')],
    'Brute': [('SM_Mace', 'R', 'blade'), ('SM_Shield', 'L', 'shield')],
    'Rogue': [('SM_Dagger', 'R', 'blade'), ('SM_Dagger', 'L', 'blade')],
    'Archer': [('SM_Bow', 'L', 'bow')],
}
WEAPON_BASE_HEIGHT_M = {'Hero': 1.5, 'Brute': 2.15, 'Rogue': 1.45, 'Archer': 1.45}


def _v(x, y, z):
    return unreal.Vector(x, y, z)


def _ortho(a, b):
    """a with its component along unit b removed, normalised."""
    return ML.normal(ML.subtract_vector_vector(a, ML.multiply_vector_float(b, ML.dot_vector_vector(a, b))))


def grip_relative(actor, comp, side, style, scale, fist=None, unit_cm=1.0):
    """Weapon transform relative to the hand bone, computed in the reference pose:
    blade  -> blade (+Z) perpendicular to the forearm, pointing forward out of the fist
    shield -> face (+X) outward/forward from the forearm, top (+Z) up
    bow    -> limbs (+Z) up, perpendicular to the forearm, string (+X) toward the archer"""
    hand = comp.get_socket_transform(f'{side}_Hand', unreal.RelativeTransformSpace.RTS_WORLD)
    fore = comp.get_socket_location(f'{side}_Forearm')
    hloc = hand.translation
    d = ML.normal(ML.subtract_vector_vector(hloc, fore))
    fwd = actor.get_actor_forward_vector()
    right = actor.get_actor_right_vector()
    up = _v(0, 0, 1)
    offset = _v(0, 0, 0)
    if fist:
        # grip in the fist, not at the wrist (4-18): along forearm->hand + the measured side offset (rest pose,
        # Blender +X forward / +Y left -> actor forward / -right)
        flen = ML.vector_distance(hloc, fore)
        px, py, pz = fist['perp_m']
        offset = ML.add_vector_vector(ML.multiply_vector_float(d, fist['along_ratio'] * flen),
                                      ML.add_vector_vector(ML.add_vector_vector(ML.multiply_vector_float(fwd, px * unit_cm),
                                                                                ML.multiply_vector_float(right, -py * unit_cm)),
                                                           _v(0, 0, pz * unit_cm)))
    if style == 'blade' and fist and fist.get('hole_axis'):
        # deathknight (4-25): the handle runs along the fist's measured hole axis (rest pose, Blender +X forward /
        # +Y left / +Z up), not straight forward: the modelled fist grips at ~35 deg outward
        hx, hy, hz = fist['hole_axis']
        z = ML.normal(ML.add_vector_vector(ML.add_vector_vector(ML.multiply_vector_float(fwd, hx), ML.multiply_vector_float(right, -hy)),
                                           _v(0, 0, hz)))
        x = d
        if fist.get('edge_axis'):
            # 4-30: roll so the edge (+Y, blade width) leads the strikes (deathknight/tools/edge_axis.py); +X along the
            # forearm swung the flat into the target
            ex, ey, ez = fist['edge_axis']
            e = ML.add_vector_vector(ML.add_vector_vector(ML.multiply_vector_float(fwd, ex), ML.multiply_vector_float(right, -ey)),
                                     _v(0, 0, ez))
            target = unreal.Transform(location=ML.add_vector_vector(hloc, offset), rotation=ML.make_rot_from_zy(z, e),
                                      scale=_v(1, 1, 1))
            hand_unscaled = unreal.Transform(location=hloc, rotation=hand.rotation.rotator(), scale=_v(1, 1, 1))
            return ML.make_relative_transform(target, hand_unscaled)
    elif style == 'blade':
        z, x = _ortho(fwd, d), d
    elif style == 'shield':
        out = ML.multiply_vector_float(right, -1.0 if side == 'L' else 1.0)
        x = _ortho(ML.normal(ML.add_vector_vector(ML.multiply_vector_float(out, 0.7), ML.multiply_vector_float(fwd, 0.5))), d)
        z = _ortho(up, x)
        offset = ML.add_vector_vector(offset, ML.multiply_vector_float(x, 12.0 * scale))
    else:  # bow
        z = _ortho(up, d)
        x = _ortho(ML.multiply_vector_float(fwd, -1.0), z)
    target = unreal.Transform(location=ML.add_vector_vector(hloc, offset), rotation=ML.make_rot_from_zx(z, x),
                              scale=_v(1, 1, 1))
    hand_unscaled = unreal.Transform(location=hloc, rotation=hand.rotation.rotator(), scale=_v(1, 1, 1))
    return ML.make_relative_transform(target, hand_unscaled)


CAST = [  # name, clip, blender-space position (m), yaw toward the hero (deg, blender), clip time (s)
    ('Hero', 'slash', (-1.2, -4.2), 60, 0.9),
    ('Brute', 'idle', (-3.6, 5.2), -76, 0.0),
    ('Brute', 'slash', (3.8, 4.4), -120, 1.2),
    ('Rogue', 'idle', (-6.8, 1.6), -46, 0.5),
    ('Rogue', 'slash', (6.9, 0.8), -148, 0.6),
    ('Archer', 'idle', (0.3, 8.6), -95, 2.0),    # Tripo 'shoot' is a rolling gun-shot, not a bow draw
]
# playable actors (C++ module Source/Nyablo): hero = player, others = enemies with AI
HERO_CLASS = unreal.load_class(None, '/Script/Nyablo.NyabloHero')
ENEMY_CLASS = unreal.load_class(None, '/Script/Nyablo.NyabloEnemy')
STATS = {   # hp, damage, reach, radius, walk speed, extra enemy settings
    'Hero':   dict(max_health=220.0, attack_damage=40.0, attack_reach=140.0, attack_radius=130.0, walk_speed=650.0,
                   # fallback single swing = Mixamo inward slash (67f); the combo below normally overrides it
                   attack_start_fraction=24/66, attack_hit_fraction=37/66, attack_end_fraction=49/66, attack_play_rate=1.6),
    'Brute':  dict(max_health=140.0, attack_damage=30.0, attack_reach=170.0, attack_radius=150.0, walk_speed=230.0, attack_range=260.0, attack_cooldown=1.8),
    'Rogue':  dict(max_health=70.0, attack_damage=14.0, attack_reach=120.0, attack_radius=110.0, walk_speed=290.0, attack_range=190.0, attack_cooldown=1.0),
    'Archer': dict(max_health=60.0, attack_damage=12.0, walk_speed=250.0,
                   ranged=True, preferred_range=950.0, attack_cooldown=2.2, timed_attack_windup=0.7, timed_attack_duration=1.1),
}
MX = '/Game/MixedVFX/Particles'
VFX = {   # Fab VFX packs: MixedVFX (CC BY 4.0, G.G.), Free_Spells, A_Surface_Footstep
    # 4-28: the blade trail (TRAIL_VFX) replaces the chest-height slash arc, which never followed the cut
    'Hero': dict(hit_vfx=(f'{MX}/Slashes/SeparateParts/Hits/NS_VampireSlash_Hit', 0.6),
                 footstep_vfx=('/Game/A_Surface_Footstep/Niagara_FX/ParticleSystems/PSN_Dirt_Surface', 1.0),
                 skill_vfx=('/Game/Free_Spells/VFX_Niagara/NS_Free_Spells_Shockwave', 1.6)),
    'Brute': dict(hit_vfx=('/Game/Nyablo/VFX/NS_MeleeContact', 1.2),
                  footstep_vfx=('/Game/A_Surface_Footstep/Niagara_FX/ParticleSystems/PSN_Gravel_Surface', 1.0)),
    'Rogue': dict(hit_vfx=('/Game/Nyablo/VFX/NS_MeleeContact', 0.9)),
    'Archer': dict(hit_vfx=('/Game/Nyablo/VFX/NS_MeleeContact', 0.9)),
}
HERO_ATTACK_SPEED = 1.5   # user request 2026-09-27: combo 1.5x faster (clip rates 1.4 -> 2.1)
STRIKE_RATE_SCALE = 1.7   # 4-28: the snap (hand speed-up -> hit) plays 1.7x the recovery rate (2.1 -> 3.57)
# 4-34: project copy of SERLO's NS_Trail_03; lifetime 0.18 s and color intensity 8
# keep the passing blade visible. The imported source asset remains the reference.
TRAIL_VFX = {'Hero': '/Game/Nyablo/VFX/NS_HeroBladeTrail'}
IDLE_CLIP = {'Hero': 'ssidle'}   # Mixamo 'Sword And Shield Idle': combat stance instead of Tripo's stand-at-attention idle (4-17)
IDLE_VARIANT_CLIP = {'Hero': 'ssplay'}   # Mixamo 'Sword And Shield Sword Play Idle' (user pick I5, 4-27)
MOVE_CLIP = {'Hero': 'runintent', 'Brute': 'walk', 'Rogue': 'walk', 'Archer': 'walk'}   # Hero: Mixamo 'Running With Intention' (user pick M2, 4-27)
ATTACK_CLIP = {'Hero': 'inward', 'Brute': 'slash', 'Rogue': 'slash', 'Archer': None}   # Tripo 'shoot' is a gun roll
for i, (name, clip, (x, y), yaw, t) in enumerate(CAST):
    sk, anims = chars[name]
    loc, rot = blender_to_ue((x, y, 0.0), yaw)
    loc = unreal.Vector(loc.x, loc.y, CHAR_HEIGHT_M[name] * 50 + 5)          # capsule centre above the floor
    actor = eas.spawn_actor_from_class(HERO_CLASS if name == 'Hero' else ENEMY_CLASS, loc, rot)
    actor.set_actor_label(f'{name}_{i}')
    actor.set_folder_path('Characters')
    actor.set_editor_property('character_mesh', sk)
    actor.set_editor_property('idle_anim', anims.get(IDLE_CLIP.get(name, 'idle'), anims['idle']))
    actor.set_editor_property('move_anim', anims.get(MOVE_CLIP[name]))
    if IDLE_VARIANT_CLIP.get(name) in anims:   # played once after standing still a while (4-27)
        actor.set_editor_property('idle_variant_anim', anims[IDLE_VARIANT_CLIP[name]])
    actor.set_editor_property('attack_anim', anims.get(ATTACK_CLIP[name]) if ATTACK_CLIP[name] else None)
    for k, v in STATS[name].items():
        actor.set_editor_property(k, v)
    for prop, (path, vscale) in VFX[name].items():
        system = EAL.load_asset(path)
        if not system:
            log('missing vfx', path)
            continue
        actor.set_editor_property(prop, system)
        scale_prop = prop.replace('_vfx', '_vfx_scale')
        if prop != 'footstep_vfx':
            actor.set_editor_property(scale_prop, vscale)
    if name in TRAIL_VFX:
        trail = EAL.load_asset(TRAIL_VFX[name])
        if trail:
            actor.set_editor_property('trail_vfx', trail)
            actor.set_editor_property('trail_hold', 0.06)
        else:
            log('missing trail vfx', TRAIL_VFX[name])
    if name == 'Hero' and HERO_CAPE:
        actor.set_editor_property('cape_asset', HERO_CAPE)
    if name == 'Hero':
        # Mixamo sword clips retargeted in process_character.py; frames from the right-hand speed curve (anim_motion.py)
        combo = []
        # 4-25: three diagonal downward cuts of Mixamo 'One Hand Sword Combo' + the leaping 'Power Slash' slam as finisher
        # (right-hand speed per frame: tools/hand_speed.py). The old inward / outward / downward set stays in the FBX.
        # strike = frame where the right hand speeds up (hand_speed.py, 4-28): wind-up plays slower, the snap faster
        # hit = frame where the sword tip passes chest height in front of the body, moving down (4-28 tip path check;
        # the old hand-speed-peak frames froze the hit-stop with the blade still overhead / behind; re-measured on the
        # --attack-body clips, whose crouch + lean bring the blade down about a frame sooner)
        # Normal cuts continue through impact without an attacker hold (4-41).
        # The shockwave retains its distinct extended-pose hold.
        for clip, last, start, strike, hit, end, rate, windup, dmg, follow, hold in (
                ('onehand', 137, 16, 26, 33, 40, 1.4, 0.75, 1.0, 5, 0.0),
                ('onehand', 137, 45, 56, 62, 68, 1.4, 0.75, 1.0, 5, 0.0),
                ('onehand', 137, 75, 86, 91, 98, 1.4, 0.75, 1.1, 5, 0.0),
                ('power', 74, 18, 38, 42, 50, 1.4, 0.65, 1.8, 4, 0.06)):   # spinning leap / shockwave
            if clip not in anims:
                log('missing combo clip', clip)
                continue
            c = unreal.NyabloAttackClip()
            c.set_editor_property('anim', anims[clip])
            for prop, frame in (('start_fraction', start), ('hit_fraction', hit), ('end_fraction', end)):
                c.set_editor_property(prop, (frame - 1) / (last - 1))
            c.set_editor_property('play_rate', rate * HERO_ATTACK_SPEED)
            c.set_editor_property('strike_fraction', (strike - 1) / (last - 1))
            windup_rate = rate * HERO_ATTACK_SPEED * windup
            strike_rate = rate * HERO_ATTACK_SPEED * STRIKE_RATE_SCALE
            if clip == 'onehand':
                # Raised-hand backswing: show the load, hand lead and blade
                # release at gameplay speed before the existing follow-through.
                # 10-01: quick blade. The top settle / end hold (rhythm C) read as a club, so both are off; wind-up,
                # snap and follow-through all run fast and the recovery hands over to the next cut sooner
                windup_rate = 2.2
                strike_rate = 2.6
            c.set_editor_property('windup_rate', windup_rate)
            c.set_editor_property('strike_rate', strike_rate)
            c.set_editor_property('follow_frames', follow)
            c.set_editor_property('follow_rate', 2.6 if clip == 'onehand' else rate * HERO_ATTACK_SPEED * 1.25)
            c.set_editor_property('hold_seconds', hold)
            c.set_editor_property('recover_rate', rate * HERO_ATTACK_SPEED * (1.3 if clip == 'onehand' else 1.0))
            c.set_editor_property('damage_scale', dmg)
            # body travel over the window (Blender x forward / y left, character units) -> actor cm (X fwd, Y right)
            unit_cm = CHAR_GRIP[name][1]
            win = next((w for w in CHAR_LUNGES.get(name, {}).get(clip, []) if w['start'] == start), None)
            if win:
                tx, ty = win['travel_m']
                c.set_editor_property('lunge', unreal.Vector(tx * unit_cm, -ty * unit_cm, 0.0))
                log('lunge', name, clip, start, round(tx * unit_cm), round(-ty * unit_cm))
            combo.append(c)
        actor.set_editor_property('combo_attacks', combo)
        actor.set_editor_property('skill_clip_index', len(combo) - 1)   # shockwave = downward slam
    natural = CLIP_SPEED_CM[name].get(MOVE_CLIP[name], 0.0)
    if natural > 1.0:
        actor.set_editor_property('move_anim_speed', natural)
    # grips are computed in the REFERENCE pose: OnConstruction shows the idle anim in the editor, and a combat-stance
    # idle (bent arm) put the sword at the wrist (4-20). Drop the idle while measuring, restore it afterwards.
    idle_anim = actor.get_editor_property('idle_anim')
    actor.set_editor_property('idle_anim', None)
    actor.refresh_visuals()                     # mesh + capsule placed -> sockets valid (ref pose)
    comp = actor.get_editor_property('mesh')
    comp.set_editor_property('animation_mode', unreal.AnimationMode.ANIMATION_BLUEPRINT)   # no anim -> reference pose
    wscale = CHAR_HEIGHT_M[name] / WEAPON_BASE_HEIGHT_M[name]
    for prop, side, style in GRIP[name]:
        fist_data, unit_cm = CHAR_GRIP.get(name, ({}, 1.0))
        rel = grip_relative(actor, comp, side, style, wscale, fist_data.get(side) if name == 'Hero' else None, unit_cm)
        ss = comp.get_socket_transform(f'{side}_Hand', unreal.RelativeTransformSpace.RTS_WORLD).scale3d
        local = unreal.Transform(location=unreal.Vector(rel.translation.x / ss.x, rel.translation.y / ss.y, rel.translation.z / ss.z),
                                 rotation=rel.rotation.rotator(),
                                 scale=unreal.Vector(wscale / ss.x, wscale / ss.y, wscale / ss.z))
        key = 'weapon_right' if side == 'R' else 'weapon_left'
        actor.set_editor_property(key + '_mesh', meshes[prop])
        actor.set_editor_property(key + '_transform', local)
    actor.set_editor_property('idle_anim', idle_anim)
    actor.refresh_visuals()
    log('actor', name, i, actor.get_class().get_name())

# cameras: reference framing + close-ups (aimed at the actor) used to check rig/weapons
cam = eas.spawn_actor_from_class(unreal.CameraActor, unreal.Vector(425, 2625, 3450), unreal.Rotator(0, -50.0, -97.4))   # frames plaza + surrounding houses
cam.set_actor_label('ShotCamera')
cam.camera_component.set_editor_property('field_of_view', 50.0)

by_label = {a.get_actor_label(): a for a in eas.get_all_level_actors()}
for label, target, (fwd, side, up), height in (('HeroCloseCamera', 'Hero_0', (420, 160, 230), 2.2),
                                                ('BruteCloseCamera', 'Brute_1', (560, -180, 300), 3.0),
                                                ('RogueCloseCamera', 'Rogue_4', (420, 150, 220), 2.05),
                                                ('ArcherCloseCamera', 'Archer_5', (420, -150, 220), 2.05)):
    t = by_label[target]
    feet = ML.subtract_vector_vector(t.get_actor_location(), unreal.Vector(0, 0, height * 50))   # actor = capsule centre
    aim = ML.add_vector_vector(feet, unreal.Vector(0, 0, height * 55))
    loc = ML.add_vector_vector(ML.add_vector_vector(ML.add_vector_vector(
        feet, ML.multiply_vector_float(t.get_actor_forward_vector(), fwd)),
        ML.multiply_vector_float(t.get_actor_right_vector(), side)), unreal.Vector(0, 0, up))
    c = eas.spawn_actor_from_class(unreal.CameraActor, loc, ML.find_look_at_rotation(loc, aim))
    c.set_actor_label(label)
    c.camera_component.set_editor_property('field_of_view', 40.0)

# gameplay-angle cameras on the hero (same pitch/yaw/distance as ANyabloHero's boom) for look-dev A/B shots
hero = by_label['Hero_0']
for label, pitch, dist, fov in (('GameplayCamera', -40.0, 2100.0, 50.0), ('HeroMidCamera', -25.0, 600.0, 40.0)):
    rot = unreal.Rotator(0.0, pitch, -97.4)
    loc = ML.subtract_vector_vector(hero.get_actor_location(), ML.multiply_vector_float(ML.get_forward_vector(rot), dist))
    c = eas.spawn_actor_from_class(unreal.CameraActor, loc, rot)
    c.set_actor_label(label)
    c.camera_component.set_editor_property('field_of_view', fov)

les.save_current_level()
log('PLAZA_BUILD_DONE', len(layout), 'placements', len(CAST), 'characters')
