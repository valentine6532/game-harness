"""Cape texture from the flat concept (design/deathknight/v3/dk3_cape_flat.png, outer side = left half):
cloth below the metal mantle, mantle texels inpainted with cloth, background -> alpha 0 (torn hem / holes).
-> T_HeroCape_BaseColor.png (RGBA). The black lining is done in the material (back faces)."""
import numpy as np, cv2
img = cv2.imread('../../../design/deathknight/v3/dk3_cape_flat.png', cv2.IMREAD_COLOR_RGB)
w = img.shape[1]
crop = img[200:992, 110:752].copy()                      # red bbox 57-983 x 125-734 (mantle above ~250)
f = crop.astype(np.float32) / 255
mx, mn = f.max(-1), f.min(-1)
sat = (mx - mn) / np.maximum(mx, 1e-4)
bg = np.abs(f - 208 / 255).max(-1) < 0.07
red = (sat > 0.3) & (f[..., 0] > f[..., 1] * 1.25)
metal = ~bg & ~red
top = np.zeros_like(bg); top[:140] = True                # mantle only reaches ~140 px into the crop
fill = metal & top
# the cloth continues under the mantle: grow a top band of the cloth outline, inpaint the metal texels
rgb = cv2.inpaint(crop, fill.astype(np.uint8) * 255, 9, cv2.INPAINT_TELEA)
alpha = (~bg).astype(np.uint8) * 255
alpha[fill] = 255
# columns that carry cloth anywhere in the top band get a full top edge (no gap under the removed mantle)
cols = red[:260].any(0)
alpha[:60, cols] = 255
rgb[:60, cols] = cv2.inpaint(rgb, ((alpha == 255) & (np.arange(alpha.shape[0])[:, None] < 60) & ~red).astype(np.uint8) * 255, 9, cv2.INPAINT_TELEA)[:60, cols]
# leftover grey mantle bits in the top corners (not cloth-coloured after the inpaint) -> transparent
g = rgb.astype(np.float32) / 255
gs = (g.max(-1) - g.min(-1)) / np.maximum(g.max(-1), 1e-4)
alpha[:150][(gs[:150] < 0.3) | (g[:150, :, 0] < g[:150, :, 1] * 1.2)] = 0
alpha = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
out = cv2.resize(np.dstack([rgb, alpha]), (1024, 1280), interpolation=cv2.INTER_AREA)
cv2.imwrite('T_HeroCape_BaseColor.png', cv2.cvtColor(out, cv2.COLOR_RGBA2BGRA))
prev = out[..., :3].astype(np.float32) * (out[..., 3:] / 255) + 60 * (1 - out[..., 3:] / 255)
cv2.imwrite('tex_preview.png', cv2.cvtColor(prev.astype(np.uint8), cv2.COLOR_RGB2BGR))
print('CAPE_TEX', out.shape, f'opaque {(out[..., 3] > 127).mean() * 100:.1f}%')
