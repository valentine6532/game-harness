"""Draw a UV layout from reuv_bake.py outputs (system Python): python draw_uv_layout.py <reuv dir> <out.png> [uv_new|uv_old] [texture.png]"""
import sys
import cv2
import numpy as np

d, outp = sys.argv[1], sys.argv[2]
key = sys.argv[3] if len(sys.argv) > 3 else 'uv_new'
N = 2048
uv = np.load(f'{d}/{key}.npy')
ls, lt = np.load(f'{d}/loop_start.npy'), np.load(f'{d}/loop_total.npy')
lab = np.load(f'{d}/face_island.npy') if key == 'uv_new' else None
if len(sys.argv) > 4:
    img = (cv2.resize(cv2.imread(sys.argv[4]), (N, N), interpolation=cv2.INTER_AREA) * 0.6).astype(np.uint8)
else:
    img = np.full((N, N, 3), 28, np.uint8)
rng = np.random.default_rng(1)
colours = rng.integers(60, 255, (int(lab.max()) + 1 if lab is not None else 1, 3))
for f in range(len(ls)):
    q = uv[ls[f]:ls[f] + lt[f]]
    pts = np.round(np.stack([q[:, 0] * N, (1 - q[:, 1]) * N], -1)).astype(np.int32)
    if lab is not None and len(sys.argv) <= 4:
        cv2.fillPoly(img, [pts], [int(c) for c in colours[lab[f]]])
    cv2.polylines(img, [pts], True, (20, 20, 20) if len(sys.argv) <= 4 else (90, 255, 255), 1)
cv2.imwrite(outp, img)
