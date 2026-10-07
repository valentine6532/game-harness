#!/usr/bin/env python3
"""Check store screenshots against the size the console asks for, and fix them.

Usage:
  python fit_screenshot.py --check <file-or-folder> --size 1179x2556
  python fit_screenshot.py --convert <file-or-folder> --size 1179x2556 [--out <folder>] [--background f7f3e5]

--size is the pixel size printed under the upload box in the store console.
Read it from the console first; accepted sizes change, and a size that worked
last year may be rejected now.

--check reports each image's size, whether it has an alpha channel (App Store
Connect rejects transparency) and whether the aspect ratio matches.
--convert flattens transparency onto the background colour and resizes to the
exact size. It refuses when the aspect ratio differs by more than 1 percent,
because stretching a real screen is worse than re-capturing it. Without --out
the files are replaced in place.

Requires Pillow.
"""
import os
import sys

# Windows consoles default to a legacy code page; force UTF-8 so Korean text and status marks print.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

try:
    from PIL import Image
except ImportError:
    print('Pillow is required: pip install pillow')
    sys.exit(2)


def images(path):
    if os.path.isfile(path):
        return [path]
    return sorted(os.path.join(path, n) for n in os.listdir(path) if n.lower().endswith(('.png', '.jpg', '.jpeg')))


def option(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    mode = '--convert' if '--convert' in sys.argv else '--check' if '--check' in sys.argv else None
    size = option('--size')
    if not mode or not size:
        print(__doc__)
        return 2
    width, height = (int(v) for v in size.lower().split('x'))
    target = option(mode)
    out = option('--out')
    background = tuple(int(option('--background', 'ffffff')[i:i + 2], 16) for i in (0, 2, 4))
    problems = 0
    for path in images(target):
        with Image.open(path) as image:
            has_alpha = image.mode in ('RGBA', 'LA', 'P') and ('A' in image.mode or 'transparency' in image.info)
            ratio_gap = abs(image.width / image.height - width / height) / (width / height)
            size_ok = image.size == (width, height)
            status = 'OK' if size_ok and not has_alpha else 'FIX'
            print(f'{status}  {os.path.basename(path)}: {image.width}x{image.height} {image.mode}'
                  + ('' if size_ok else f' (want {width}x{height}, aspect differs {ratio_gap:.2%})')
                  + (' has transparency' if has_alpha else ''))
            if mode == '--check':
                problems += status != 'OK'
                continue
            if size_ok and not has_alpha:
                continue
            if ratio_gap > 0.01:
                print('  not converted: aspect ratio differs by more than 1%. Re-capture at the right size instead.')
                problems += 1
                continue
            flat = Image.new('RGB', image.size, background)
            rgba = image.convert('RGBA')
            flat.paste(rgba, mask=rgba.split()[3])
            result = flat if size_ok else flat.resize((width, height), Image.LANCZOS)
        destination = os.path.join(out, os.path.basename(path)) if out else path
        if out:
            os.makedirs(out, exist_ok=True)
        if not destination.lower().endswith('.png'):
            destination = os.path.splitext(destination)[0] + '.png'
        result.save(destination, optimize=True)
        print(f'  wrote {destination} as {width}x{height} RGB')
    if mode == '--check':
        print(f'\n{problems} file(s) need fixing.' if problems else '\nAll files match.')
    print('Opening the images and looking at them is still required; this only checks size and transparency.')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
