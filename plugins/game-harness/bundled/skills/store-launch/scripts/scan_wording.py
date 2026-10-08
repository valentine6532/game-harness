#!/usr/bin/env python3
"""Find wording that gets apps rejected or confuses users on the other platform.

Usage: python scan_wording.py <file-or-folder> [more paths...] [--kids-ok] [--ext .cs,.json,.uxml,.md,.html]

Reports three groups:
  1. Other-store or other-platform names (Google Play, App Store, Android, iPhone ...).
     These are fine only where the code picks the text per platform; check each hit.
  2. "For kids" style wording, which Apple reserves for Kids Category apps.
     Skipped with --kids-ok.
  3. Leftover placeholders such as the template markers 【 】.

It prints the file, line number and line so each hit can be judged in context.
Exit code is 0 either way; this is a list to review, not a pass/fail check.
"""
import os
import sys

# Windows consoles default to a legacy code page; force UTF-8 so Korean text and status marks print.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

STORES = ['Google Play', '구글 플레이', '구글플레이', 'Play Store', 'Play 스토어', '플레이 스토어', '플레이스토어',
          'App Store', '앱 스토어', '앱스토어', 'Android', '안드로이드', 'iPhone', '아이폰', 'iOS', 'Galaxy', '갤럭시',
          'グーグル', 'アンドロイド', 'TestFlight']
KIDS = ['어린이용', '키즈', '유아용', '아동용', 'For Kids', 'for kids', 'For Children', 'for children', '子ども向け', 'キッズ']
PLACEHOLDERS = ['【', 'TODO', 'lorem ipsum']
DEFAULT_EXT = ('.cs', '.json', '.uxml', '.md', '.html', '.txt', '.xml', '.strings', '.js', '.ts')
SKIP_DIRS = {'.git', 'Library', 'Temp', 'node_modules', 'obj', 'Logs', 'PackageCache', 'build', 'Builds'}


def files(paths, extensions):
    for path in paths:
        if os.path.isfile(path):
            yield path
            continue
        for root, dirs, names in os.walk(path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in names:
                if name.lower().endswith(extensions):
                    yield os.path.join(root, name)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print(__doc__)
        return 2
    extensions = DEFAULT_EXT
    if '--ext' in sys.argv:
        extensions = tuple(e.strip() for e in sys.argv[sys.argv.index('--ext') + 1].split(','))
        args = [a for a in args if a != sys.argv[sys.argv.index('--ext') + 1]]
    groups = [('Other store or platform names', STORES), ('Placeholders left in text', PLACEHOLDERS)]
    if '--kids-ok' not in sys.argv:
        groups.insert(1, ('"For kids" wording (reserved for Kids Category apps on the App Store)', KIDS))
    hits = {label: [] for label, _ in groups}
    for path in files(args, extensions):
        try:
            with open(path, encoding='utf-8', errors='replace') as stream:
                for number, line in enumerate(stream, 1):
                    for label, words in groups:
                        found = [w for w in words if w in line]
                        if found:
                            hits[label].append((path, number, ', '.join(found), line.strip()[:160]))
        except OSError as error:
            print(f'skip {path}: {error}')
    for label, _ in groups:
        print(f'\n== {label}: {len(hits[label])} line(s)')
        for path, number, words, line in hits[label][:200]:
            print(f'{path}:{number} [{words}] {line}')
        if len(hits[label]) > 200:
            print(f'... {len(hits[label]) - 200} more')
    print('\nJudge each hit: text chosen per platform in code is fine; text every user sees is not.')
    print('Text can also be baked into images, which this scan cannot see.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
