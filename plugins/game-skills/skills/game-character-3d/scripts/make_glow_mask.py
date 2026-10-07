"""Glow mask for Unreal's M_Char Emissive input: saturated blue texels of T_<Name>_BaseColor (runes, gems) -> white.
python make_glow_mask.py <dir> <Name> [--preview png]   -> <dir>/T_<Name>_Emissive.png (deathknight rune sword, step 5)"""
import sys, argparse
from pathlib import Path
import numpy as np, cv2
ap = argparse.ArgumentParser(); ap.add_argument('dir'); ap.add_argument('name'); ap.add_argument('--preview')
a = ap.parse_args()
d = Path(a.dir)
src = d / '_texfix_src' / f'T_{a.name}_BaseColor.png'          # colour before fix_textures, if it ran
img = cv2.imread(str(src if src.exists() else d / f'T_{a.name}_BaseColor.png'), cv2.IMREAD_COLOR_RGB).astype(np.float32) / 255
hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)                      # float input: H 0-360, S 0-1, V 0-1
h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
r, g, b = img[..., 0], img[..., 1], img[..., 2]
gem = (h > 180) & (h < 235) & (s > 0.3) & (v > 0.35)
rune = (v > 0.5) & ((b - r) > 0.07) & (s > 0.08)          # pale frost-blue lines (0.77, 0.82, 0.87)
m = (gem | rune).astype(np.float32)
m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))   # drop single-texel noise
m = np.clip(cv2.GaussianBlur(m, (0, 0), 1.2) * 1.4, 0, 1) * np.clip((v - 0.3) / 0.4, 0.4, 1)   # soft edge, brighter core
cv2.imwrite(str(d / f'T_{a.name}_Emissive.png'), (m * 255).astype(np.uint8))
print('GLOW_MASK', a.name, f'{(m > 0.5).mean() * 100:.2f}% of texels')
if a.preview:
    p = img.copy(); p[m > 0.5] = (1, 0, 1)
    cv2.imwrite(a.preview, cv2.cvtColor((p * 255).astype(np.uint8), cv2.COLOR_RGB2BGR))
