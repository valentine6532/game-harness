#!/usr/bin/env python3
"""Summarise a launch checklist: counts per status and what is still open.

Usage: python checklist_status.py <launch-checklist.md> [--open] [--owner 본인|코드]

Rows are Markdown table rows whose first cell is a status mark:
  ✅ done, ⬜ to do, ❓ needs checking in a console, ➖ not applicable.
--open lists the ⬜ and ❓ rows grouped by section heading.
--owner keeps only rows whose owner cell matches.
"""
import sys

# Windows consoles default to a legacy code page; force UTF-8 so Korean text and status marks print.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, ValueError):
        pass

MARKS = {'✅': 'done', '⬜': 'to do', '❓': 'needs checking', '➖': 'not applicable'}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        print(__doc__)
        return 2
    owner = sys.argv[sys.argv.index('--owner') + 1] if '--owner' in sys.argv else None
    if owner in args:
        args.remove(owner)
    counts = {mark: 0 for mark in MARKS}
    open_rows = []
    section = ''
    with open(args[0], encoding='utf-8') as stream:
        for line in stream:
            if line.startswith('#'):
                section = line.strip('# \n')
                continue
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if not line.startswith('|') or not cells or cells[0] not in MARKS or len(cells) < 3:
                continue  # legend rows have two cells; task rows have three or more
            if owner and owner not in cells[2:3]:
                continue
            counts[cells[0]] += 1
            if cells[0] in ('⬜', '❓'):
                open_rows.append((section, cells[0], cells[1], cells[2] if len(cells) > 3 else ''))
    total = sum(counts.values())
    print(f'{total} items: ' + ', '.join(f'{mark} {MARKS[mark]} {count}' for mark, count in counts.items()))
    if '--open' in sys.argv:
        current = None
        for section_name, mark, task, who in open_rows:
            if section_name != current:
                current = section_name
                print(f'\n[{current}]')
            print(f'  {mark} {task}' + (f' ({who})' if who else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
