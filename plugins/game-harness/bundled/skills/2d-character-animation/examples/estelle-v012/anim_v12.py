"""Estelle v012 Idle / Attack -> anim.json (v007/v011 motion on the v012 part-per-bone rig).

Body joints are keyed; the legs are solved with two-bone IK every frame so the feet stay planted
while the hips move (the knee always bends forward, the foot keeps its rest angle). Hair, shawl
panels and the three dress columns are simulated as in v011 (verlet ropes with a natural period,
damping ratio and parent follow per chain), then baked into bone rotations.

Unity convention: +rotation = counter-clockwise; the character faces +X (forward lean < 0).
Attack concept: forward staff-thrust cast (wind-up, strike, impact flash, follow-through).
"""
import json
import math
import os
import shutil

import numpy as np

import rig_v12 as rig

HERE = os.path.dirname(os.path.abspath(__file__))
FPS = 30
SUB = 8                         # simulation substeps per frame
PPU = rig.PPU
POS = {n: np.array([p[0], rig.H - p[1]], float) for n, _, p in rig.BONES}   # px, y up (ground-relative is irrelevant)
PARENT = rig.PARENT

CHAINS = {
    # name: (bones, virtual tip px, natural period s, damping ratio, parent follow)
    # Period/damping set how cloth swings (slow, soft settle); `follow` is how much of the
    # parent's rotation the rest shape inherits, the remainder hangs with gravity.
    "HairL": (["HairL1", "HairL2", "HairL3"], 150, 0.70, 0.50, 0.75),
    "HairR": (["HairR1", "HairR2"], 110, 0.62, 0.50, 0.75),
    "ShawlL": (["ShawlL1", "ShawlL2", "ShawlL3"], 260, 0.90, 0.48, 0.25),
    "ShawlR": (["ShawlR1", "ShawlR2", "ShawlR3"], 260, 0.85, 0.48, 0.25),
    "DressL": (["DressL1", "DressL2", "DressL3"], 220, 0.62, 0.46, 0.50),
    "DressC": (["DressC1", "DressC2", "DressC3"], 220, 0.55, 0.50, 0.60),
    "DressR": (["DressR1", "DressR2", "DressR3"], 220, 0.72, 0.44, 0.45),
}
# Idle breeze on the chain tips (deg amplitude, phase) keeps cloth alive between breaths.
BREEZE = {"HairL": (0.8, 0.6), "HairR": (0.7, 1.4), "ShawlL": (0.8, 0.2), "ShawlR": (0.8, 1.1),
          "DressL": (1.0, 0.4), "DressC": (0.7, 1.9), "DressR": (1.1, 3.3)}


def rot(a):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return np.array([[c, -s], [s, c]])


def world(pose, name, cache):
    """World (position px y-up, angle deg) of bone `name` for a pose dict of local deltas."""
    if name in cache:
        return cache[name]
    par = PARENT[name]
    off = np.array([pose.get((name, "posX"), 0.0), pose.get((name, "posY"), 0.0)]) * PPU
    if par is None:
        res = (POS[name] + off, pose.get((name, "rot"), 0.0))
    else:
        pp, pa = world(pose, par, cache)
        res = (pp + rot(pa) @ (POS[name] - POS[par] + off), pa + pose.get((name, "rot"), 0.0))
    cache[name] = res
    return res


class Rope:
    def __init__(self, bones, tip, period, zeta, follow):
        self.bones, self.follow = bones, follow
        w = 2 * math.pi / (period * FPS * SUB)                  # rad per substep
        # outer segments are softer so a wave travels down the chain
        self.stiff = [w * w * f for f in (1.0, 0.75, 0.55)[:len(bones)]]
        self.damp = 1 - 2 * zeta * w
        pts = [POS[b] for b in bones]
        last = pts[-1] - pts[-2]
        pts.append(pts[-1] + last / np.linalg.norm(last) * tip)
        self.rest = [pts[k + 1] - pts[k] for k in range(len(bones))]
        self.length = [np.linalg.norm(d) for d in self.rest]
        self.p = None

    def reset(self, root, frame_angle):
        self.p = [root]
        for d in self.rest:
            self.p.append(self.p[-1] + rot(frame_angle) @ d)
        self.prev = [q.copy() for q in self.p]

    def step(self, root, frame_angle, offsets):
        self.p[0] = root
        self.prev[0] = root
        angle = frame_angle * self.follow
        for k in range(len(self.rest)):
            cur, old = self.p[k + 1], self.prev[k + 1]
            vel = (cur - old) * self.damp
            ang_k = angle + offsets[k]
            target = self.p[k] + rot(ang_k) @ self.rest[k]
            nxt = cur + vel + (target - cur) * self.stiff[k]
            d = nxt - self.p[k]
            nxt = self.p[k] + d / np.linalg.norm(d) * self.length[k]
            self.prev[k + 1] = cur
            self.p[k + 1] = nxt
            # the next segment's rest frame follows this segment's actual direction
            actual = math.degrees(math.atan2(d[1], d[0]))
            restang = math.degrees(math.atan2(self.rest[k][1], self.rest[k][0]))
            angle = actual - restang

    def deltas(self, frame_angle):
        out, prev = [], frame_angle
        for k, d0 in enumerate(self.rest):
            d = self.p[k + 1] - self.p[k]
            phi = math.degrees(math.atan2(d[1], d[0]) - math.atan2(d0[1], d0[0]))
            phi = (phi - prev + 180) % 360 - 180 + prev
            out.append(phi - prev)
            prev = phi
        return out


def simulate(pose_at, t0, t1, breeze=False):
    """Run all ropes from t0 to t1 driven by the keyed pose; returns per-frame chain deltas."""
    ropes = {n: Rope(*c) for n, c in CHAINS.items()}
    frames = []
    n_frames = int(round((t1 - t0) * FPS))
    dt = 1.0 / (FPS * SUB)
    for name, r in ropes.items():
        cache = {}
        pp, pa = world(pose_at(t0), PARENT[r.bones[0]], cache)
        root = pp + rot(pa) @ (POS[r.bones[0]] - POS[PARENT[r.bones[0]]])
        r.reset(root, pa * r.follow)
    for f in range(n_frames + 1):
        t = t0 + f / FPS
        for s in range(SUB):
            ts = t + s * dt
            pose = pose_at(ts)
            cache = {}
            for name, r in ropes.items():
                par = PARENT[r.bones[0]]
                pp, pa = world(pose, par, cache)
                root = pp + rot(pa) @ (POS[r.bones[0]] - POS[par])
                off = [0.0] * len(r.bones)
                if breeze:
                    amp, ph = BREEZE[name]
                    for k in range(len(off)):
                        off[k] = amp * (k + 1) / len(off) * math.sin(2 * math.pi * ts / IDLE_LENGTH * 2 - ph - 0.7 * k)
                r.step(root, pa, off)
        pose = pose_at(t)
        cache = {}
        vals = {}
        for name, r in ropes.items():
            _, pa = world(pose, PARENT[r.bones[0]], cache)
            for b, d in zip(r.bones, r.deltas(pa)):
                vals[b] = d
        frames.append(vals)
    return frames


LEGS = [("ThighR", "KneeR", "AnkleR"), ("ThighL", "KneeL", "AnkleL")]


def with_ik(pose):
    """Add thigh / knee / ankle rotations that keep each ankle at its rest position."""
    pose = dict(pose)
    for th, kn, an in LEGS:
        for b in (th, kn, an):
            pose[(b, "rot")] = 0.0
        cache = {}
        pp, pa = world(pose, "Hips", cache)
        hip = pp + rot(pa) @ (POS[th] - POS["Hips"])
        a0, b0 = POS[kn] - POS[th], POS[an] - POS[kn]
        l1, l2 = np.linalg.norm(a0), np.linalg.norm(b0)
        d = POS[an] - hip
        dist = min(np.linalg.norm(d), l1 + l2 - 0.05)
        ca = np.clip((l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist), -1, 1)
        base, off = math.atan2(d[1], d[0]), math.acos(ca)
        best = None
        for sgn in (1, -1):
            t1 = base + sgn * off
            knee = hip + l1 * np.array([math.cos(t1), math.sin(t1)])
            sh = POS[an] - knee
            cross = math.cos(t1) * sh[1] - math.sin(t1) * sh[0]
            if best is None or cross < best[0]:           # knee forward (+x) = negative cross
                best = (cross, t1, math.atan2(sh[1], sh[0]))
        _, t1, t2 = best
        thigh = math.degrees(t1 - math.atan2(a0[1], a0[0])) - pa
        knee = math.degrees(t2 - math.atan2(b0[1], b0[0])) - (pa + thigh)
        wrap = lambda v: (v + 180) % 360 - 180
        thigh, knee = wrap(thigh), wrap(knee)
        pose[(th, "rot")], pose[(kn, "rot")], pose[(an, "rot")] = thigh, knee, -(pa + thigh + knee)
    return pose


def tangents(values, dt, periodic):
    n = len(values)
    out = []
    for i in range(n):
        if periodic:
            a = values[(i - 1) % (n - 1)] if i > 0 else values[n - 2]
            b = values[(i + 1) % (n - 1)] if i < n - 1 else values[1]
        else:
            a = values[max(i - 1, 0)]
            b = values[min(i + 1, n - 1)]
        span = dt * (2 if (periodic or 0 < i < n - 1) else 1)
        out.append((b - a) / span)
    return out


# ------------------------------------------------------------------------------------- Idle
IDLE_LENGTH = 3.2
IDLE_KEYED = {
    # the hips stay still in Idle: moving them bends the legs under the sheer chiffon, whose baked
    # leg outlines then double up; the breath is in the chest and neck
    ("Chest", "rot"): (1.3, 0.5), ("Neck", "rot"): (1.3, 1.0),
    ("FreeShoulder", "rot"): (1.4, 1.3), ("FreeElbow", "rot"): (1.8, 1.7),
    ("StaffShoulder", "rot"): (-1.0, 1.1), ("StaffElbow", "rot"): (1.0, 1.4), ("StaffWrist", "rot"): (0.9, 1.7),
}


IDLE_HIPS_DROP = 0.0        # units; the hips bob below rest so the straight legs can follow


def idle_pose(t):
    p = {k: a * math.sin(2 * math.pi * t / IDLE_LENGTH - ph) for k, (a, ph) in IDLE_KEYED.items()}
    p[("Hips", "posY")] = p.get(("Hips", "posY"), 0.0) - IDLE_HIPS_DROP
    # keyed at rest so an unanimated hip never keeps another clip's value
    p.setdefault(("Hips", "posX"), 0.0); p.setdefault(("Hips", "rot"), 0.0)
    return with_ik(p)


def idle_clip():
    cycles = 5
    sim = simulate(idle_pose, 0.0, IDLE_LENGTH * cycles, breeze=True)
    n = int(round(IDLE_LENGTH * FPS))
    dt = 1 / FPS
    start = IDLE_LENGTH * (cycles - 1)
    times = [i * dt for i in range(n + 1)]
    ch = []
    for k in idle_pose(0.0):
        vals = [idle_pose(t)[k] for t in times]
        vals[-1] = vals[0]
        ch.append(dict(bone=k[0], prop=k[1], times=times, values=vals, tangents=tangents(vals, dt, True)))
    for bones, *_ in CHAINS.values():
        for b in bones:
            vals = [sim[int(round(start * FPS)) + i][b] for i in range(len(times))]
            drift = vals[-1] - vals[0]
            vals = [v - drift * (i / n) for i, v in enumerate(vals)]     # close the loop exactly
            ch.append(dict(bone=b, prop="rot", times=times, values=vals, tangents=tangents(vals, dt, True)))
    return dict(name="EstelleIdleV12", length=IDLE_LENGTH, loop=True, channels=ch)


# ----------------------------------------------------------------------------------- Attack
def ease_in_out(u):
    return u * u * (3 - 2 * u)


def ease_in(u):
    return u * u * u


def ease_out(u):
    return 1 - (1 - u) ** 3


SHOULDER_MAX = 8.0          # deg
HIPS_SHARE = 0.3             # share of the keyed hip rotation / travel kept on the hips


def attack_pose(body, staff_shoulder, staff_elbow, staff_world, free_world, free_elbow, extra):
    hips, spine, chest = body
    lean = hips + spine + chest
    # the lean is taken above the waist: turning the hips bends the legs under the sheer chiffon
    hips, spine = hips * HIPS_SHARE, spine + hips * (1 - HIPS_SHARE)
    # the staff shoulder is covered by the shawl and the bust: keep it within SHOULDER_MAX and give
    # the rest of the swing to the elbow (review round 1: a 28 deg shoulder tore the torso side open)
    s = max(-SHOULDER_MAX, min(SHOULDER_MAX, staff_shoulder))
    staff_elbow += staff_shoulder - s
    staff_shoulder = s
    p = {("Hips", "rot"): hips, ("Chest", "rot"): spine + chest,
         ("StaffShoulder", "rot"): staff_shoulder, ("StaffElbow", "rot"): staff_elbow,
         ("StaffWrist", "rot"): staff_world - (lean + staff_shoulder + staff_elbow),
         ("FreeShoulder", "rot"): free_world - lean, ("FreeElbow", "rot"): free_elbow}
    p.update(extra)
    return p


ATTACK_KEYS = [
    (0.00, None, {}),
    # Wind-up: weight back, chest opens, staff drawn back so the orb tips behind the head.
    (0.28, ease_in_out, attack_pose((1.5, 2.5, 4.0), -8, 8, 22, 5, 5, {
        ("Hips", "posX"): -0.05, ("Hips", "posY"): -0.02, ("Neck", "rot"): -2.0})),
    # Strike: fast drive forward; the wrist snaps the orb toward the target.
    (0.38, ease_in, attack_pose((-2.0, -3.5, -6.5), 24, -20, -35, -8, -4, {
        ("Hips", "posX"): 0.07, ("Hips", "posY"): -0.03, ("Neck", "rot"): 4.0,
        ("CastFlash", "scale"): 1.15, ("CastFlash", "alpha"): 1.0})),
    # Impact hold with a small overshoot.
    (0.48, ease_out, attack_pose((-2.4, -4.0, -7.5), 28, -22, -40, -10, -5, {
        ("Hips", "posX"): 0.08, ("Hips", "posY"): -0.032, ("Neck", "rot"): 4.5,
        ("CastFlash", "scale"): 1.55, ("CastFlash", "alpha"): 0.85})),
    # Follow-through: the body eases while the cloth (simulated) keeps travelling.
    (0.66, ease_in_out, attack_pose((-1.5, -2.5, -4.5), 20, -14, -28, -5, -2, {
        ("Hips", "posX"): 0.055, ("Hips", "posY"): -0.02, ("Neck", "rot"): 3.0,
        ("CastFlash", "scale"): 2.0, ("CastFlash", "alpha"): 0.0})),
    (1.00, ease_in_out, {}),
]
ATTACK_LENGTH = 1.25            # body is back at rest at 1.0 s; cloth settles until 1.25 s


def keyed_attack(t):
    p = _keyed_attack(t)
    for k in (("Hips", "posX"), ("Hips", "posY")):
        if k in p:
            p[k] *= HIPS_SHARE
    p[("Hips", "posY")] = p.get(("Hips", "posY"), 0.0) - IDLE_HIPS_DROP
    # keyed at rest so an unanimated hip never keeps another clip's value
    p.setdefault(("Hips", "posX"), 0.0); p.setdefault(("Hips", "rot"), 0.0)   # same baseline as Idle: no pop at the transitions
    return with_ik(p)


def _keyed_attack(t):
    keys = ATTACK_KEYS
    chans = {c for _, _, p in keys for c in p}
    if t >= keys[-1][0]:
        return {c: 0.0 for c in chans}
    if t <= 0:
        return {c: 0.0 for c in chans}
    for (t0, _, p0), (t1, ease, p1) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            u = ease((t - t0) / (t1 - t0))
            return {c: p0.get(c, 0.0) + (p1.get(c, 0.0) - p0.get(c, 0.0)) * u for c in chans}
    return {c: 0.0 for c in chans}


def attack_clip():
    sim = simulate(keyed_attack, -0.4, ATTACK_LENGTH)
    n = int(round(ATTACK_LENGTH * FPS))
    dt = 1 / FPS
    times = [i * dt for i in range(n + 1)]
    ch = []
    chans = sorted(keyed_attack(0.3).keys())
    for c in chans:
        vals = [keyed_attack(t)[c] for t in times]
        ch.append(dict(bone=c[0], prop=c[1], times=times, values=vals, tangents=tangents(vals, dt, False)))
    settle_start = 1.0                       # body is at rest; ease the cloth into the idle pose
    for bones, *_ in CHAINS.values():
        for b in bones:
            vals = [sim[int(round(0.4 * FPS)) + i][b] for i in range(len(times))]
            for i, t in enumerate(times):
                if t > settle_start:
                    u = (t - settle_start) / (ATTACK_LENGTH - settle_start)
                    vals[i] *= 1 - u * u * (3 - 2 * u)
            ch.append(dict(bone=b, prop="rot", times=times, values=vals, tangents=tangents(vals, dt, False)))
    return dict(name="EstelleAttackV12", length=ATTACK_LENGTH, loop=False, channels=ch)


BLEND_IN, BLEND_OUT = 0.2, 1.0      # s: the attack leaves the idle's first pose by BLEND_IN, returns after BLEND_OUT


def join_to_idle(attack, idle):
    """Start and end the attack on the idle's first frame (every channel, cloth included), so
    Idle -> Attack -> Idle has no jump even without an Animator crossfade."""
    first = {(c["bone"], c["prop"]): c["values"][0] for c in idle["channels"]}
    for c in attack["channels"]:
        key = (c["bone"], c["prop"])
        if key not in first:
            continue
        s0 = first[key]
        for i, t in enumerate(c["times"]):
            if t < BLEND_IN:
                w = 1 - ease_in_out(t / BLEND_IN)
            elif t > BLEND_OUT:
                w = ease_in_out((t - BLEND_OUT) / (attack["length"] - BLEND_OUT))
            else:
                w = 0.0
            c["values"][i] = c["values"][i] * (1 - w) + s0 * w
        c["tangents"] = tangents(c["values"], 1 / FPS, False)
    return attack


if __name__ == "__main__":
    idle = idle_clip()
    data = dict(clips=[idle, join_to_idle(attack_clip(), idle)])
    path = os.path.join(HERE, "anim.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    shutil.copyfile(path, os.path.join(rig.UNITY_V12, "anim.json"))
    for c in data["clips"]:
        world_dev = {}
        for chain, (bones, *_r) in CHAINS.items():
            vals = [0.0] * len(c["channels"][0]["times"])
            for b in bones:
                chv = next(ch for ch in c["channels"] if ch["bone"] == b)
                vals = [v + w for v, w in zip(vals, chv["values"])]
            world_dev[chain + "_tip_vs_parent"] = round(max(abs(v) for v in vals), 1)
        print(c["name"], world_dev)
        peaks = {ch["bone"]: round(max(abs(v) for v in ch["values"]), 2) for ch in c["channels"]
                 if ch["prop"] == "rot" and ch["bone"][:-1] in ("HairL", "HairR", "ShawlL", "ShawlR", "DressL", "DressC", "DressR")}
        print(c["name"], len(c["channels"]), "channels; cloth peak deg:", peaks)
