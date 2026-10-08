"""Bake secondary motion (hair, capes, skirts, tails) into clip keys.

Each chain is a verlet rope anchored to its animated parent bone (forward kinematics of the
keyed body). Every segment springs back toward its rest direction; the rest frame inherits
only `follow` of the parent's rotation, the rest hangs with gravity. Simulated directions are
converted back into LOCAL bone rotations (deltas from a rest pose of zero local rotation).

Parameters are physical: natural period (s) and damping ratio. Typical values
  hair   0.6-0.7 s, zeta 0.5, follow 0.75
  cape   0.85-0.9 s, zeta 0.48, follow 0.25     (anchor capes to the chest, not the arm)
  skirt  0.55-0.72 s per column (make columns differ), zeta 0.44-0.5, follow 0.45-0.6

Conventions: positions in reference px with y UP, rotations in degrees, +CCW (Unity).
"""
import math

import numpy as np


def rot(a):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return np.array([[c, -s], [s, c]])


class Skeleton:
    """bones: [(name, parent or None, (x, y_down))]; image_height converts to y up."""

    def __init__(self, bones, image_height, ppu):
        self.pos = {n: np.array([p[0], image_height - p[1]], float) for n, _, p in bones}
        self.parent = {n: q for n, q, _ in bones}
        self.ppu = ppu

    def world(self, pose, name, cache):
        """(position px y-up, angle deg) of `name` for a pose {(bone, prop): value}.
        props: "rot" (deg), "posX"/"posY" (Unity units)."""
        if name in cache:
            return cache[name]
        par = self.parent[name]
        off = np.array([pose.get((name, "posX"), 0.0), pose.get((name, "posY"), 0.0)]) * self.ppu
        if par is None:
            res = (self.pos[name] + off, pose.get((name, "rot"), 0.0))
        else:
            pp, pa = self.world(pose, par, cache)
            res = (pp + rot(pa) @ (self.pos[name] - self.pos[par] + off), pa + pose.get((name, "rot"), 0.0))
        cache[name] = res
        return res


class Rope:
    def __init__(self, skel, bones, tip, period, zeta, follow, fps, substeps):
        self.skel, self.bones, self.follow = skel, bones, follow
        pts = [skel.pos[b] for b in bones]
        last = pts[-1] - pts[-2]
        pts.append(pts[-1] + last / np.linalg.norm(last) * tip)
        self.rest = [pts[k + 1] - pts[k] for k in range(len(bones))]
        self.length = [np.linalg.norm(d) for d in self.rest]
        w = 2 * math.pi / (period * fps * substeps)
        self.stiff = [w * w * f for f in (1.0, 0.75, 0.55, 0.45, 0.4)[:len(bones)]]   # softer toward the tip
        self.damp = 1 - 2 * zeta * w

    def anchor(self, pose, cache):
        par = self.skel.parent[self.bones[0]]
        pp, pa = self.skel.world(pose, par, cache)
        return pp + rot(pa) @ (self.skel.pos[self.bones[0]] - self.skel.pos[par]), pa

    def reset(self, root, parent_angle):
        self.p = [root]
        for d in self.rest:
            self.p.append(self.p[-1] + rot(parent_angle * self.follow) @ d)
        self.prev = [q.copy() for q in self.p]

    def step(self, root, parent_angle, offsets):
        self.p[0] = root
        self.prev[0] = root
        angle = parent_angle * self.follow
        for k in range(len(self.rest)):
            cur, old = self.p[k + 1], self.prev[k + 1]
            target = self.p[k] + rot(angle + offsets[k]) @ self.rest[k]
            nxt = cur + (cur - old) * self.damp + (target - cur) * self.stiff[k]
            d = nxt - self.p[k]
            nxt = self.p[k] + d / np.linalg.norm(d) * self.length[k]
            self.prev[k + 1], self.p[k + 1] = cur, nxt
            angle = math.degrees(math.atan2(d[1], d[0])) - math.degrees(math.atan2(self.rest[k][1], self.rest[k][0]))

    def deltas(self, parent_angle):
        out, prev = [], parent_angle
        for k, d0 in enumerate(self.rest):
            d = self.p[k + 1] - self.p[k]
            phi = math.degrees(math.atan2(d[1], d[0]) - math.atan2(d0[1], d0[0]))
            phi = (phi - prev + 180) % 360 - 180 + prev
            out.append(phi - prev)
            prev = phi
        return out


def simulate(skel, chains, pose_at, t0, t1, fps=30, substeps=8, breeze=None, breeze_period=1.6):
    """chains: {name: (bones, tip_px, period_s, zeta, follow)}; pose_at(t) -> keyed pose.
    breeze: {name: (amp_deg, phase)} adds a slow travelling sway (idle).
    Returns a list (one per frame from t0 to t1) of {bone: local rotation delta}."""
    ropes = {n: Rope(skel, *c, fps=fps, substeps=substeps) for n, c in chains.items()}
    for r in ropes.values():
        root, pa = r.anchor(pose_at(t0), {})
        r.reset(root, pa)
    frames = []
    dt = 1.0 / (fps * substeps)
    for f in range(int(round((t1 - t0) * fps)) + 1):
        t = t0 + f / fps
        for s in range(substeps):
            ts = t + s * dt
            pose, cache = pose_at(ts), {}
            for name, r in ropes.items():
                root, pa = r.anchor(pose, cache)
                off = [0.0] * len(r.bones)
                if breeze and name in breeze:
                    amp, ph = breeze[name]
                    off = [amp * (k + 1) / len(off) * math.sin(2 * math.pi * ts / breeze_period - ph - 0.7 * k)
                           for k in range(len(off))]
                r.step(root, pa, off)
        pose, cache, vals = pose_at(t), {}, {}
        for r in ropes.values():
            _, pa = r.anchor(pose, cache)
            vals.update(zip(r.bones, r.deltas(pa)))
        frames.append(vals)
    return frames


def tangents(values, dt, periodic):
    """Finite-difference tangents; periodic ones make a seamless loop."""
    n, out = len(values), []
    for i in range(n):
        if periodic:
            a = values[(i - 1) % (n - 1)] if i > 0 else values[n - 2]
            b = values[(i + 1) % (n - 1)] if i < n - 1 else values[1]
            span = 2 * dt
        else:
            a, b = values[max(i - 1, 0)], values[min(i + 1, n - 1)]
            span = dt * (2 if 0 < i < n - 1 else 1)
        out.append((b - a) / span)
    return out


def close_loop(values):
    """Remove residual drift so the last key equals the first (take the last simulated cycle)."""
    n = len(values) - 1
    drift = values[-1] - values[0]
    return [v - drift * (i / n) for i, v in enumerate(values)]


def settle(values, times, start, end):
    """Ease baked cloth to the rest pose between `start` and `end` (end of a one-shot clip)."""
    out = []
    for v, t in zip(values, times):
        if t > start:
            u = min((t - start) / (end - start), 1.0)
            v *= 1 - u * u * (3 - 2 * u)
        out.append(v)
    return out
