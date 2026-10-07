"""Estelle v007 Idle / Attack -> anim.json.

Body joints are keyed. Hair, shawl panels and the three dress columns are simulated: each chain
is a verlet rope anchored to its animated parent (forward kinematics of the keyed body), with a
per-segment spring back to its rest shape. The simulated directions are converted into local
bone rotations, so cloth lags, overshoots and settles instead of bending as one block.

Unity convention: +rotation = counter-clockwise; the character faces +X (forward lean < 0).
Attack concept: forward staff-thrust cast. v007: the staff sleeve is split (body band + rigid arm piece), so the shoulder can lift to 28 deg again without stretching; v006: shoulder <= 11 deg, the thrust comes from elbow (tested -26..+10) and wrist, so cloth attached to the body never stretches. (wind-up, strike, impact flash, follow-through).
"""
import json
import math
import os
import shutil

import numpy as np

import rig_v7 as rig

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
    ("Hips", "posY"): (0.012, 0.0), ("Hips", "posX"): (0.004, 1.2), ("Hips", "rot"): (0.4, 0.4),
    ("Spine", "rot"): (0.5, 0.3), ("Chest", "rot"): (0.8, 0.6), ("Neck", "rot"): (1.3, 1.0),
    ("FreeShoulder", "rot"): (1.4, 1.3), ("FreeElbow", "rot"): (1.8, 1.7),
    ("StaffShoulder", "rot"): (-1.0, 1.1), ("StaffElbow", "rot"): (1.0, 1.4), ("StaffWrist", "rot"): (0.9, 1.7),
}


def idle_pose(t):
    return {k: a * math.sin(2 * math.pi * t / IDLE_LENGTH - ph) for k, (a, ph) in IDLE_KEYED.items()}


def idle_clip():
    cycles = 5
    sim = simulate(idle_pose, 0.0, IDLE_LENGTH * cycles, breeze=True)
    n = int(round(IDLE_LENGTH * FPS))
    dt = 1 / FPS
    start = IDLE_LENGTH * (cycles - 1)
    times = [i * dt for i in range(n + 1)]
    ch = []
    for k in IDLE_KEYED:
        vals = [idle_pose(t)[k] for t in times]
        vals[-1] = vals[0]
        ch.append(dict(bone=k[0], prop=k[1], times=times, values=vals, tangents=tangents(vals, dt, True)))
    for bones, *_ in CHAINS.values():
        for b in bones:
            vals = [sim[int(round(start * FPS)) + i][b] for i in range(len(times))]
            drift = vals[-1] - vals[0]
            vals = [v - drift * (i / n) for i, v in enumerate(vals)]     # close the loop exactly
            ch.append(dict(bone=b, prop="rot", times=times, values=vals, tangents=tangents(vals, dt, True)))
    return dict(name="EstelleIdleV7", length=IDLE_LENGTH, loop=True, channels=ch)


# ----------------------------------------------------------------------------------- Attack
def ease_in_out(u):
    return u * u * (3 - 2 * u)


def ease_in(u):
    return u * u * u


def ease_out(u):
    return 1 - (1 - u) ** 3


def attack_pose(body, staff_shoulder, staff_elbow, staff_world, free_world, free_elbow, extra):
    hips, spine, chest = body
    lean = hips + spine + chest
    p = {("Hips", "rot"): hips, ("Spine", "rot"): spine, ("Chest", "rot"): chest,
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
    chans = sorted({c for _, _, p in ATTACK_KEYS for c in p})
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
    return dict(name="EstelleAttackV7", length=ATTACK_LENGTH, loop=False, channels=ch)


if __name__ == "__main__":
    data = dict(clips=[idle_clip(), attack_clip()])
    path = os.path.join(rig.OUT, "anim.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    shutil.copyfile(path, os.path.join(rig.UNITY_V4, "anim.json"))
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
