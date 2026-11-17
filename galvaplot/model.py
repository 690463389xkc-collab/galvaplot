"""Common in-memory model for one battery test file.

Every reader (LAND .cex, Excel/CSV exports) converts its input into a
:class:`CellData`: per-point arrays plus a list of :class:`Step` objects.

Conventions
-----------
* time ``t`` in seconds from the first data point
* voltage ``V`` in volts
* current ``I`` in mA, positive = charge, negative = discharge
* ``Q`` / ``E``: capacity (mAh) and energy (mWh) accumulated *within the
  current step*, always >= 0 (they restart at every step)
* cycle numbers are the ones written by the tester (LAND numbers them from 1)
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field

import numpy as np

CHARGE, DISCHARGE, REST = "charge", "discharge", "rest"

# Mode labels that tell the step direction without looking at the current.
_MODE_KIND = {
    "cc_chg": CHARGE, "cv_chg": CHARGE, "cccv_chg": CHARGE, "cp_chg": CHARGE, "cr_chg": CHARGE,
    "cc_dchg": DISCHARGE, "cv_dchg": DISCHARGE, "cccv_dchg": DISCHARGE, "cp_dchg": DISCHARGE,
    "cr_dchg": DISCHARGE, "rest": REST,
}
_ZH_CHARGE = ("充电", "充")
_ZH_DISCHARGE = ("放电", "放")
_ZH_REST = ("静置", "搁置", "休眠")


@dataclass
class Step:
    number: int          # 1-based logical step index within the file
    cycle: int           # cycle number as written by the tester
    kind: str            # CHARGE / DISCHARGE / REST
    mode: str            # raw mode label (for display only)
    start: int           # first point index
    stop: int            # one past the last point index
    t_start: float
    t_end: float
    V_start: float
    V_end: float
    I_mean_mA: float
    capacity_mAh: float
    energy_mWh: float

    @property
    def duration_s(self) -> float:
        return self.t_end - self.t_start

    @property
    def n_points(self) -> int:
        return self.stop - self.start


@dataclass
class CellData:
    path: str
    source: str                      # e.g. "LAND .cex", "Excel export"
    t: np.ndarray
    V: np.ndarray
    I: np.ndarray
    Q: np.ndarray
    E: np.ndarray
    steps: list
    start_time: _dt.datetime | None = None
    warnings: list = field(default_factory=list)
    info: dict = field(default_factory=dict)

    @property
    def n_points(self) -> int:
        return int(len(self.t))

    @property
    def cycles(self) -> list:
        return sorted({s.cycle for s in self.steps if s.kind != REST})

    @property
    def duration_h(self) -> float:
        return float(self.t[-1] - self.t[0]) / 3600 if self.n_points else 0.0


def kind_from_mode(mode: str | None) -> str | None:
    """Direction implied by a mode label, or None if the label is not conclusive."""
    if not mode:
        return None
    m = str(mode).strip()
    k = _MODE_KIND.get(m.lower().replace(" ", "_").replace("-", "_"))
    if k:
        return k
    if any(z in m for z in _ZH_REST):
        return REST
    if "放电" in m:
        return DISCHARGE
    if "充电" in m:
        return CHARGE
    ml = m.lower()
    if "rest" in ml or "pause" in ml or ml == "ocv":
        return REST
    if "dchg" in ml or "discharge" in ml:
        return DISCHARGE
    if "chg" in ml or "charge" in ml:
        return CHARGE
    return None


def kind_from_current(I_mA: np.ndarray, scale_mA: float) -> str:
    """Direction from the median current of a step (positive = charge)."""
    if len(I_mA) == 0:
        return REST
    med = float(np.median(I_mA))
    thr = max(1e-6, 1e-3 * scale_mA)
    if abs(med) <= thr:
        return REST
    return CHARGE if med > 0 else DISCHARGE


def _integrate(y: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Cumulative trapezoid integral of y dt / 3600 (mA -> mAh, mW -> mWh), starting at 0."""
    if len(y) < 2:
        return np.zeros(len(y))
    inc = 0.5 * (y[1:] + y[:-1]) * np.diff(t) / 3600.0
    return np.r_[0.0, np.cumsum(inc)]


def assemble(path, source, t, V, I, Q, E, run_id, cycle_of_run, mode_of_run,
             start_time=None, warnings=None, info=None) -> CellData:
    """Build a CellData from per-point arrays.

    run_id        per-point integer id of the step the point belongs to; a new
                  Step starts wherever run_id changes.
    cycle_of_run  mapping run_id -> cycle number
    mode_of_run   mapping run_id -> raw mode label (may be None)
    Q, E          per-step accumulated capacity / energy (any sign), or None
                  to integrate them from the current.
    """
    warnings = list(warnings or [])
    t = np.asarray(t, dtype=np.float64)
    V = np.asarray(V)
    I = np.asarray(I)
    run_id = np.asarray(run_id)
    n = len(t)
    if n == 0:
        raise ValueError("文件里没有数据点")
    Q = np.abs(np.asarray(Q)) if Q is not None else None
    E = np.abs(np.asarray(E)) if E is not None else None
    bnd = np.flatnonzero(np.r_[True, run_id[1:] != run_id[:-1], True])
    scale = float(np.nanmax(np.abs(I))) if n else 0.0
    Qout = np.zeros(n) if Q is None else Q
    Eout = np.zeros(n) if E is None else E
    steps = []
    for k, (a, b) in enumerate(zip(bnd[:-1], bnd[1:])):
        rid = run_id[a]
        mode = mode_of_run.get(rid) if hasattr(mode_of_run, "get") else None
        kind = kind_from_mode(mode)
        kind_I = kind_from_current(I[a:b], scale)
        if kind is None:
            kind = kind_I
        elif kind != kind_I and kind_I != REST and kind != REST:
            warnings.append(f"工步 {k + 1}（{mode}）的电流方向与工步类型不一致，按工步类型处理")
        if Q is None or not np.isfinite(Qout[a:b]).all():
            Qout[a:b] = np.abs(_integrate(np.abs(I[a:b]), t[a:b]))
        if E is None or not np.isfinite(Eout[a:b]).all():
            Eout[a:b] = np.abs(_integrate(np.abs(V[a:b] * I[a:b]), t[a:b]))
        if kind == REST:
            cap, en = 0.0, 0.0
        else:
            cap, en = float(Qout[b - 1]), float(Eout[b - 1])
        steps.append(Step(number=k + 1, cycle=int(cycle_of_run.get(rid, 1)), kind=kind,
                          mode=str(mode) if mode else kind, start=int(a), stop=int(b),
                          t_start=float(t[a]), t_end=float(t[b - 1]), V_start=float(V[a]),
                          V_end=float(V[b - 1]), I_mean_mA=float(np.mean(I[a:b], dtype=np.float64)),
                          capacity_mAh=cap, energy_mWh=en))
    t0 = t[0]
    # float32 is what LAND stores; it halves memory for 10 large files (time stays float64)
    f32 = np.float32
    return CellData(path=str(path), source=source, t=t - t0, V=V.astype(f32, copy=False),
                    I=I.astype(f32, copy=False), Q=Qout.astype(f32, copy=False), E=Eout.astype(f32, copy=False),
                    steps=steps, start_time=start_time, warnings=warnings, info=dict(info or {}))
