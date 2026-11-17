"""Per-cycle metrics, voltage profiles, dQ/dV and plot decimation."""
from __future__ import annotations

import numpy as np

from .model import CHARGE, DISCHARGE, REST, CellData


def cycle_table(cell: CellData, ce_mode: str = "dchg/chg") -> list:
    """One dict per cycle that has at least one charge or discharge step.

    ce_mode  "dchg/chg": CE = discharge / charge capacity of the same cycle
             (cathodes, full cells, Li/Na–Cl2 cells);
             "chg/dchg": CE = charge / discharge (anode half-cells).
    Energy efficiency uses the same direction.
    """
    rows = {}
    for s in cell.steps:
        if s.kind == REST:
            continue
        r = rows.setdefault(s.cycle, dict(cycle=s.cycle, chg_mAh=0.0, dchg_mAh=0.0, chg_mWh=0.0,
                                          dchg_mWh=0.0, n_chg=0, n_dchg=0))
        if s.kind == CHARGE:
            r["chg_mAh"] += s.capacity_mAh
            r["chg_mWh"] += s.energy_mWh
            r["n_chg"] += 1
        else:
            r["dchg_mAh"] += s.capacity_mAh
            r["dchg_mWh"] += s.energy_mWh
            r["n_dchg"] += 1
    out = []
    nan = float("nan")
    for c in sorted(rows):
        r = rows[c]
        qc, qd, ec, ed = r["chg_mAh"], r["dchg_mAh"], r["chg_mWh"], r["dchg_mWh"]
        r["Vavg_chg"] = ec / qc if r["n_chg"] and qc > 0 else nan
        r["Vavg_dchg"] = ed / qd if r["n_dchg"] and qd > 0 else nan
        r["dV"] = r["Vavg_chg"] - r["Vavg_dchg"]
        if not r["n_chg"]:
            r["chg_mAh"] = r["chg_mWh"] = nan
        if not r["n_dchg"]:
            r["dchg_mAh"] = r["dchg_mWh"] = nan
        both = r["n_chg"] and r["n_dchg"] and qc > 0 and qd > 0
        if both:
            if ce_mode == "chg/dchg":
                r["CE"], r["EE"] = 100 * qc / qd, (100 * ec / ed if ed > 0 else nan)
            else:
                r["CE"], r["EE"] = 100 * qd / qc, (100 * ed / ec if ec > 0 else nan)
        else:
            r["CE"] = r["EE"] = nan
        r["complete"] = True
        out.append(r)
    if out and last_cycle_incomplete(cell):
        out[-1]["complete"] = False
    return out


def last_cycle_incomplete(cell: CellData) -> bool:
    """Heuristic: is the last cycle cut short (test still running or stopped mid-step)?

    The last cycle counts as incomplete if it has fewer charge/discharge steps
    than the cycle before it, or if its final step matches the corresponding
    step of the previous cycle in neither end voltage (voltage cut-off),
    duration (time limit) nor capacity (capacity limit).
    """
    act = [s for s in cell.steps if s.kind != REST]
    cyc = sorted({s.cycle for s in act})
    if len(cyc) < 2:
        return False
    last = [s for s in act if s.cycle == cyc[-1]]
    prev = [s for s in act if s.cycle == cyc[-2]]
    if len(last) < len(prev):
        return True
    sl = last[-1]
    same = [s for s in prev if s.kind == sl.kind]
    if not same:
        return False
    sp = same[-1]
    # The voltage criterion applies only if the previous step really ended on a
    # voltage cut-off: away from 0 V (symmetric cells sit near 0 V) and with the
    # voltage still moving at the end (a time-limited step usually ends on a plateau).
    v_ok = (abs(sp.V_end) > 0.1 and _steep_end(cell, sp)
            and abs(sl.V_end - sp.V_end) <= 0.01 * abs(sp.V_end) + 0.005)
    t_ok = abs(sl.duration_s - sp.duration_s) <= 0.02 * sp.duration_s + 2
    q_ok = sp.capacity_mAh > 0 and abs(sl.capacity_mAh - sp.capacity_mAh) <= 0.02 * sp.capacity_mAh
    return not (v_ok or t_ok or q_ok)


def _steep_end(cell: CellData, s, frac: float = 0.02, dv: float = 0.01) -> bool:
    """Did the voltage change by more than dv (V) over the last `frac` of the step?"""
    t = cell.t[s.start:s.stop]
    if len(t) < 3 or s.duration_s <= 0:
        return False
    j = int(np.searchsorted(t, t[-1] - frac * s.duration_s))
    j = min(j, len(t) - 2)
    return abs(float(cell.V[s.stop - 1] - cell.V[s.start + j])) > dv


def first_discharge_cycle(cell: CellData):
    for s in cell.steps:
        if s.kind == DISCHARGE and s.capacity_mAh > 0:
            return s.cycle
    return None


def profile(cell: CellData, cycle: int, kind: str):
    """(capacity_mAh, voltage) of all `kind` steps of one cycle, capacity accumulated across steps."""
    steps = [s for s in cell.steps if s.cycle == cycle and s.kind == kind]
    if not steps:
        return None
    qs, vs, off = [], [], 0.0
    for s in steps:
        q = cell.Q[s.start:s.stop] + off
        qs.append(q)
        vs.append(cell.V[s.start:s.stop])
        off = float(q[-1])
    return np.concatenate(qs), np.concatenate(vs)


def dqdv(Q: np.ndarray, V: np.ndarray, dv: float = 0.005, smooth: int = 3):
    """Differential capacity by voltage-step resampling.

    A point is kept each time the voltage has moved by at least `dv` (V) from
    the last kept point; dQ/dV is the finite difference between kept points,
    then a centred moving average over `smooth` points. Discharge gives
    negative values (Q rises while V falls).
    """
    if Q is None or len(Q) < 3:
        return np.array([]), np.array([])
    keep = [0]
    v0 = V[0]
    for i in range(1, len(V)):
        if abs(V[i] - v0) >= dv:
            keep.append(i)
            v0 = V[i]
    if len(keep) < 3:
        return np.array([]), np.array([])
    k = np.array(keep)
    Vk, Qk = V[k], Q[k]
    dV = np.diff(Vk)
    dQ = np.diff(Qk)
    x = 0.5 * (Vk[1:] + Vk[:-1])
    y = dQ / dV
    if smooth and smooth > 1 and len(y) > smooth:
        w = np.ones(int(smooth)) / int(smooth)
        y = np.convolve(y, w, mode="same")
        h = int(smooth) // 2
        x, y = x[h:len(x) - h], y[h:len(y) - h]
    return x, y


def decimate(x: np.ndarray, y: np.ndarray, n: int = 4000):
    """Reduce a curve to about n points evenly spaced along its (normalised) length.

    Sharp features (steps, spikes) cover a long path and keep their points;
    long flat stretches are thinned. Purely cosmetic: used only for drawing.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) <= n:
        return x, y
    fx, fy = np.isfinite(x), np.isfinite(y)
    sx = np.ptp(x[fx]) if fx.any() else 1.0
    sy = np.ptp(y[fy]) if fy.any() else 1.0
    sx = sx or 1.0
    sy = sy or 1.0
    d = np.hypot(np.diff(x) / sx * 1.5, np.diff(y) / sy)
    d = np.nan_to_num(d)
    s = np.r_[0.0, np.cumsum(d)]
    if s[-1] <= 0:
        idx = np.linspace(0, len(x) - 1, n).astype(int)
    else:
        idx = np.searchsorted(s, np.linspace(0, s[-1], n))
        idx = np.clip(idx, 0, len(x) - 1)
        extra = [0, len(x) - 1]
        if fy.any():
            extra += [int(np.nanargmin(y)), int(np.nanargmax(y))]
        idx = np.unique(np.r_[idx, extra])
    return x[idx], y[idx]
