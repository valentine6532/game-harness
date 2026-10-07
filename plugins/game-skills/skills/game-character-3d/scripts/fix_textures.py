"""Texture pass for Tripo characters / props (4-20): Tripo bakes lighting into BaseColor and gives metal one smooth,
blobby roughness (~0.59) -> plates read as wet plastic, trim as yellow wax, straps pick up metal from the blurred
metallic map. Per texel class (same colour rules as process_character.texel_class):

- metal (Tripo metallic > 0.3) split into steel / gold (warm, saturated, bright) and cleaned: red cloth or dark brown
  leather texels inside the blurred metal blob become non-metal.
- steel / gold BaseColor: the large-scale painted light (masked local mean) is replaced by a flat metal F0, the fine
  detail (ratio to that mean) is kept but clamped -> no painted highlight blobs, scratches / grime stay.
- steel / gold roughness: from that same detail (bright scratches smoother, grime rougher) instead of one smooth blob.
- leather / cloth: only painted highlights (texel > 1.25x its masked local mean) are compressed; darks are kept
  (ORM.R is 1, painted shadows are the only crevice darkening).
- with --charts (reuv_bake.py dir) and T_<Name>_Classes.png (process_character part map), per UV chart (4-22):
  cloth loses 70 % and leather 40 % of its large-scale painted shading (masked mean inside the chart, sigma 48 px
  at 4K), small dark smears / specks (< 0.6x the local mean) are lifted. Folds and crevices now come from the baked
  AO + normal map. Fur / tail (stripes, white paws) are never touched.
- fur / everything else: untouched.

Usage: python fix_textures.py <dir> <Name> [--preview class.png] [--no-gold] [--charts reuv_dir]
  T_<Name>_BaseColor.png / T_<Name>_ORM.png, originals kept in <dir>/_texfix_src.
  --no-gold: the P1 weapon atlas paints wood / grips metallic too; every warm brown there is wood or leather.
"""
import argparse, hashlib, shutil
from pathlib import Path
import cv2
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument('dir')
ap.add_argument('name')
ap.add_argument('--preview')
ap.add_argument('--no-gold', action='store_true')
ap.add_argument('--charts', help='reuv_bake.py output dir: UV charts for per-part delighting (needs T_<Name>_Classes.png)')
ap.add_argument('--cloth-delight', type=float, default=0.7)
ap.add_argument('--steel-f0', default='0.18', help="flat steel F0 (linear), or 'keep' = the steel's own median brightness "
                "(blackened iron of the deathknight: painted light is still removed, the dark plate stays dark)")
ap.add_argument('--gold-f0', default='0.32', help="flat gold F0 (linear), or 'keep' = its own median brightness (deathknight bone rims)")
ap.add_argument('--steel-chroma', type=float, default=0.35, help='how much of the texel hue steel keeps (bone / bronze rims: 1)')
ap.add_argument('--leather-delight', type=float, default=0.4)
args = ap.parse_args()
d, name = Path(args.dir), args.name
preview = Path(args.preview) if args.preview else None
src = d / '_texfix_src'
src.mkdir(exist_ok=True)
for role in ('BaseColor', 'ORM'):
    f = d / f'T_{name}_{role}.png'
    stamp = src / f'{f.name}.out.sha1'
    # the file is an original unless it is exactly what this script wrote last time (process_character re-run -> new original)
    if not (src / f.name).exists() or not stamp.exists() or stamp.read_text() != hashlib.sha1(f.read_bytes()).hexdigest():
        shutil.copy2(f, src / f.name)       # keep Tripo's original; runs always start from it


def load(role):
    return cv2.imread(str(src / f'T_{name}_{role}.png'), cv2.IMREAD_COLOR_RGB).astype(np.float32) / 255


base = load('BaseColor')
H, W = base.shape[:2]
orm = cv2.resize(load('ORM'), (W, H), interpolation=cv2.INTER_LINEAR)   # Tripo ORM is 2K: work (and save) at colour res
rough, metal = orm[..., 1], orm[..., 2]

r, g, b = base[..., 0], base[..., 1], base[..., 2]
mx, mn = base.max(-1), base.min(-1)
dlt = np.maximum(mx - mn, 1e-4)
sat = np.where(mx > 1e-4, (mx - mn) / np.maximum(mx, 1e-4), 0)
hue = np.where(mx == r, ((g - b) / dlt) % 6, np.where(mx == g, (b - r) / dlt + 2, (r - g) / dlt + 4)) / 6

red_cloth = ((hue < 0.035) | (hue > 0.95)) & (sat > 0.38) & (mx > 0.18)
leather = (hue >= 0.02) & (hue < 0.14) & (sat > 0.38) & (mx > 0.08) & (mx < 0.42)
if args.no_gold:
    leather = (hue >= 0.02) & (hue < 0.16) & (sat > 0.2) & (mx > 0.05)
# Tripo's 2K metallic map is a soft blob that runs over the black gaps, dark cloth and white fur next to a plate:
# painted steel is 0.25-0.6 sRGB, so near-black texels and bright neutral fur outside the metal core leave it
metal_m = (metal > 0.3) & ~red_cloth & ~leather & (mx > 0.18) & ~((mx > 0.75) & (sat < 0.15) & (metal < 0.7))
gold = metal_m & (not args.no_gold) & (hue >= 0.04) & (hue < 0.15) & (sat >= 0.25) & (sat < 0.8) & (mx > 0.42)
steel = metal_m & ~gold
leather &= ~metal_m
red_cloth &= ~metal_m

lin = np.power(base, 2.2)
lum = lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)


def masked_mean(x, m, sigma):
    """Gaussian mean of x over texels of mask m only (UV islands of other classes do not bleed in)."""
    mf = m.astype(np.float32)
    num = cv2.GaussianBlur(x * mf, (0, 0), sigma)
    den = cv2.GaussianBlur(mf, (0, 0), sigma)
    return num / np.maximum(den, 1e-4)


s = W / 4096
out = lin.copy()
new_rough = rough.copy()
new_metal = np.zeros_like(metal)
stats = {}
steel_f0 = float(np.median(lum[steel])) if args.steel_f0 == 'keep' and steel.any() else float(args.steel_f0 if args.steel_f0 != 'keep' else 0.18)
gold_f0 = float(np.median(lum[gold])) if args.gold_f0 == 'keep' and gold.any() else float(args.gold_f0 if args.gold_f0 != 'keep' else 0.32)
for cls, m, f0, keep_chroma, r0, r_lo, r_hi in (('steel', steel, steel_f0, args.steel_chroma, 0.55, 0.35, 0.82),
                                                 ('gold', gold, gold_f0, 1.0, 0.45, 0.32, 0.65)):
    if not m.any():
        continue
    mean = masked_mean(lum, m, 24 * s)
    detail = np.clip(lum / np.maximum(mean, 1e-4), 0.35, 1.6)
    chroma = lin / np.maximum(lum, 1e-4)[..., None]                     # hue at unit luminance
    chroma = 1 + (np.clip(chroma, 0, 3) - 1) * keep_chroma               # steel: mostly neutral grey
    # flat F0 scaled by 60 % of the island's own brightness (a dark plate stays darker than a light one)
    level = f0 * np.power(np.maximum(mean, 1e-4) / np.median(mean[m]), 0.6)
    col = chroma * (level * detail)[..., None]
    out[m] = col[m]
    rr = r0 - 0.45 * (detail - 1) + 0.3 * (rough - np.median(rough[m]))  # bright scratch smoother, grime rougher
    new_rough[m] = np.clip(rr, r_lo, r_hi)[m]
    new_metal[m] = 1.0
    lum_new = out[m] @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    stats[cls] = (round(float(m.mean()), 4), 'lum', round(float(np.median(lum[m])), 3), '->', round(float(np.median(lum_new)), 3),
                  'rough', round(float(np.median(rough[m])), 2), '->', round(float(np.median(new_rough[m])), 2))

cls_path = d / f'T_{name}_Classes.png'
if args.charts and cls_path.exists():
    cls = cv2.resize(cv2.imread(str(cls_path), cv2.IMREAD_COLOR_RGB), (W, H), interpolation=cv2.INTER_NEAREST) > 127
    part_cloth, part_leather = cls[..., 2] & ~metal_m, cls[..., 1] & ~metal_m
    cd = Path(args.charts)
    uvn, lst, ltt = np.load(cd / 'uv_new.npy'), np.load(cd / 'loop_start.npy'), np.load(cd / 'loop_total.npy')
    flab = np.load(cd / 'face_island.npy')
    ids = np.full((H, W), -1, np.int32)
    for f in range(len(lst)):
        q = uvn[lst[f]:lst[f] + ltt[f]]
        cv2.fillPoly(ids, [np.round(np.stack([q[:, 0] * W - 0.5, (1 - q[:, 1]) * H - 0.5], -1)).astype(np.int32)], int(flab[f]))
    gain = np.ones((H, W), np.float32)
    for tag, pm, k in (('cloth', part_cloth, args.cloth_delight), ('leather', part_leather, args.leather_delight)):
        done = 0
        for c in range(int(flab.max()) + 1):
            m = pm & (ids == c)
            if m.sum() < 400:
                continue
            ys, xs = np.nonzero(m)
            y0, y1, x0, x1 = max(ys.min() - 150, 0), min(ys.max() + 150, H), max(xs.min() - 150, 0), min(xs.max() + 150, W)
            mc, lc = m[y0:y1, x0:x1], lum[y0:y1, x0:x1]
            low = masked_mean(lc, mc, 48 * s)                     # painted light / shadow across the part
            target = np.median(lc[mc])
            g_low = np.power(target / np.maximum(low, 1e-5), k)
            near = masked_mean(lc, mc, 4 * s)                     # smear / speck: much darker than its surroundings
            ratio = lc / np.maximum(near, 1e-5)
            g_speck = np.where(ratio < 0.6, np.power(0.6 / np.maximum(ratio, 1e-3), 0.8), 1.0)
            gc = np.clip(g_low * g_speck, 0.4, 2.5)
            # face-level part labels leave stair-step borders inside a chart: fade the correction out over ~8 px
            # (only inside this chart) so no square patches appear where the label changes
            cm = ids[y0:y1, x0:x1] == c
            w = np.clip(cv2.GaussianBlur(mc.astype(np.float32), (0, 0), 8 * s) * 2 - 0.5, 0, 1) * mc
            gsub = gain[y0:y1, x0:x1]
            gsub[cm] = (gsub * (1 - w) + gc * w)[cm]
            done += 1
        stats[f'{tag}_delight'] = (done, round(float(pm.mean()), 4))
    out *= gain[..., None]
    lum = out @ np.array([0.2126, 0.7152, 0.0722], np.float32)   # the highlight cap below works on the delit texture

soft = leather | red_cloth
if soft.any():
    mean = masked_mean(lum, soft, 40 * s)
    ratio = lum / np.maximum(mean, 1e-4)
    capped = np.where(ratio > 1.25, 1.25 + (ratio - 1.25) * 0.4, ratio)
    k = np.where(soft, capped / np.maximum(ratio, 1e-4), 1.0)
    out *= k[..., None]
    stats['soft_highlights'] = round(float((soft & (ratio > 1.25)).sum() / max(soft.sum(), 1)), 3)
# the old ORM floor from process_character (leather 0.65, cloth 0.9, fur 0.85) stays for non-metal; leather that
# came out of the metal blob gets the leather floor
freed = (metal > 0.3) & ~metal_m
new_rough[freed] = np.maximum(new_rough[freed], np.where(red_cloth[freed], 0.9, 0.65))
stats['freed_from_metal'] = round(float(freed.mean()), 4)

res = np.clip(np.power(np.clip(out, 0, 1), 1 / 2.2), 0, 1)
cv2.imwrite(str(d / f'T_{name}_BaseColor.png'), cv2.cvtColor((res * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGB2BGR))
orm_out = np.stack([orm[..., 0], new_rough, new_metal], -1)
cv2.imwrite(str(d / f'T_{name}_ORM.png'), cv2.cvtColor((np.clip(orm_out, 0, 1) * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGB2BGR))
for role in ('BaseColor', 'ORM'):
    f = d / f'T_{name}_{role}.png'
    (src / f'{f.name}.out.sha1').write_text(hashlib.sha1(f.read_bytes()).hexdigest())
print('TEXFIX', name, stats, flush=True)

if preview:
    vis = base * 0.3
    for m, c in ((steel, (0.3, 0.5, 1)), (gold, (1, 0.85, 0)), (leather, (0.45, 0.22, 0.05)), (red_cloth, (0.8, 0, 0)), (freed, (0, 1, 0))):
        vis[m] = c
    cv2.imwrite(str(preview), cv2.cvtColor((cv2.resize(vis, (1024, 1024)) * 255).astype(np.uint8), cv2.COLOR_RGB2BGR))
