import json, glob, sys, os
W = 'D:/HarnessPrograming/diablo/workspace/deathknight/'
def g(d):
    return glob.glob(W + d + '/**/*.glb', recursive=True)[0].replace(os.sep, '/')
parts = {
 'head': {'name': 'head', 'quad': [0, 0], 'init': 'top', 'region': {'z': [0.845, 1.0]}, 'src': 'parts/head_low'},
 'arm_r': {'name': 'arm_r', 'quad': [1, 0], 'init': 'axis', 'region': {'z': [0.42, 0.76], 'y': [-1, -0.155]}, 'src': 'parts/arm_low'},
 'arm_l': {'name': 'arm_l', 'quad': [1, 0], 'init': 'axis', 'mirror': True, 'share_uv_with': 'arm_r', 'region': {'z': [0.42, 0.76], 'y': [0.155, 1]}, 'src': 'parts/arm_low'},
 'torso': {'name': 'torso', 'quad': [0, 1], 'init': 'top', 'region': {'z': [0.58, 0.87], 'y': [-0.2, 0.2]}, 'src': 'parts/torso_low'},
 'legs': {'name': 'legs', 'quad': [1, 1], 'init': 'bottom', 'region': {'z': [0.0, 0.60], 'y': [-0.16, 0.16]}, 'src': 'parts/legs_low'},
}
tag, names = sys.argv[1], sys.argv[2].split(',')
extra = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
ps = []
for n in names:
    p = dict(parts[n]); p.update(extra.get(n, {})); src = p.pop('src'); p['glb'] = g(src)
    nd = W + src + '/T_normal2k_dx.png'
    if os.path.exists(nd) and not p.get('share_uv_with'):
        p['normal_dx'] = nd
    ps.append(p)
cfg = {'tail': {'part': 'legs', 'x_below': -0.07, 'z_below': 0.5}, 'body_pts': W + 'body/body_pts.npy', 'out': W + 'assembly/' + tag, 'name': os.environ.get('NAME', 'DK'), 'atlas': 4096, 'parts': ps}
json.dump(cfg, open(W + f'assembly/{tag}.json', 'w'), indent=1)
print(W + f'assembly/{tag}.json')
