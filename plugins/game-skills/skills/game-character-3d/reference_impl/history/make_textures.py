"""Turn the generated environment images into engine textures.

python make_textures.py <concepts dir> <out dir>
- tileable maps (stone, paving, roof): crop border artefacts, remove seams with a half-offset
  feathered blend, 1024 px
- every map gets a DirectX normal map derived from luminance (grout/gaps read as grooves)
- plaza medallion is a unique (non-tiling) map, 2048 px
- banner: flat grey background keyed out -> RGBA
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

src, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)


def seamless(img, size):
    a = np.asarray(img.resize((size, size), Image.LANCZOS), dtype=np.float32)
    b = np.roll(np.roll(a, size // 2, 0), size // 2, 1)
    t = np.linspace(-1, 1, size)
    # weight of the original: 1 in the middle, 0 at the borders (where b has no seam)
    w1 = np.clip((1 - np.abs(t)) * 3.0, 0, 1)
    w = np.minimum.outer(w1, w1)[..., None]
    return Image.fromarray(np.clip(a * w + b * (1 - w), 0, 255).astype(np.uint8))


def normal_from(img, strength, blur=1.2):
    g = np.asarray(img.convert('L').filter(ImageFilter.GaussianBlur(blur)), dtype=np.float32) / 255.0
    dx = (np.roll(g, -1, 1) - np.roll(g, 1, 1)) * strength
    dy = (np.roll(g, -1, 0) - np.roll(g, 1, 0)) * strength
    n = np.dstack((-dx, dy, np.ones_like(g)))          # DirectX (green down)
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return Image.fromarray(((n * 0.5 + 0.5) * 255).astype(np.uint8))


def save(name, color, strength):
    color.save(out / f'T_{name}_BaseColor.png')
    normal_from(color, strength).save(out / f'T_{name}_Normal.png')
    print('saved', name, color.size)


for name, file, crop in (('Stone', 'tex_stone.png', 0.02), ('Paving', 'tex_paving.png', 0.02), ('Roof', 'tex_roof.png', 0.06)):
    im = Image.open(src / file).convert('RGB')
    w, h = im.size
    c = int(w * crop)
    save(name, seamless(im.crop((c, c, w - c, h - c)), 1024), 6.0)

plaza = Image.open(src / 'tex_plaza.png').convert('RGB').resize((2048, 2048), Image.LANCZOS)
save('Plaza', plaza, 5.0)

banner = Image.open(src / 'prop_banner.png').convert('RGB')
arr = np.asarray(banner, dtype=np.float32)
bg = np.median(np.concatenate([arr[:8].reshape(-1, 3), arr[-8:].reshape(-1, 3)]), axis=0)
dist = np.linalg.norm(arr - bg, axis=2)
alpha = np.clip((dist - 10) / 18, 0, 1) * 255
rgba = Image.fromarray(np.dstack((arr, alpha)).astype(np.uint8), 'RGBA')
bbox = rgba.getchannel('A').point(lambda v: 255 if v > 128 else 0).getbbox()
rgba = rgba.crop(bbox)
rgba.save(out / 'T_Banner_BaseColor.png')
print('banner bbox', bbox, rgba.size)
