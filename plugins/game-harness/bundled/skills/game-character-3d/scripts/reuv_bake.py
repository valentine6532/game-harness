"""Blender: new clean UV layout for a Tripo retopo/rig mesh + re-baked textures (4-21).

blender -b --python reuv_bake.py -- --rig rig_or_anim.fbx --parts segment.glb --high high.glb     --src-dir dir_with_old_textures --name Hero --out dir [--min-faces 60] [--split-rounds 4] [--res 4096] [--uv-only]

Tripo's retopology unwraps into ~2,400 islands, 1,200 of them 1-4 faces: seams everywhere, mip bleeding, and a
texture nobody can read or touch up. Here:

1. charts = Tripo body parts (segmentation GLB, nearest point), borders smoothed, scraps < --min-faces folded into
   a neighbour.
2. each chart is cut into a topological disk (tree-cotree, cut_chart): the needed cuts (handles such as the fist grip
   hole or a belt loop, links between tube openings) take the cheapest arcs, weighted to the back / underside.
3. unwrap (MINIMUM_STRETCH; charts it collapses are redone ANGLE_BASED), charts with uneven texel density are split
   in two by normal direction and everything is re-unwrapped (--split-rounds); equal texel density, pack.
4. BaseColor / ORM: transferred old UV -> new UV on the same mesh (Cycles EMIT bake, texture read through the old
   UV map, raw values) - no ray error. Normal + AO: baked from the Tripo high-poly onto the new UV (fit as
   bake_normal_onto.py). ORM.R = 0.4 + 0.6 * AO (full AO turns fur near-black, 4-8).

Writes T_<Name>_{BaseColor,ORM,Normal}.png, uv_new.npy / uv_old.npy (per loop), loop_verts.npy (mesh check for
process_character --uv), loop_start/loop_total/face_island.npy (draw_uv_layout.py), reuv.json (stats).
"""
import argparse, json, sys, time
from collections import defaultdict
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector, kdtree

p = argparse.ArgumentParser()
p.add_argument('--rig', required=True)
p.add_argument('--high')
p.add_argument('--src-dir', required=True)
p.add_argument('--name', required=True)
p.add_argument('--out', required=True)
p.add_argument('--parts', help='Tripo segmentation GLB: one chart per body part')
p.add_argument('--min-faces', type=int, default=60)
p.add_argument('--margin', type=float, default=0.004)
p.add_argument('--res', type=int, default=4096)
p.add_argument('--unwrap', default='MINIMUM_STRETCH', choices=['ANGLE_BASED', 'CONFORMAL', 'MINIMUM_STRETCH'])
p.add_argument('--split-rounds', type=int, default=4, help='split charts whose texel density is too uneven, re-unwrap')
p.add_argument('--split-threshold', type=float, default=0.12,
               help='split a chart when this share of its area is off its own median density by > 2x')
p.add_argument('--split-by', default='normal', choices=['normal', 'shorter'],
               help='normal = 4-21 behaviour; shorter = normal or position split, whichever cut is shorter (4-23)')
p.add_argument('--head-weight', type=float, default=1.0,
               help='texel area weight of faces skinned to the Head bone (4-23: 2.0; 1.0 = plain equal density)')
p.add_argument('--hand-weight', type=float, default=1.0, help='same for L_Hand / R_Hand')
p.add_argument('--facing-weight', type=float, nargs=2, default=[1.0, 1.0], metavar=('FRONT', 'BACK'),
               help='area weight of front (+X) faces / back (-X) or underside faces')
p.add_argument('--align-rotation', action='store_true', help='uv.align_rotation(AUTO) before packing')
p.add_argument('--uv-only', action='store_true', help='stop after the unwrap (layout / stats only)')
a = p.parse_args(sys.argv[sys.argv.index('--') + 1:])
out = Path(a.out).resolve()        # Image.save() silently writes nothing for a relative path
out.mkdir(parents=True, exist_ok=True)
t0 = time.time()
stats = {}

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
bpy.ops.import_scene.fbx(filepath=a.rig, use_anim=True, ignore_leaf_bones=False)   # same options as process_character
arm = next(o for o in sc.objects if o.type == 'ARMATURE')
low = next(o for o in sc.objects if o.type == 'MESH' and o.parent == arm)
for o in list(sc.objects):
    if o is not low:
        bpy.data.objects.remove(o, do_unlink=True)
low.modifiers.clear()                  # rest pose (bakes against the high-poly need the undeformed shape)
low.animation_data_clear()
me = low.data
assert len(me.uv_layers) == 1, [l.name for l in me.uv_layers]
old_uv = me.uv_layers[0]
old_uv.name = 'old'
nl, nf = len(me.loops), len(me.polygons)
loop_verts = np.zeros(nl, dtype=np.int32)
me.loops.foreach_get('vertex_index', loop_verts)
np.save(out / 'loop_verts.npy', loop_verts)
uv_old = np.zeros(nl * 2, dtype=np.float32)
old_uv.data.foreach_get('uv', uv_old)
uv_old = uv_old.reshape(-1, 2)

# ---------------------------------------------------------------- 1. old islands + seam graph
bm = bmesh.new()
bm.from_mesh(me)
bm.faces.ensure_lookup_table()
bm.edges.ensure_lookup_table()
uvl = bm.loops.layers.uv['old']


def uv_continuous(l, l2):
    """edge shared by loops l (face A) and l2 (face B): same UVs on both ends?"""
    a1, b1 = l[uvl].uv, l.link_loop_next[uvl].uv
    if l2.vert == l.vert:
        a2, b2 = l2[uvl].uv, l2.link_loop_next[uvl].uv
    else:
        a2, b2 = l2.link_loop_next[uvl].uv, l2[uvl].uv
    return (a1 - a2).length < 1e-5 and (b1 - b2).length < 1e-5


parent = list(range(nf))


def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


seam_edges = []          # (edge index, face a, face b) where the old UV is cut between two faces
for e in bm.edges:
    if len(e.link_loops) != 2:
        continue
    l, l2 = e.link_loops
    if uv_continuous(l, l2):
        ra, rb = find(l.face.index), find(l2.face.index)
        if ra != rb:
            parent[ra] = rb
    else:
        seam_edges.append((e.index, l.face.index, l2.face.index))
old_island = np.array([find(i) for i in range(nf)])
stats['old_islands'] = int(len(set(old_island)))
stats['old_tiny_le4'] = int(sum(1 for c in np.unique(old_island, return_counts=True)[1] if c <= 4))

face_area = np.array([f.calc_area() for f in bm.faces])
part_of_face = np.zeros(nf, dtype=np.int32)
if a.parts:
    before = set(sc.objects)
    bpy.ops.import_scene.gltf(filepath=a.parts)
    parts = [o for o in sc.objects if o not in before and o.type == 'MESH']
    # same fit as process_character.face_classes_from_parts: bounds + 4 yaw turns onto the rig mesh
    lp = np.array([low.matrix_world @ v.co for v in me.vertices])
    pts, pid = [], []
    for i, o in enumerate(parts):
        for v in list(o.data.vertices)[::3]:
            pts.append(o.matrix_world @ v.co)
            pid.append(i)
    pts = np.array(pts)
    tree = kdtree.KDTree(len(lp))
    for i, x in enumerate(lp):
        tree.insert(x, i)
    tree.balance()
    llo, lhi = lp.min(0), lp.max(0)
    best = None
    for k in range(4):
        rz = np.array(Matrix.Rotation(k * np.pi / 2, 3, 'Z'))
        q = pts @ rz.T
        lo, hi = q.min(0), q.max(0)
        s = (lhi[2] - llo[2]) / max(hi[2] - lo[2], 1e-6)
        off = (llo + lhi) / 2 - s * (lo + hi) / 2
        off[2] = llo[2] - s * lo[2]
        err = float(np.mean([tree.find(x)[2] for x in (q * s + off)[::40]]))
        if best is None or err < best[0]:
            best = (err, q * s + off)
    ptree = kdtree.KDTree(len(best[1]))
    for i, x in enumerate(best[1]):
        ptree.insert(x, i)
    ptree.balance()
    part_of_face = np.array([pid[ptree.find(low.matrix_world @ f.calc_center_median())[1]] for f in bm.faces])
    for o in parts:
        bpy.data.objects.remove(o, do_unlink=True)
    stats['parts'] = len(parts)

# ---------------------------------------------------------------- 2. charts = body parts, cut open into disks
# (a first try merged Tripo's crumbs into their neighbours: 401 ragged, branching islands, 27 % of the texture used)
assert a.parts, '--parts (Tripo segmentation GLB) is required'
from collections import Counter
import heapq

face_nb = [[] for _ in range(nf)]            # (neighbour face, edge index)
for e in bm.edges:
    if len(e.link_faces) == 2:
        f0, f1 = e.link_faces[0].index, e.link_faces[1].index
        face_nb[f0].append((f1, e.index))
        face_nb[f1].append((f0, e.index))
edge_len = np.array([e.calc_length() for e in bm.edges])
label = part_of_face.copy()
for _ in range(3):                           # smooth the ragged nearest-point part borders (majority of edge neighbours)
    new = label.copy()
    for f in range(nf):
        c = Counter(label[g] for g, _ in face_nb[f])
        c[label[f]] += 1
        new[f] = c.most_common(1)[0][0]
    label = new


def components(lbl):
    comp = -np.ones(nf, dtype=np.int64)
    n = 0
    for f in range(nf):
        if comp[f] >= 0:
            continue
        comp[f] = n
        stack = [f]
        while stack:
            x = stack.pop()
            for g, _ in face_nb[x]:
                if comp[g] < 0 and lbl[g] == lbl[x]:
                    comp[g] = n
                    stack.append(g)
        n += 1
    return comp, n


while True:                                  # absorb small scraps into the neighbour label with the longest border
    comp, n = components(label)
    sizes = np.bincount(comp)
    moved = 0
    for c in np.argsort(sizes):
        if sizes[c] >= a.min_faces:
            break
        faces = np.nonzero(comp == c)[0]
        border = Counter()
        for f in faces:
            for g, ei in face_nb[f]:
                if comp[g] != c:
                    border[label[g]] += edge_len[ei]
        if border:
            label[faces] = border.most_common(1)[0][0]
            moved += 1
    if not moved:
        break
comp, n_charts = components(label)
stats['charts'] = int(n_charts)

mw = low.matrix_world
vco = np.array([(mw @ v.co)[:] for v in bm.verts])
vno = np.array([(mw.to_3x3() @ v.normal).normalized()[:] for v in bm.verts])
height = vco[:, 2].max() - vco[:, 2].min()
# front = +X in the Tripo rest pose (4-12: the tail sits at X < 0); check: the tail tip is the lowest-X point below the waist
low_half = vco[:, 2] < vco[:, 2].min() + 0.6 * height
stats['tail_side_x'] = round(float(vco[low_half, 0].min() / height), 3)


def cut_cost(v1, v2):
    """seam cost: length, x3 on the front (+X), x1.5 facing up (quarter-view camera) -> seams go to the back / below"""
    nrm = vno[v1] + vno[v2]
    nrm /= max(np.linalg.norm(nrm), 1e-9)
    return float(np.linalg.norm(vco[v1] - vco[v2]) * (1 + 3 * max(0.0, nrm[0]) + 1.5 * max(0.0, nrm[2])))


def cut_chart(F):
    """Cut one chart into a topological disk (tree-cotree): shortest-path forest from the chart border (costs as
    cut_cost), a maximum dual spanning tree over the remaining edges; each edge left over closes one needed cut (a
    handle - fist grip hole, belt loop, arm touching the body - or a link between two openings of a tube). The cut =
    that edge + the two tree paths back to the border: the cheapest arcs, mostly on the back / underside."""
    cuts = set()
    ecount = Counter(e.index for f in F for e in bm.faces[f].edges)
    # an edge is a border of the chart unless exactly two chart faces share it (non-manifold edges are cut too)
    border = {ei for ei, k in ecount.items() if k != 2 or len(bm.edges[ei].link_faces) != 2}
    inner = [ei for ei in ecount if ei not in border]
    src = {v.index for ei in border for v in bm.edges[ei].verts}
    if not src:                              # closed piece: slit one edge at the most hidden vertex
        e0 = min(inner, key=lambda ei: cut_cost(*(v.index for v in bm.edges[ei].verts)) - 10 * edge_len[ei])
        cuts.add(e0)
        inner.remove(e0)
        src = {v.index for v in bm.edges[e0].verts}
    adj = defaultdict(list)
    for ei in inner:
        v1, v2 = (v.index for v in bm.edges[ei].verts)
        w = cut_cost(v1, v2)
        adj[v1].append((v2, w, ei))
        adj[v2].append((v1, w, ei))
    dist = {v: 0.0 for v in src}
    prev = {}
    heap = [(0.0, v) for v in src]
    heapq.heapify(heap)
    while heap:
        d, x = heapq.heappop(heap)
        if d > dist[x]:
            continue
        for y, w, ei in adj[x]:
            if d + w < dist.get(y, 1e18):
                dist[y] = d + w
                prev[y] = (x, ei)
                heapq.heappush(heap, (d + w, y))
    tree = {ei for _, ei in prev.values()}
    rest = [ei for ei in inner if ei not in tree]
    rest.sort(key=lambda ei: -(dist[bm.edges[ei].verts[0].index] + dist[bm.edges[ei].verts[1].index]
                               + cut_cost(*(v.index for v in bm.edges[ei].verts))))
    par = {f: f for f in F}

    def root(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for ei in rest:
        f0, f1 = (f.index for f in bm.edges[ei].link_faces)
        r0, r1 = root(f0), root(f1)
        if r0 != r1:
            par[r0] = r1
            continue
        cuts.add(ei)                         # left over -> one needed cut
        for v in bm.edges[ei].verts:
            x = v.index
            while x in prev:
                x, pe = prev[x]
                cuts.add(pe)
    return cuts


fno = np.array([(mw.to_3x3() @ f.normal).normalized()[:] for f in bm.faces])

# body region per face from the skin weights (majority of its vertices' dominant bone) -> texel area weight (4-23):
# the face is what the close camera looks at, the back / underside what the quarter view never shows
REGIONS = {'head': ('Head', 'NeckTwist01', 'NeckTwist02'), 'hand': ('L_Hand', 'R_Hand'),
           'torso': ('Spine01', 'Spine02', 'Waist')}
gname = [g.name for g in low.vertex_groups]
vreg = np.full(len(me.vertices), '', dtype=object)
for v in me.vertices:
    if v.groups:
        b = gname[max(v.groups, key=lambda g: g.weight).group]
        vreg[v.index] = next((r for r, bones in REGIONS.items() if b in bones), '')
face_region = np.array([Counter(vreg[v.index] for v in f.verts).most_common(1)[0][0] for f in bm.faces])
face_w = np.ones(nf)
face_w[face_region == 'head'] *= a.head_weight
face_w[face_region == 'hand'] *= a.hand_weight
face_w[fno[:, 0] > 0.3] *= a.facing_weight[0]
face_w[(fno[:, 0] < -0.3) | (fno[:, 2] < -0.6)] *= a.facing_weight[1]
stats['region_faces'] = {r: int((face_region == r).sum()) for r in REGIONS}


fcen = np.array([(mw @ f.calc_center_median())[:] for f in bm.faces])


def split_boundary(F, lab):
    """length of the cut between the two halves (short = two compact pieces, long = combs / fringes)"""
    side = dict(zip(F.tolist(), lab.tolist()))
    return sum(edge_len[ei] for f in F for g, ei in face_nb[f] if g in side and side[g] != side[f]) / 2


def split_chart(F):
    """two halves: by face normal (2-means seeded by the most opposite faces) or by position (plane through the
    centre across the longest axis) - whichever cut is shorter. On the tattered cape the normal split alone made
    comb / star shaped pieces along the pleats and cost ~10 % of the texture in packing (4-23)."""
    F = np.array(F)
    fn, ln = split_by_normal(F)
    if a.split_by == 'normal':
        return fn, ln
    x = fcen[F] - np.average(fcen[F], axis=0, weights=face_area[F])
    axis = np.linalg.svd(x * np.sqrt(face_area[F])[:, None], full_matrices=False)[2][0]
    lp = (x @ axis > 0).astype(int)
    if lp.min() == lp.max() or split_boundary(F, lp) < split_boundary(F, ln):
        return F, lp
    return fn, ln


def split_by_normal(F):
    n = fno[F]
    s0 = int(np.argmax(-n @ n.mean(0)))
    s1 = int(np.argmin(n @ n[s0]))
    cen = np.stack([n[s0], n[s1]])
    lab = np.zeros(len(F), dtype=int)
    for _ in range(8):
        lab = np.argmax(n @ cen.T, 1)
        for k in (0, 1):
            if (lab == k).any():
                m = n[lab == k].mean(0)
                cen[k] = m / max(np.linalg.norm(m), 1e-9)
    return F, lab


loop_start = np.zeros(nf, dtype=np.int32)
loop_total = np.zeros(nf, dtype=np.int32)
me.polygons.foreach_get('loop_start', loop_start)
me.polygons.foreach_get('loop_total', loop_total)
np.save(out / 'loop_start.npy', loop_start)
np.save(out / 'loop_total.npy', loop_total)


def uv_area(uv):
    ar = np.zeros(nf)
    for i in range(nf):
        q = uv[loop_start[i]:loop_start[i] + loop_total[i]]
        x, y = q[:, 0], q[:, 1]
        ar[i] = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
    return ar


def read_uv():
    q = np.zeros(nl * 2, dtype=np.float32)
    me.uv_layers['new'].data.foreach_get('uv', q)
    return q.reshape(-1, 2)


def select_faces(faces):
    bpy.ops.object.mode_set(mode='OBJECT')
    sel = np.zeros(nf, dtype=bool)
    sel[faces] = True
    me.polygons.foreach_set('select', sel)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.uv.select_all(action='SELECT')


# ---------------------------------------------------------------- 3. seams + unwrap into a new layer (split rounds)
new_uv = me.uv_layers.new(name='new')
me.uv_layers.active = new_uv
bpy.context.view_layer.objects.active = low
low.select_set(True)
stats['unwrap'] = a.unwrap
fa, fb = np.array([[e.link_faces[0].index, e.link_faces[-1].index] if e.link_faces else [0, 0] for e in bm.edges]).T
for rnd in range(a.split_rounds + 1):
    chart_faces = [np.nonzero(comp == c)[0] for c in range(n_charts)]
    cut_edges = set()
    for F in chart_faces:
        cut_edges |= cut_chart(list(F))
    seam = np.array([e.index in cut_edges for e in bm.edges]) | (comp[fa] != comp[fb])
    me.edges.foreach_set('use_seam', seam)
    select_faces(np.arange(nf))
    bpy.ops.uv.unwrap(method=a.unwrap, margin=0.0)
    bpy.ops.object.mode_set(mode='OBJECT')
    # a solver that collapsed a chart (MINIMUM_STRETCH does on some) -> redo that chart angle-based
    ar = uv_area(read_uv())
    chart_d = np.array([ar[F].sum() / max(face_area[F].sum(), 1e-12) for F in chart_faces])
    bad = [c for c in range(n_charts) if not chart_d[c] > 1e-3 * np.median(chart_d)]
    if bad:
        select_faces(np.concatenate([chart_faces[c] for c in bad]))
        bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=0.0)
        bpy.ops.object.mode_set(mode='OBJECT')
        ar = uv_area(read_uv())
    dens = ar / np.maximum(face_area, 1e-12)
    # distortion per chart: share of its area whose texel density is < 1/2 or > 2x the chart's own median
    worst = []
    for c, F in enumerate(chart_faces):
        d = dens[F] / max(np.median(dens[F]), 1e-12)
        off = face_area[F][(d < 0.5) | (d > 2.0)].sum() / face_area[F].sum()
        worst.append((float(off), c))
    worst.sort(reverse=True)
    print('ROUND', rnd, 'charts', n_charts, 'collapsed', len(bad),
          'worst', [(round(o, 2), len(chart_faces[c])) for o, c in worst[:6]], flush=True)
    if rnd == a.split_rounds:
        break
    split = 0
    for o, c in worst:
        if o < a.split_threshold or len(chart_faces[c]) < 2 * a.min_faces:
            continue
        F, lab = split_chart(chart_faces[c])
        if lab.min() == lab.max():
            continue
        comp[F[lab == 1]] = n_charts
        n_charts += 1
        split += 1
    if not split:
        break
    # splits can leave disconnected bits: relabel connected components, fold scraps into a neighbour chart
    label = comp.copy()
    while True:
        comp, n_charts = components(label)
        sizes = np.bincount(comp)
        moved = 0
        for c in np.argsort(sizes):
            if sizes[c] >= a.min_faces // 3:
                break
            faces = np.nonzero(comp == c)[0]
            border = Counter()
            for f in faces:
                for g, ei in face_nb[f]:
                    if comp[g] != c:
                        border[label[g]] += edge_len[ei]
            if border:
                label[faces] = border.most_common(1)[0][0]
                moved += 1
        if not moved:
            break

select_faces(np.arange(nf))
bpy.ops.uv.average_islands_scale()
bpy.ops.object.mode_set(mode='OBJECT')
# per-chart texel density: scale each chart about its UV centre by sqrt(area-weighted mean face weight);
# pack_islands then rescales everything uniformly, so the ratios survive
chart_faces = [np.nonzero(comp == c)[0] for c in range(n_charts)]
uv = read_uv()
chart_w = np.ones(n_charts)
head_share = []
for c, F in enumerate(chart_faces):
    chart_w[c] = float((face_w[F] * face_area[F]).sum() / face_area[F].sum())
    hs = float(face_area[F][face_region[F] == 'head'].sum() / face_area[F].sum())
    if hs > 0.02:
        head_share.append((round(hs, 2), len(F), round(chart_w[c], 2)))
    if abs(chart_w[c] - 1.0) < 1e-6:
        continue
    li = np.concatenate([np.arange(loop_start[f], loop_start[f] + loop_total[f]) for f in F])
    cen = uv[li].mean(0)
    uv[li] = cen + (uv[li] - cen) * np.sqrt(chart_w[c])
me.uv_layers['new'].data.foreach_set('uv', uv.astype(np.float32).ravel())
stats['head_charts_share_faces_weight'] = sorted(head_share, reverse=True)
select_faces(np.arange(nf))
if a.align_rotation:
    bpy.ops.uv.align_rotation(method='AUTO')
bpy.ops.uv.pack_islands(rotate=True, scale=True, margin_method='FRACTION', margin=a.margin, shape_method='CONCAVE')
bpy.ops.object.mode_set(mode='OBJECT')
new_uv = me.uv_layers['new']      # edit-mode round trips reallocate the layer: re-fetch
stats['charts'] = int(n_charts)
stats['cut_edges'] = len(cut_edges)
if cut_edges:
    ce = np.array(sorted(cut_edges))
    en = np.array([(vno[bm.edges[i].verts[0].index] + vno[bm.edges[i].verts[1].index])[0] for i in ce])
    stats['cut_len_back_share'] = round(float(edge_len[ce][en < 0].sum() / edge_len[ce].sum()), 3)
label = comp
uv_new = read_uv()
# pass checks (4-23): head vs torso density, low-density area (raw, and relative to the intended chart weight)
dens = uv_area(uv_new) / np.maximum(face_area, 1e-12)
dens /= np.median(dens)
intended = dens / chart_w[comp]
intended /= np.median(intended)
med = {r: float(np.median(dens[face_region == r])) for r in REGIONS if (face_region == r).any()}
stats['density_median_by_region'] = {r: round(v, 3) for r, v in med.items()}
stats['head_over_torso'] = round(med.get('head', 0) / max(med.get('torso', 1e-9), 1e-9), 3)
stats['area_share_dens_lt_0.35'] = round(float(face_area[dens < 0.35].sum() / face_area.sum()), 4)
stats['area_share_intended_lt_0.35'] = round(float(face_area[intended < 0.35].sum() / face_area.sum()), 4)
stats['intended_p5_p95'] = [round(float(np.percentile(intended, 5)), 3), round(float(np.percentile(intended, 95)), 3)]
np.save(out / 'uv_new.npy', uv_new)
np.save(out / 'uv_old.npy', uv_old)
np.save(out / 'face_island.npy', label)
for tag, uv in (('old', uv_old), ('new', uv_new)):
    ar = uv_area(uv)
    ratio = ar / np.maximum(face_area, 1e-12)
    ratio /= np.median(ratio)
    stats[f'{tag}_density_p5_p95'] = [round(float(np.percentile(ratio, 5)), 3), round(float(np.percentile(ratio, 95)), 3)]
    stats[f'{tag}_uv_coverage'] = round(float(ar.sum()), 4)
print('REUV', json.dumps(stats), f'{time.time() - t0:.0f}s', flush=True)
(out / 'reuv.json').write_text(json.dumps(stats, indent=1), encoding='utf-8')

if a.uv_only:
    sys.exit(0)

# ---------------------------------------------------------------- 4. bakes
sc.render.engine = 'CYCLES'
sc.cycles.device = 'CPU'
prefs = bpy.context.preferences.addons['cycles'].preferences
for backend in ('OPTIX', 'CUDA'):
    try:
        prefs.compute_device_type = backend
        prefs.get_devices()
    except Exception:
        continue
    if any(d.type != 'CPU' for d in prefs.devices):
        for d in prefs.devices:
            d.use = d.type != 'CPU'
        sc.cycles.device = 'GPU'
        break
bk = sc.render.bake
bk.margin = 16
bk.margin_type = 'EXTEND'
if low.data.has_custom_normals:
    bpy.ops.object.select_all(action='DESELECT')
    low.select_set(True)
    bpy.ops.mesh.customdata_custom_splitnormals_clear()
for poly in me.polygons:
    poly.use_smooth = True              # game shading, as bake_normal_onto.py
me.uv_layers.active = new_uv
me.materials.clear()
mat = bpy.data.materials.new('bake')
mat.use_nodes = True
nt = mat.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
uvnode = nt.nodes.new('ShaderNodeUVMap')
uvnode.uv_map = 'old'
src = nt.nodes.new('ShaderNodeTexImage')
src.interpolation = 'Linear'
em = nt.nodes.new('ShaderNodeEmission')
outn = nt.nodes.new('ShaderNodeOutputMaterial')
nt.links.new(uvnode.outputs['UV'], src.inputs['Vector'])
nt.links.new(src.outputs['Color'], em.inputs['Color'])
nt.links.new(em.outputs['Emission'], outn.inputs['Surface'])
target = nt.nodes.new('ShaderNodeTexImage')
nt.nodes.active = target
me.materials.append(mat)


def new_target(name):
    img = bpy.data.images.new(name, a.res, a.res, alpha=False, float_buffer=True)
    img.colorspace_settings.name = 'Non-Color'
    target.image = img
    nt.nodes.active = target
    return img


def to_px(img):
    return np.array(img.pixels[:], dtype=np.float32).reshape(a.res, a.res, 4)


def save_png(px, name, srgb=False):
    h, w = px.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=False)
    img.colorspace_settings.name = 'sRGB' if srgb else 'Non-Color'
    img.pixels = np.clip(px, 0, 1).ravel()
    img.filepath_raw = str(out / f'{name}.png')
    img.file_format = 'PNG'
    img.save()
    assert (out / f'{name}.png').is_file(), f'{name}.png not written'


bpy.ops.object.select_all(action='DESELECT')
low.select_set(True)
bpy.context.view_layer.objects.active = low
bk.use_selected_to_active = False
sc.cycles.samples = 4
maps = {}
for role in ('BaseColor', 'ORM'):
    s_img = bpy.data.images.load(str(Path(a.src_dir) / f'T_{a.name}_{role}.png'))
    s_img.colorspace_settings.name = 'Non-Color'     # raw values in, raw values out (no sRGB round trip)
    src.image = s_img
    img = new_target(f'bake_{role}')
    bpy.ops.object.bake(type='EMIT')
    maps[role] = to_px(img)
    print('TRANSFER', role, round(float(maps[role][..., :3].mean()), 4), f'{time.time() - t0:.0f}s', flush=True)

if a.high:
    bpy.ops.import_scene.gltf(filepath=a.high)
    highs = [o for o in sc.objects if o.type == 'MESH' and o is not low]
    # fit the high-poly onto the low by bounds (4 yaw turns, nearest error), as bake_normal_onto.py
    lp = np.array([low.matrix_world @ v.co for v in me.vertices])
    tree = kdtree.KDTree(len(lp))
    for i, x in enumerate(lp):
        tree.insert(x, i)
    tree.balance()
    hp = np.array([o.matrix_world @ v.co for o in highs for v in list(o.data.vertices)[::50]])
    llo, lhi = lp.min(0), lp.max(0)
    best = None
    for k in range(4):
        rz = np.array(Matrix.Rotation(k * np.pi / 2, 3, 'Z'))
        q = hp @ rz.T
        lo, hi = q.min(0), q.max(0)
        s = (lhi[2] - llo[2]) / max(hi[2] - lo[2], 1e-6)
        off = (llo + lhi) / 2 - s * (lo + hi) / 2
        off[2] = llo[2] - s * lo[2]
        err = float(np.mean([tree.find(x)[2] for x in (q * s + off)[::20]]))
        if best is None or err < best[0]:
            best = (err, k, s, off)
    err, k, s, off = best
    fit = Matrix.Translation(Vector(off)) @ Matrix.Scale(s, 4) @ Matrix.Rotation(k * np.pi / 2, 4, 'Z')
    for o in highs:
        o.matrix_world = fit @ o.matrix_world
    size = float(max(lhi - llo))
    stats['high_fit_mean_dist_pct'] = round(err / size * 100, 3)
    print(f'HIGH_FIT yaw={k * 90} scale={s:.4f} mean_dist={err / size * 100:.3f}%', flush=True)
    for o in highs:
        o.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    bk.use_selected_to_active = True
    bk.use_cage = False
    bk.cage_extrusion = size * 0.008
    bk.max_ray_distance = size * 0.025

    sc.cycles.samples = 16
    img = new_target('bake_nrm')
    bpy.ops.object.bake(type='NORMAL', normal_space='TANGENT')
    n = to_px(img)[..., :3].copy()
    tilt = np.clip((n[..., 2] - 0.35) / 0.2, 0.0, 1.0)[..., None]          # missed rays on thin parts -> flat
    n = n * tilt + np.array([0.5, 0.5, 1.0], dtype=np.float32) * (1.0 - tilt)
    n[..., 1] = 1.0 - n[..., 1]                                            # OpenGL -> DirectX
    maps['Normal'] = np.concatenate([n, np.ones_like(n[..., :1])], -1)
    stats['normal_std'] = round(float(n[..., :2].std()), 4)
    print('NORMAL', stats['normal_std'], f'{time.time() - t0:.0f}s', flush=True)

    # AO on the high-poly surface; the low must not occlude it (it sits inside / on the high shell)
    for attr in ('visible_diffuse', 'visible_glossy', 'visible_transmission', 'visible_volume_scatter', 'visible_shadow'):
        setattr(low, attr, False)
    if sc.world is None:
        sc.world = bpy.data.worlds.new('w')
    sc.world.light_settings.distance = size * 0.06
    sc.cycles.samples = 64
    img = new_target('bake_ao')
    bpy.ops.object.bake(type='AO')
    ao = to_px(img)[..., 0]
    stats['ao_mean'] = round(float(ao.mean()), 4)
    stats['ao_p5'] = round(float(np.percentile(ao, 5)), 4)
    maps['ORM'][..., 0] = 0.4 + 0.6 * ao
    print('AO', stats['ao_mean'], stats['ao_p5'], f'{time.time() - t0:.0f}s', flush=True)

save_png(maps['BaseColor'], f'T_{a.name}_BaseColor', srgb=False)   # raw values (the sRGB source was read raw)
save_png(maps['ORM'], f'T_{a.name}_ORM')
if 'Normal' in maps:
    save_png(maps['Normal'], f'T_{a.name}_Normal')
(out / 'reuv.json').write_text(json.dumps(stats, indent=1), encoding='utf-8')
print('REUV_DONE', json.dumps(stats), f'{time.time() - t0:.0f}s', flush=True)
