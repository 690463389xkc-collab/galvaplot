"""Experimental reader for tables exported by tester software (Excel / CSV / TXT).

The record (per-point) sheet is located by its column headers. Chinese and
English headers are recognised by keyword, units are taken from the header
text (V/mV, A/mA/μA, Ah/mAh/μAh, Wh/mWh, s/min/h). Charge and discharge are
told apart by a step-type column when present, otherwise by the sign of the
current. Large record tables split over several sheets with the same header
are joined in workbook order.
"""
from __future__ import annotations

import csv
import datetime as _dt
import io
import os
import re

import numpy as np

from ..model import CHARGE, DISCHARGE, REST, assemble, kind_from_mode

# ---------------------------------------------------------------- header matching
_EXCL_STAT = re.compile(r"起始|终止|中值|平均|开始|结束|截止|最大|最小|start|end|mid|median|avg|mean|max|min|init|final", re.I)
_EXCL_SPEC = re.compile(r"比|面|spe|/\s*g|\bg\b|cm|areal|specific|per", re.I)
FIELDS = {
    "voltage": (re.compile(r"电压|voltage|volt|^\s*v\s*([/(\[]|$)", re.I), [_EXCL_STAT]),
    "current": (re.compile(r"电流|current|^\s*i\s*([/(\[]|$)", re.I), [_EXCL_STAT, _EXCL_SPEC]),
    "chg_cap": (re.compile(r"充电容量|chg\.?\s*cap|charge\s*cap", re.I), [_EXCL_SPEC]),
    "dchg_cap": (re.compile(r"放电容量|dchg\.?\s*cap|dis\.?\s*cap|discharge\s*cap", re.I), [_EXCL_SPEC]),
    "capacity": (re.compile(r"容量|capacity|^\s*cap\b|^\s*q\s*([/(\[]|$)", re.I), [_EXCL_SPEC, _EXCL_STAT, re.compile(r"充电|放电|chg|charge|discharge|retention|保持", re.I)]),
    "energy": (re.compile(r"能量|energy", re.I), [_EXCL_SPEC, _EXCL_STAT, re.compile(r"充电|放电|chg|charge|discharge", re.I)]),
    "test_time": (re.compile(r"测试时间|总时间|累计时间|运行时间|test\s*_?time|total\s*time|^\s*time\b|^\s*时间", re.I), [re.compile(r"步|step|系统|绝对|sys|date|日期", re.I)]),
    "step_time": (re.compile(r"步骤时间|工步时间|step\s*_?time", re.I), []),
    "abs_time": (re.compile(r"系统时间|绝对时间|实际时间|real\s*time|sys\s*_?time|date\s*time|^\s*date|日期", re.I), []),
    "cycle": (re.compile(r"循环|cycle", re.I), [re.compile(r"寿命|life|time|时间|容量|cap", re.I)]),
    "step": (re.compile(r"工步号|工步序号|^\s*工步\s*$|^\s*step\s*$|step\s*_?(no|index|id|number|#)", re.I), []),
    "state": (re.compile(r"工步类型|工步状态|工作状态|状态|模式|step\s*_?type|^\s*mode|^\s*state|status", re.I), []),
}


def _match_header(names):
    """Map field -> column index for a header row (first match wins)."""
    out = {}
    for f, (pat, excl) in FIELDS.items():
        for j, h in enumerate(names):
            if not h or j in out.values():
                continue
            if pat.search(h) and not any(e.search(h) for e in excl):
                out[f] = j
                break
    return out


def _score(m):
    return (("voltage" in m) * 3 + ("current" in m) * 2 + bool({"test_time", "abs_time", "step_time"} & m.keys()) * 2
            + bool({"capacity", "chg_cap", "dchg_cap"} & m.keys()) + ("cycle" in m) + ("step" in m))


def _unit(h: str, kind: str) -> float:
    s = h.lower().replace("µ", "μ")
    unit = ""
    mm = re.search(r"[/(\[（]\s*([a-zμ]+)", s)
    if mm:
        unit = mm.group(1)
    else:
        mm = re.search(r"([a-zμ]+)\s*$", s)
        unit = mm.group(1) if mm else ""
    if kind == "voltage":
        return 1e-3 if unit == "mv" else 1.0
    if kind == "current":
        return {"a": 1e3, "ma": 1.0, "μa": 1e-3, "ua": 1e-3, "na": 1e-6}.get(unit, 1.0)
    if kind == "capacity":
        return {"ah": 1e3, "mah": 1.0, "μah": 1e-3, "uah": 1e-3}.get(unit, 1.0)
    if kind == "energy":
        return {"wh": 1e3, "mwh": 1.0, "μwh": 1e-3, "uwh": 1e-3}.get(unit, 1.0)
    if kind == "time":
        return {"h": 3600.0, "hr": 3600.0, "hour": 3600.0, "min": 60.0, "ms": 1e-3, "s": 1.0, "sec": 1.0}.get(unit, 1.0)
    return 1.0


# ---------------------------------------------------------------- value parsing
_DUR = re.compile(r"^\s*(?:(\d+)\s*(?:d|day|days|天|-)\s*)?(\d+):(\d{1,2}):(\d{1,2}(?:\.\d*)?)\s*$", re.I)
_MS = re.compile(r"^\s*(\d+):(\d{1,2}(?:\.\d*)?)\s*$")


def _num(x):
    if x is None:
        return np.nan
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    try:
        return float(str(x).strip().replace(",", ""))
    except ValueError:
        return np.nan


def _to_seconds(vals, factor):
    """Durations/timestamps -> seconds. Returns (array, is_absolute)."""
    out = np.full(len(vals), np.nan)
    absolute = False
    first_abs = None
    for i, v in enumerate(vals):
        if v is None:
            continue
        if isinstance(v, _dt.datetime):
            absolute = True
            first_abs = first_abs or v
            out[i] = (v - first_abs).total_seconds()
        elif isinstance(v, _dt.timedelta):
            out[i] = v.total_seconds()
        elif isinstance(v, _dt.time):
            out[i] = v.hour * 3600 + v.minute * 60 + v.second + v.microsecond / 1e6
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[i] = float(v) * factor
        else:
            s = str(v).strip()
            m = _DUR.match(s)
            if m:
                d, h, mi, se = m.groups()
                out[i] = int(d or 0) * 86400 + int(h) * 3600 + int(mi) * 60 + float(se)
                continue
            m = _MS.match(s)
            if m:
                out[i] = int(m.group(1)) * 60 + float(m.group(2))
                continue
            try:
                out[i] = float(s.replace(",", "")) * factor
                continue
            except ValueError:
                pass
            try:
                d = _dt.datetime.fromisoformat(s.replace("/", "-"))
                absolute = True
                first_abs = first_abs or d
                out[i] = (d - first_abs).total_seconds()
            except ValueError:
                pass
    return out, absolute


# ---------------------------------------------------------------- table sources
def _rows_xlsx(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            yield ws.title, ws.iter_rows(values_only=True)
    finally:
        wb.close()


def _rows_xls(path):
    import xlrd
    book = xlrd.open_workbook(path, on_demand=True)
    for k in range(book.nsheets):
        sh = book.sheet_by_index(k)

        def gen(sh=sh):
            for r in range(sh.nrows):
                row = []
                for c in sh.row(r):
                    if c.ctype == xlrd.XL_CELL_DATE:
                        try:
                            row.append(xlrd.xldate.xldate_as_datetime(c.value, book.datemode))
                        except Exception:
                            row.append(c.value)
                    else:
                        row.append(c.value)
                yield row
        yield sh.name, gen()


def _rows_csv(path):
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "gb18030", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:20000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        delim = dialect.delimiter
    except csv.Error:
        delim = "\t" if sample.count("\t") > sample.count(",") else ","
    yield os.path.basename(path), csv.reader(io.StringIO(text), delimiter=delim)


def _iter_sheets(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        return _rows_xlsx(path)
    if ext == ".xls":
        return _rows_xls(path)
    return _rows_csv(path)


def _find_record_table(path):
    """Return (header names, mapping, list of data rows) of the best per-point table."""
    best = None
    tables = []
    for title, rows in _iter_sheets(path):
        head, header_idx, buf = None, None, []
        for i, row in enumerate(rows):
            row = list(row) if row is not None else []
            if head is None:
                names = [str(x).strip() if x is not None else "" for x in row]
                m = _match_header(names)
                if _score(m) >= 7 and "voltage" in m and "current" in m:
                    head, header_idx, mapping = names, i, m
                elif i > 40:
                    break
                continue
            buf.append(row)
        if head is not None:
            tables.append((title, head, mapping, buf))
    if not tables:
        raise ValueError("没找到逐点数据表：需要同时有“电压”“电流”和“时间”列。"
                         "请在蓝电软件中导出“记录/数据”表（不是工步表或循环表）。")
    # best table = highest score; then join every table with the same header (split sheets)
    tables.sort(key=lambda x: -_score(x[2]))
    best = tables[0]
    rows = []
    for title, head, mapping, buf in tables:
        if head == best[1]:
            rows.extend(buf)
    return best[1], best[2], rows


def read_table(path: str):
    head, m, rows = _find_record_table(path)
    warnings = ["表格导入是实验功能：请抽查几个循环的容量是否与蓝电软件一致"]

    def col(f):
        j = m[f]
        return [r[j] if j < len(r) else None for r in rows]

    V = np.array([_num(x) for x in col("voltage")]) * _unit(head[m["voltage"]], "voltage")
    ok = np.isfinite(V)
    if not ok.any():
        raise ValueError("电压列没有可识别的数值")
    rows = [r for r, k in zip(rows, ok) if k]
    V = V[ok]
    I = np.array([_num(x) for x in col("current")]) * _unit(head[m["current"]], "current")
    I = np.nan_to_num(I)

    # time
    t, start = None, None
    for f in ("test_time", "abs_time", "step_time"):
        if f in m:
            tt, absolute = _to_seconds(col(f), _unit(head[m[f]], "time"))
            if np.isfinite(tt).mean() > 0.9:
                if f == "abs_time" and absolute:
                    v0 = next((x for x in col(f) if isinstance(x, _dt.datetime)), None)
                    start = v0
                if f == "step_time":
                    # rebuild a running clock from a per-step clock
                    tt = np.nan_to_num(tt)
                    jump = np.r_[False, np.diff(tt) < 0]
                    offs = np.cumsum(np.where(jump, np.r_[0, tt[:-1]], 0.0))
                    tt = tt + offs
                    warnings.append("文件里没有总测试时间，已由工步时间累加得到")
                t = tt
                break
    if t is None:
        raise ValueError("没找到时间列（测试时间/系统时间/工步时间）")
    good = np.isfinite(t)
    if not good.all():
        rows = [r for r, k in zip(rows, good) if k]
        V, I, t = V[good], I[good], t[good]
    if "abs_time" in m and start is None:
        v0 = next((x for x in col("abs_time") if isinstance(x, _dt.datetime)), None)
        start = v0

    # steps (runs)
    n = len(V)
    keys = []
    if "step" in m:
        keys.append([str(x) for x in col("step")])
    if "cycle" in m:
        cyc_raw = np.array([_num(x) for x in col("cycle")])
        keys.append(list(cyc_raw))
    states = [str(x).strip() if x is not None else "" for x in col("state")] if "state" in m else None
    if states is not None:
        keys.append(states)
    if "step" not in m and states is None:
        scale = float(np.max(np.abs(I))) if n else 0.0
        thr = max(1e-6, 1e-3 * scale)
        sgn = np.where(I > thr, 1, np.where(I < -thr, -1, 0))
        keys.append(list(sgn))
        warnings.append("表格里没有工步列，已按电流正负划分充电/放电/静置")
    change = np.zeros(n, dtype=bool)
    change[0] = True
    for k in keys:
        a = np.array(k, dtype=object)
        change[1:] |= a[1:] != a[:-1]
    run_id = np.cumsum(change) - 1
    starts = np.flatnonzero(change)

    mode_of_run = {}
    if states is not None:
        for r, a in enumerate(starts):
            mode_of_run[r] = states[a] or None

    # capacity / energy within each run
    def per_run(arr):
        out = np.abs(arr.copy())
        ends = np.r_[starts[1:], n]
        for a, b in zip(starts, ends):
            seg = arr[a:b]
            if not np.isfinite(seg).all():
                out[a:b] = np.nan
                continue
            peak = np.max(np.abs(seg)) if len(seg) else 0.0
            if abs(seg[0]) <= 0.05 * peak + 1e-12:
                out[a:b] = np.abs(seg)           # restarts at each step
            else:
                base = arr[a - 1] if a > 0 and np.isfinite(arr[a - 1]) else seg[0]
                out[a:b] = np.abs(seg - base)    # cumulative over the test
        return out

    Q = E = None
    if "capacity" in m:
        Q = np.array([_num(x) for x in col("capacity")]) * _unit(head[m["capacity"]], "capacity")
    elif "chg_cap" in m and "dchg_cap" in m:
        qc = np.nan_to_num(np.array([_num(x) for x in col("chg_cap")])) * _unit(head[m["chg_cap"]], "capacity")
        qd = np.nan_to_num(np.array([_num(x) for x in col("dchg_cap")])) * _unit(head[m["dchg_cap"]], "capacity")
        Q = np.where(I >= 0, qc, qd)
    if Q is not None:
        Q = per_run(Q)
    else:
        warnings.append("表格里没有容量列，容量由电流对时间积分得到")
    if "energy" in m:
        E = per_run(np.array([_num(x) for x in col("energy")]) * _unit(head[m["energy"]], "energy"))

    # cycles
    cycle_of_run = {}
    if "cycle" in m:
        for r, a in enumerate(starts):
            c = cyc_raw[a]
            cycle_of_run[r] = int(c) if np.isfinite(c) else 1
        if min(cycle_of_run.values()) == 0:
            cycle_of_run = {r: c + 1 for r, c in cycle_of_run.items()}
    else:
        # new cycle whenever the first active step type comes back after the other one
        scale = float(np.max(np.abs(I))) if n else 0.0
        from ..model import kind_from_current
        first_kind, seen_other, cyc = None, False, 1
        ends = np.r_[starts[1:], n]
        for r, (a, b) in enumerate(zip(starts, ends)):
            kd = kind_from_mode(mode_of_run.get(r)) or kind_from_current(I[a:b], scale)
            if kd in (CHARGE, DISCHARGE):
                if first_kind is None:
                    first_kind = kd
                elif kd == first_kind and seen_other:
                    cyc += 1
                    seen_other = False
                elif kd != first_kind:
                    seen_other = True
            cycle_of_run[r] = cyc
        warnings.append("表格里没有循环号列，已按充放电交替自动编号，可能与蓝电软件不同")

    src = "Excel 导出" if os.path.splitext(path)[1].lower() in (".xlsx", ".xlsm", ".xls") else "CSV/TXT 导出"
    return assemble(path, src, t=t, V=V, I=I, Q=Q, E=E, run_id=run_id,
                    cycle_of_run=cycle_of_run, mode_of_run=mode_of_run, start_time=start,
                    warnings=warnings, info={"columns": {f: head[j] for f, j in m.items()}})
