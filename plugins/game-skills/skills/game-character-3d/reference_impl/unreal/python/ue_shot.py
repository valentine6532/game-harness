"""Open /Game/Maps/Plaza in the editor, render the real viewport through level cameras, save shots, quit.

Run through Scripts/run_shots.sh, which launches:
UnrealEditor.exe Nyablo.uproject -ExecCmds="py <abs path>/ue_shot.py"
    "-ini:EditorSettings:[/Script/UnrealEd.EditorPerformanceSettings]:bThrottleCPUWhenNotForeground=False"
- -ExecutePythonScript closes the editor as soon as the script returns, so tick callbacks never run: use -ExecCmds.
- Without the -ini override the editor renders ~1 fps in the background and high-res shots never complete.
- Scene captures were tried and dropped: no Lumen GI / eye adaptation, results lag a frame.
- The viewport is refreshed with editor_invalidate_viewports(); editor_set_viewport_realtime() is not used
  because it raises an editor ensure dialog ("No realtime override was found").
Config: Scripts/shot_config.json
  {"name": "plaza", "res": [1536, 1024], "warmup": 45, "gap": 8,
   "shots": [{"camera": "ShotCamera", "bias": -1, "pp": {"film_slope": 0.6}, "light": {"sky": 4}}, ...]}
  "pp" = PostProcessSettings props (lists become Vector4/LinearColor), "light" = sun/sky/sun_angle/sun_rot/fog, sun_color/sky_color (0-255), fog_color/rayleigh (linear).
Output: Saved/Screenshots/WindowsEditor/<name>_<index>_<camera>.png
"""
import json
import os
import time

import unreal


def _main():
    cfg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shot_config.json')))
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les.load_level(cfg.get('map', '/Game/Maps/Plaza'))
    # shots may use {"view": {"loc": [x,y,z], "rot": [roll,pitch,yaw], "fov": 50}} instead of a level camera:
    # the editor viewport is moved (no actor is spawned, so the map never becomes dirty / asks to save on quit)
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    actors = eas.get_all_level_actors()
    cams = {a.get_actor_label(): a for a in actors if isinstance(a, unreal.CameraActor)}
    ppv = next((a for a in actors if isinstance(a, unreal.PostProcessVolume)), None)
    for a in actors:
        if isinstance(a, unreal.SkeletalMeshActor):
            a.skeletal_mesh_component.set_update_animation_in_editor(True)
    les.editor_set_game_view(True)
    shots = cfg['shots']
    gap = cfg.get('gap', 8)
    state = {'i': 0, 'phase': 'warmup', 'since': time.time(), 'last': 0.0}

    def setup(shot):
        if 'view' in shot:
            v = shot['view']
            les.eject_pilot_level_actor()
            ues.set_level_viewport_camera_info(unreal.Vector(*v['loc']), unreal.Rotator(*v['rot']))
            les.set_level_viewport_fov(float(v.get('fov', 50)), les.get_active_viewport_config_key())
        else:
            cam = cams[shot['camera']]
            les.pilot_level_actor(cam)
            les.set_level_viewport_fov(cam.camera_component.get_editor_property('field_of_view'),
                                       les.get_active_viewport_config_key())
        pp = dict(shot.get('pp', {}))
        if 'bias' in shot:
            pp['auto_exposure_bias'] = shot['bias']
        if ppv is not None and pp:
            s = ppv.get_editor_property('settings')
            for k, v in pp.items():
                if isinstance(v, list):
                    v = unreal.Vector4(*v) if len(v) == 4 else unreal.LinearColor(*v, 1.0)
                s.set_editor_property('override_' + k, True)
                s.set_editor_property(k, v)
            ppv.set_editor_property('settings', s)
        light = shot.get('light', {})   # optional lighting experiment: sun / sky / sun_angle / fog
        for a in actors:
            if isinstance(a, unreal.DirectionalLight):
                c = a.get_component_by_class(unreal.DirectionalLightComponent)
                if 'sun' in light:
                    c.set_editor_property('intensity', float(light['sun']))
                if 'sun_angle' in light:
                    c.set_editor_property('light_source_angle', float(light['sun_angle']))
                if 'sun_rot' in light:   # [roll, pitch, yaw]
                    a.set_actor_rotation(unreal.Rotator(*light['sun_rot']), False)
                if 'sun_color' in light:   # [r, g, b] 0-255
                    c.set_editor_property('light_color', unreal.Color(*light['sun_color'], 255))
            elif isinstance(a, unreal.SkyLight):
                c = a.get_component_by_class(unreal.SkyLightComponent)
                if 'sky' in light:
                    c.set_editor_property('intensity', float(light['sky']))
                if 'sky_color' in light:
                    c.set_editor_property('light_color', unreal.Color(*light['sky_color'], 255))
            elif isinstance(a, unreal.ExponentialHeightFog):
                c = a.get_component_by_class(unreal.ExponentialHeightFogComponent)
                if 'fog' in light:
                    c.set_editor_property('fog_density', float(light['fog']))
                if 'fog_color' in light:   # [r, g, b] linear
                    c.set_editor_property('fog_inscattering_luminance', unreal.LinearColor(*light['fog_color'], 1.0))
            elif isinstance(a, unreal.SkyAtmosphere) and 'rayleigh' in light:
                a.get_component_by_class(unreal.SkyAtmosphereComponent).set_rayleigh_scattering(unreal.LinearColor(*light['rayleigh'], 1.0))

    def tick(dt):
        now = time.time()
        if now - state['last'] < 0.25:
            return
        state['last'] = now
        les.editor_invalidate_viewports()
        waited = now - state['since']
        if state['phase'] == 'warmup' and waited >= cfg.get('warmup', 45) - gap:
            setup(shots[0])
            state.update(phase='settle', since=now)
        elif state['phase'] == 'settle' and waited >= gap:
            shot = shots[state['i']]
            path = f"{cfg['name']}_{state['i']}_{shot.get('camera', 'view')}.png"
            state['file'] = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.screen_shot_dir()), path)
            if os.path.exists(state['file']):
                os.remove(state['file'])
            state['i'] += 1                                   # update state first: the screenshot call
            state.update(phase='next' if state['i'] < len(shots) else 'done', since=now)   # can re-enter tick
            unreal.AutomationLibrary.take_high_res_screenshot(cfg['res'][0], cfg['res'][1], path,
                                                              camera=cams.get(shot.get('camera')))
            unreal.log(f'NYABLO_SHOT {path}')
        elif state['phase'] == 'next' and (os.path.exists(state['file']) or waited >= 60):   # shot written
            setup(shots[state['i']])
            state.update(phase='settle', since=now)
        elif state['phase'] == 'done' and waited >= 15:
            unreal.unregister_slate_post_tick_callback(unreal._nyablo_shot_handle)
            les.eject_pilot_level_actor()
            unreal.log('NYABLO_SHOT_QUIT')
            unreal.SystemLibrary.quit_editor()

    def safe_tick(dt):
        try:
            tick(dt)
        except Exception as exc:          # a bad shot config would otherwise raise every tick and hang the editor
            unreal.unregister_slate_post_tick_callback(unreal._nyablo_shot_handle)
            unreal.log_error(f'NYABLO_SHOT_FAILED {exc!r}')
            unreal.SystemLibrary.quit_editor()

    unreal._nyablo_shot_handle = unreal.register_slate_post_tick_callback(safe_tick)


if os.environ.get('NYABLO_SHOT_ACTIVE') != '1':   # -ExecCmds may run the file twice; env is process-wide
    os.environ['NYABLO_SHOT_ACTIVE'] = '1'
    try:
        _main()
    except Exception as exc:                                  # never leave a headless editor hanging
        unreal.log_error(f'NYABLO_SHOT_FAILED {exc!r}')
        unreal.SystemLibrary.quit_editor()
