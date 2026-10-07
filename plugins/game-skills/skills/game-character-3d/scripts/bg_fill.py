"""Set the background of a concept image to exact #d0d0d0: pixels close to the border background color that are
connected to the image border.  python bg_fill.py <in> <out> [tol]"""
import sys, numpy as np, cv2
src, dst = sys.argv[1], sys.argv[2]; tol = float(sys.argv[3]) if len(sys.argv) > 3 else 16
im = cv2.imread(src, cv2.IMREAD_COLOR).astype(np.float32)
h, w = im.shape[:2]
border = np.concatenate([im[:4].reshape(-1, 3), im[-4:].reshape(-1, 3), im[:, :4].reshape(-1, 3), im[:, -4:].reshape(-1, 3)])
bg = np.median(border, axis=0)
# the background may carry a soft gradient: compare with a heavily blurred version of the image where it is background-like
near = np.linalg.norm(im - bg, axis=2) < tol * 2.2
sat = im.max(2) - im.min(2)
cand = (near & (sat < 14)).astype(np.uint8)
n, lab = cv2.connectedComponents(cand, connectivity=4)
edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
mask = np.isin(lab, list(edge))
# soften the seam: 1px feather band blends toward #d0d0d0
out = im.copy(); out[mask] = 208
band = cv2.dilate(mask.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool) & ~mask
out[band] = out[band] * 0.6 + 208 * 0.4
cv2.imwrite(dst, np.clip(out, 0, 255).astype(np.uint8))
print(f'{src}: border bg {bg.round(1)}, filled {mask.mean()*100:.1f}%')
