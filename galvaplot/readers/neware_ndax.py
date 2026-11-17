"""Reader for Neware (新威) BTS ``.ndax`` files.

Neware does not publish the format. This reader was reverse-engineered from
26 files written by BTS Client 8.0 (ndc file version 17) and checked for
internal consistency: recorded capacity == ∫|I|dt (median ratio 1.000000 over
331 charge/discharge steps), energy == ∫V|I|dt (median 0.9999–1.0002, spread
from the 30 s sampling), current sign matches the step type at every point.
It has NOT been compared with an official BTSDA export. Other ndc versions
(older BTS clients) are rejected with a clear message.

Layout
  .ndax = zip archive with XML metadata (TestInfo.xml, Step.xml, ...) and
  binary .ndc files. Every .ndc file: byte 0 = file type, byte 2 = version,
  then 4096-byte pages; page 0 is a file header, each later page has a
  132-byte header (u16 page type, u16 record count, used-slot bitmap) and
  fixed-length records.

  data.ndc          (type 1)  8-byte records: f32 voltage (V), f32 current (A,
                              + = charge); one per data point, in index order
  data_runInfo.ndc  (type 18) 100-byte records, one per data point:
      +0  u32 time in step (ms)          +5  f32 charge capacity (Ah)
      +9  f32 discharge capacity (Ah)    +13 f32 charge energy (Wh)
      +17 f32 discharge energy (Wh)      +21 f32 current range (A)
      +33 u32 unix time (s)              +37 u32 step (1-based row of data_step)
      +41 u32 data-point index (1-based; index 1 is written twice)
      +47 f32 / +51 f32 running net capacity (Ah) / energy (Wh)
  data_step.ndc     (type 7)  100-byte records, one per executed step:
      +0  u32 loop counter (0-based)     +4  u32 step ID in the program
      +24 u8  step type (1 CC charge, 2 CC discharge, 4 rest; 5/6 are the
              program's cycle/end control steps and do not appear)
      +25 i64 test time at step start (ms)
      +33 u32 index of the first data point of the step

Cycle numbering: the program's loop start step (from the step table, or from
Step.xml if the loop has not repeated yet) starts a new cycle; steps before
the loop with charge/discharge form cycle 1 (e.g. a first discharge), as in
LAND files. Rest-only segments join the following cycle.
"""
from __future__ import annotations

import datetime as _dt
import re
import struct
import zipfile
import xml.etree.ElementTree as ET

import numpy as np

from ..model import assemble

PAGE, PAGE_HDR = 4096, 132
SUPPORTED_VERSION = 17
TYPE_NAMES = {1: "CC_Chg", 2: "CC_DChg", 4: "Rest"}       # verified on real files
CONTROL_TYPES = {5, 6}                                    # cycle / end (program only)

RUN17 = np.dtype([("tstep_ms", "<u4"), ("_b4", "u1"), ("qc", "<f4"), ("qd", "<f4"), ("ec", "<f4"),
                  ("ed", "<f4"), ("range_A", "<f4"), ("_b25", "u1"), ("_r26", "V3"), ("_d29", "<u4"),
                  ("unix", "<u4"), ("step", "<u4"), ("idx", "<u4"), ("_s45", "<u2"), ("qnet", "<f4"),
                  ("enet", "<f4"), ("_b55", "u1"), ("_tail", "V44")])
STEP17 = np.dtype([("loop", "<u4"), ("sid", "<u4"), ("_r8", "V16"), ("type", "u1"), ("t0_ms", "<i8"),
                   ("idx0", "<u4"), ("_tail", "V63")])
assert RUN17.itemsize == 100 and STEP17.itemsize == 100


class NdaxFormatError(ValueError):
    pass


def _records(buf: bytes, rec_len: int, ftype: int, name: str) -> np.ndarray:
    if len(buf) < PAGE:
        raise NdaxFormatError(f"{name} 太短，文件可能不完整")
    if buf[0] != ftype or buf[2] != SUPPORTED_VERSION:
        raise NdaxFormatError(
            f"{name} 的版本是 v{buf[2]}（类型 {buf[0]}），目前只支持新威 BTS 8.x 写出的 v{SUPPORTED_VERSION}。"
            "可以在 BTSDA 里导出 Excel 再拖进来，或到 GitHub 提交 issue 附上文件。")
    chunks = []
    cap = (PAGE - PAGE_HDR) // rec_len
    for p in range(1, len(buf) // PAGE):
        o = p * PAGE
        n = struct.unpack_from("<H", buf, o + 2)[0]
        if n == 0:
            continue
        if n > cap:
            raise NdaxFormatError(f"{name} 第 {p} 页记录数 {n} 超出页容量，文件格式与预期不同")
        chunks.append(np.frombuffer(buf, np.uint8, count=n * rec_len, offset=o + PAGE_HDR))
    if not chunks:
        return np.zeros((0, rec_len), np.uint8)
    return np.concatenate(chunks).reshape(-1, rec_len)


def _xml(z: zipfile.ZipFile, name: str):
    """Parse an XML member. Neware declares GB2312 for some files, which the
    expat parser cannot decode itself: decode in Python, drop the declaration."""
    try:
        raw = z.read(name)
    except KeyError:
        return None
    try:
        return ET.fromstring(raw)
    except (ET.ParseError, ValueError, LookupError):
        pass
    for enc in ("utf-8", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        return None
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text)
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        return None


def _xml_loop_starts(z: zipfile.ZipFile) -> set:
    root = _xml(z, "Step.xml")
    out = set()
    if root is None:
        return out
    for el in root.iter():
        if el.get("Step_Type") == "5":
            st = el.find(".//Start_Step")
            if st is not None and (st.get("Value") or "").isdigit():
                out.add(int(st.get("Value")))
    return out


def _start_time(z: zipfile.ZipFile):
    root = _xml(z, "TestInfo.xml")
    if root is None:
        return None
    ti = root.find(".//TestInfo")
    s = ti.get("StartTime") if ti is not None else None
    if s:
        try:
            return _dt.datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    return None


def cycles_from_steps(loop, sid, types, xml_starts=()) -> list:
    """Cycle number (1-based) of each executed step; see module docstring."""
    n = len(sid)
    starts = {int(sid[k]) for k in range(1, n) if loop[k] != loop[k - 1]}
    if not starts:
        starts = set(int(x) for x in xml_starts)
    seg, segs = 0, []
    for k in range(n):
        if k > 0 and (int(sid[k]) in starts or loop[k] != loop[k - 1]):
            seg += 1
        segs.append(seg)
    active_segs = sorted({s for s, t in zip(segs, types) if int(t) not in (4, *CONTROL_TYPES)})
    if not active_segs:
        return [1] * n
    number = {s: i + 1 for i, s in enumerate(active_segs)}
    out = []
    for s in segs:
        nxt = [a for a in active_segs if a >= s]       # rest-only segment joins the next cycle
        out.append(number[nxt[0]] if nxt else number[active_segs[-1]])
    return out


def read_ndax(path: str):
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise NdaxFormatError("这不是新威 .ndax 文件（不是 zip 包）。旧版 .nda 文件暂不支持，可以在 BTSDA 里另存为 .ndax 或导出 Excel。")
    with z:
        names = set(z.namelist())
        need = {"data.ndc", "data_runInfo.ndc", "data_step.ndc"}
        if not need <= names:
            raise NdaxFormatError("压缩包里缺少 " + "、".join(sorted(need - names)) + "，不是本程序支持的 .ndax 版本")
        D = _records(z.read("data.ndc"), 8, 1, "data.ndc").view("<f4").reshape(-1, 2)
        R = _records(z.read("data_runInfo.ndc"), 100, 18, "data_runInfo.ndc").copy().view(RUN17).ravel()
        S = _records(z.read("data_step.ndc"), 100, 7, "data_step.ndc").copy().view(STEP17).ravel()
        xml_starts = _xml_loop_starts(z)
        start = _start_time(z)
    warnings = []
    N = len(D)
    if N == 0 or len(R) == 0 or len(S) == 0:
        raise NdaxFormatError("文件里没有数据点（测试可能还没开始记录）")

    # one runInfo record per data point; index 1 is written twice -> keep the last record per index
    order = np.argsort(R["idx"], kind="stable")
    R = R[order]
    R = R[np.r_[R["idx"][1:] != R["idx"][:-1], True]]
    idx = R["idx"].astype(np.int64)
    ok = (idx >= 1) & (idx <= N)
    if not ok.all() or len(R) != N:
        warnings.append(f"数据点与运行信息条数不一致（{N} / {len(R)}），只保留两者都有的点")
    R = R[ok]
    rows = idx[ok] - 1
    V = D[rows, 0]
    I = D[rows, 1] * np.float32(1e3)

    step = R["step"].astype(np.int64)
    bad = (step < 1) | (step > len(S))
    if bad.any():
        warnings.append(f"{int(bad.sum())} 个数据点的工步号超出工步表，已忽略")
        keep = ~bad
        R, V, I, step = R[keep], V[keep], I[keep], step[keep]
    t_ms = S["t0_ms"][step - 1] + R["tstep_ms"].astype(np.int64)
    if (np.diff(t_ms) < 0).any():
        warnings.append("时间不是单调递增，已按记录顺序处理")

    types = S["type"].astype(int)
    unknown = sorted({t for t in types if t not in TYPE_NAMES})
    if unknown:
        warnings.append("包含未验证的工步类型 " + ", ".join(f"type {t}" for t in unknown) +
                        "，已按电流方向判断充电/放电/静置；结果请与 BTSDA 核对")
    cyc = cycles_from_steps(S["loop"], S["sid"], types, xml_starts)
    run_id = step - 1
    cycle_of_run = {k: cyc[k] for k in range(len(S))}
    mode_of_run = {k: TYPE_NAMES.get(int(types[k])) for k in range(len(S))}

    Q = (R["qc"] + R["qd"]) * np.float32(1e3)
    E = (R["ec"] + R["ed"]) * np.float32(1e3)
    return assemble(path, "Neware .ndax", t=t_ms / 1000.0, V=V, I=I, Q=Q, E=E, run_id=run_id,
                    cycle_of_run=cycle_of_run, mode_of_run=mode_of_run, start_time=start,
                    warnings=warnings, info={"ndc_version": SUPPORTED_VERSION, "n_steps": len(S)})
