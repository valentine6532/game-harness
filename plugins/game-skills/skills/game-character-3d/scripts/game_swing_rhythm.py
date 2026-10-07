"""Game-side swing rhythm from NYABLO_TIP log lines (fixed step, e.g. -UseFixedTimeStep -FPS=30 -NyabloTipLog).

usage: python game_swing_rhythm.py --clip onehand --win 16:26:33:40 --win 45:56:62:68 --win 75:86:91:98 \
           <log.txt> [<log.txt> ...] [--json out.json]

Each --win is s:k:h:e in source frames (07_animation.md). One log line = one rendered frame. Per swing:
  windup  rendered frames before k            strike  frames k -> h
  total   frames of the swing until the next swing / end
  lag     tip speed peak minus hand speed peak (rendered frames, k-2 .. h+4)
  ratio   tip speed / hand speed at their peaks  -> whip vs stick; independent of playback rate
  contrast tip speed peak / mean tip speed in the windup -> how much the cut "snaps" out of the load
Rendered lag shrinks as playback speeds up (sampling); judge stiffness by ratio, not lag.
Log line format (NyabloCharacter.cpp): NYABLO_TIP anim=.. frame=.. rate=.. speed=<tip cm/frame> hand=<grip cm/frame> hit= hold=
"""
import re, json, argparse, statistics as st

ap = argparse.ArgumentParser()
ap.add_argument('logs', nargs='+')
ap.add_argument('--clip', required=True, help='substring of the attack anim name')
ap.add_argument('--win', action='append', required=True, help='s:k:h:e')
ap.add_argument('--json')
a = ap.parse_args()
WIN = [tuple(float(x) for x in w.split(':')) for w in a.win]
pat = re.compile(r'NYABLO_TIP anim=(\S+) frame=([\d.]+) rate=([\d.]+) speed=([\d.]+) hand=([\d.]+) hit=(\d) hold=(\d)')


def swings(path):
    rows = [m.groups() for m in map(pat.search, open(path, encoding='utf-8', errors='ignore')) if m and a.clip in m.group(1)]
    out, cur = [], []
    for an, f, r, s, h, hit, hold in rows:
        f = float(f)
        if cur and (an != cur[-1][0] or f < cur[-1][1] - 1 or any(abs(f - w[0]) < 0.02 for w in WIN)):
            out.append(cur); cur = []
        cur.append((an, f, float(r), float(s), float(h)))
    if cur:
        out.append(cur)
    return out


def metrics(c):
    k_i = next((i for i, w in enumerate(WIN) if w[0] - 3 <= c[0][1] <= w[1]), None)
    if k_i is None:
        return None
    s, k, h, e = WIN[k_i]
    wind = [x for x in c if x[1] < k]
    seg = [x for x in c if k - 2 <= x[1] <= h + 4]
    if len(seg) < 3 or not wind:
        return None
    hi = max(range(len(seg)), key=lambda i: seg[i][4])
    ti = max(range(len(seg)), key=lambda i: seg[i][3])
    return dict(cut=k_i + 1, windup=len(wind), strike=sum(1 for x in c if k <= x[1] < h), total=len(c), lag=ti - hi,
                ratio=round(seg[ti][3] / max(seg[hi][4], .1), 2), tip_peak=round(seg[ti][3], 1),
                contrast=round(seg[ti][3] / max(st.mean(x[3] for x in wind), .1), 1))


res = {}
for p in a.logs:
    ms = [m for m in map(metrics, swings(p)) if m]
    res[p] = ms
    if ms:
        print(p, len(ms), {k: round(st.mean(m[k] for m in ms), 2) for k in ('windup', 'strike', 'total', 'lag', 'ratio', 'contrast', 'tip_peak')})
if a.json:
    json.dump(res, open(a.json, 'w'), indent=1)
