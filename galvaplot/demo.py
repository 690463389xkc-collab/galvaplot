"""Synthetic example data written in the .cex layout read by readers.land_cex.

The curves are made up (a generic layered-oxide cathode vs Li, with different
fade rates); they exist so new users can try the program and so tests do not
depend on anyone's real data.
"""
from __future__ import annotations

import os
import struct

import numpy as np

MODE = {"rest": 0x70, "charge": 0x03, "discharge": 0x02}


def _ocv(x):
    """Open-circuit voltage vs state of charge x (0..1) of a made-up layered oxide."""
    return 3.55 + 0.62 * x + 0.05 * np.tanh((x - 0.5) * 6) + 0.10 * np.exp(-(1 - x) * 25) - 0.35 * np.exp(-x * 18)


class CexWriter:
    """Minimal writer for the record layout documented in readers/land_cex.py."""

    def __init__(self, t0_unix=1_760_000_000):
        self.buf = bytearray(b"\x10\x11\x09\x88" + bytes(60))
        self.t0 = t0_unix

    def step(self, mode, cycle, step_no, t_ms, set_current_A, kind=0x22):
        """mode: 'rest' / 'charge' / 'discharge' or a raw mode byte; kind 0x25 = resume."""
        r = bytearray(32)
        r[0:4] = b"\xc2\xcc\xff\xff"
        r[4] = kind
        struct.pack_into("<I", r, 8, int(self.t0 + t_ms / 1000))
        r[16] = MODE[mode] if isinstance(mode, str) else int(mode)
        struct.pack_into("<H", r, 20, cycle - 1)
        r[22] = step_no
        struct.pack_into("<f", r, 28, float(set_current_A))
        self.buf += r

    def points(self, t_ms, V, I_A, Q_Ah, E_Wh):
        rec = np.zeros(len(t_ms), dtype=[("magic", "<u4"), ("pad", "<u4"), ("t", "<u8"),
                                         ("V", "<f4"), ("I", "<f4"), ("Q", "<f4"), ("E", "<f4")])
        rec["magic"] = 0xFFFFCCC3
        rec["t"], rec["V"], rec["I"], rec["Q"], rec["E"] = t_ms, V, I_A, Q_Ah, E_Wh
        self.buf += rec.tobytes()

    def trailer(self, name, folder):
        content = name.encode("gbk", "replace") + b"\x00" + folder.encode("gbk", "replace") + b"\x00"
        content += bytes(-len(content) % 16)
        key = struct.pack("<HH", 0xCC, len(content) & 0xFFFF)
        self.buf += b"\xaa\xaa\xff\xff" + key + bytes(8) + content + b"\xbb\xbb\xff\xff" + key + bytes(24)

    def save(self, path):
        with open(path, "wb") as f:
            f.write(bytes(self.buf))


def synth_cell(path, cap0_mAh=2.0, fade=0.002, r_ohm=25.0, n_cycles=40, i_mA=0.4, seed=0,
               v_hi=4.3, v_lo=2.8, dt_s=30.0, ce_first=0.86):
    """Write one synthetic cathode half-cell test: rest, then n x (charge, discharge)."""
    rng = np.random.default_rng(seed)
    w = CexWriter()
    t = 0.0
    # 1 h rest
    w.step("rest", 1, 1, t * 1000, 0.0)
    tt = np.arange(0, 3600 + 1e-9, 120.0)
    w.points((t + tt) * 1000, 3.05 + 0.02 * np.exp(-tt / 900), np.zeros_like(tt), np.zeros_like(tt), np.zeros_like(tt))
    t += tt[-1] + dt_s
    for c in range(1, n_cycles + 1):
        cap = cap0_mAh * (1 - fade * (c - 1)) * (1 + 0.003 * rng.standard_normal())
        r = r_ohm * (1 + 0.004 * (c - 1))
        ce = ce_first if c == 1 else min(0.9995, 0.996 + 0.002 * rng.standard_normal())
        q_chg = None
        for kind in ("charge", "discharge"):
            sign = 1 if kind == "charge" else -1
            if kind == "charge":
                q_max = cap / ce if c == 1 else cap * 1.002     # extra first-charge capacity (SEI/CEI)
            else:
                q_max = q_chg * ce
            n = int(q_max / i_mA * 3600 / dt_s) + 2
            q = np.linspace(0, q_max, n)                         # mAh within the step
            # state of charge runs 0 -> 1 on charge and 1 -> 0 on discharge; the extra
            # first-charge capacity is irreversible, so it does not come back on discharge
            xs = q / q_max if kind == "charge" else 1 - q / q_max
            V = _ocv(np.clip(xs, 0, 1)) + sign * (i_mA * 1e-3 * r) + 0.0008 * rng.standard_normal(n)
            if kind == "charge" and c == 1:
                V += 0.06 * np.exp(-q / (0.08 * cap))            # first-charge activation
            hit = (V >= v_hi) if kind == "charge" else (V <= v_lo)
            if hit.any():
                k = int(np.argmax(hit))
                q, V = q[:k + 1], V[:k + 1]
                V[-1] = v_hi if kind == "charge" else v_lo
            if kind == "charge":
                q_chg = float(q[-1])
            ts = q / i_mA * 3600.0
            E = np.r_[0, np.cumsum(0.5 * (V[1:] + V[:-1]) * np.diff(q))]  # mWh
            w.step(kind, c, 2 if kind == "charge" else 3, t * 1000, sign * i_mA / 1000)
            w.points((t + ts) * 1000, V, np.full(len(q), sign * i_mA / 1000), q / 1000, E / 1000)
            t += ts[-1] + dt_s
    w.trailer(os.path.splitext(os.path.basename(path))[0], r"C:\data\demo")
    w.save(path)


DEMO_FILES = [
    # messy names on purpose: date prefix, recipe, LAND _box_channel suffix
    ("20261101-NCM811-1M LiPF6 EC-DMC-cell1_005_3.cex", dict(cap0_mAh=2.05, fade=0.0045, r_ohm=30, seed=1)),
    ("20261101-NCM811-1M LiPF6 EC-DMC-cell2_005_4.cex", dict(cap0_mAh=1.98, fade=0.0050, r_ohm=32, seed=2)),
    ("20261103-NCM811-1M LiPF6 EC-DMC+2%FEC-cell1_006_1.cex", dict(cap0_mAh=2.02, fade=0.0018, r_ohm=24, seed=3)),
    ("20261103-NCM811-1M LiPF6 EC-DMC+2%FEC-cell2_006_2.cex", dict(cap0_mAh=2.07, fade=0.0021, r_ohm=26, seed=4)),
]


def write_demo(folder):
    os.makedirs(folder, exist_ok=True)
    out = []
    for name, kw in DEMO_FILES:
        p = os.path.join(folder, name)
        synth_cell(p, **kw)
        out.append(p)
    return out
