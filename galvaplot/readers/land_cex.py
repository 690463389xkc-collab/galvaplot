"""Reader for LAND (蓝电) native ``.cex`` files.

LAND does not publish the .cex format. This reader was reverse-engineered
from 140+ files written by LAND testers and checked for internal
consistency (capacity == ∫|I|dt, energy == ∫V|I|dt, set current == measured
current, current sign matches the step type). It has NOT been compared point
by point with an official LANDdt export, and only rest / constant-current
charge / constant-current discharge steps were present in the reference
files. Steps with other modes (CV, CCCV, pulse, ...) are classified by the
sign of their current and reported in ``CellData.warnings``.

Layout (little-endian, 16-byte aligned)
  0x00-0x3F  header, magic ``10 11 09 88``; +0x1C f32 active-material mass (g) as
             entered in LAND, 0 if none was entered (checked on 143 files: in every
             file with a mass, the programmed step current / mass is exactly the
             specific current of the test plan, 100 or 500 mA/g; the trailer block
             repeats the value)
  blocks     ``aa aa ff ff <tag u16> <len u16>`` ... ``bb bb ff ff`` + same 4 bytes
             (tag 0x15 = step program, tag 0xcc = trailer with cell name)
  records    32 bytes, magic ``cX cc ff ff``
    c3 / c4  data point: +0x08 u64 test time (ms), +0x10 f32 voltage (V),
             +0x14 f32 current (A, + = charge), +0x18 f32 step capacity (Ah),
             +0x1c f32 step energy (Wh)
    c2       step start: +0x04 u8 kind (0x22 new step, 0x25 resume after a
             program edit), +0x08 u32 unix start time (tester PC clock),
             +0x10 u8 mode (0x70 rest, 0x02 CC discharge, 0x03 CC charge),
             +0x14 u16 cycle index (0-based), +0x16 u8 step number in the
             program, +0x1c f32 set current (A)
    c1       events (not decoded)
"""
from __future__ import annotations

import datetime as _dt
import mmap
import os
import struct

import numpy as np

from ..model import assemble

MAGIC = b"\x10\x11\x09\x88"
MODE_NAMES = {0x70: "Rest", 0x02: "CC_DChg", 0x03: "CC_Chg"}
REC = np.dtype([("magic", "<u4"), ("pad", "<u4"), ("t_ms", "<u8"),
                ("V", "<f4"), ("I", "<f4"), ("Q", "<f4"), ("E", "<f4")])


class CexFormatError(ValueError):
    pass


def _run_end(b: bytes, o: int) -> int:
    """End offset of the contiguous run of 32-byte ``cX cc ff ff`` records starting at o."""
    n = (len(b) - o) // 32
    if n <= 0:
        return o
    arr = np.frombuffer(b, dtype=np.uint8, count=n * 32, offset=o).reshape(n, 32)
    ok = (arr[:, 1] == 0xCC) & (arr[:, 2] == 0xFF) & (arr[:, 3] == 0xFF)
    k = n if ok.all() else int(np.argmin(ok))
    return o + 32 * k


FIELDS = ("t", "V", "I", "Q", "E")


def parse_cex_bytes(b) -> dict:
    """Low-level parse of a bytes-like object (bytes or mmap).

    Returns dict(fields, steps, events, meta, warnings); `fields` holds the data
    points as separate columns: t (s, float64), V (V), I (mA), Q (mAh), E (mWh)
    (float32, as stored by LAND). Columns are extracted chunk by chunk so that
    no full copy of the 32-byte records is kept.
    """
    if b[:4] != MAGIC:
        raise CexFormatError(
            f"文件头不是已知的蓝电 .cex 格式（magic = {b[:4].hex()}）。"
            "可以在蓝电数据软件里把数据导出为 Excel 再拖进来。")
    o, n = 0x40, len(b)
    cols = {k: [] for k in FIELDS}
    steps, events, blocks, warnings = [], [], [], []
    n_data = 0
    while o + 16 <= n:
        h = b[o:o + 4]
        if h == b"\xaa\xaa\xff\xff":
            key = b[o + 4:o + 8]
            e = b.find(b"\xbb\xbb\xff\xff" + key, o + 16)
            if e < 0 or e % 16:
                warnings.append(f"文件末尾有未结束的数据块（偏移 {o:#x}），可能是测试仍在进行")
                break
            blocks.append((struct.unpack_from("<H", b, o + 4)[0], o, e + 32))
            o = e + 32
        elif h[1:] == b"\xcc\xff\xff":
            end = _run_end(b, o)
            if end == o:
                break
            recs = np.frombuffer(b, dtype=REC, count=(end - o) // 32, offset=o)
            typ = (recs["magic"] & 0xFF).astype(np.uint8)
            isdata = (typ == 0xC3) | (typ == 0xC4)
            ctrl = np.flatnonzero(~isdata)
            if len(ctrl):
                before = np.cumsum(isdata)  # data records up to and including j
                for j in ctrl:
                    ro = o + 32 * int(j)
                    r = b[ro:ro + 32]
                    if r[0] == 0xC2:
                        n_before = int(before[j - 1]) if j > 0 else 0
                        steps.append(dict(
                            kind=r[4], unix_start=struct.unpack_from("<I", r, 8)[0],
                            mode_code=r[16], mode=MODE_NAMES.get(r[16], f"mode_0x{r[16]:02x}"),
                            cycle=struct.unpack_from("<H", r, 20)[0] + 1, step_no=r[22],
                            set_current_A=struct.unpack_from("<f", r, 28)[0],
                            first_data=n_data + n_before))
                    elif r[0] == 0xC1:
                        events.append((ro, r[4]))
                    else:
                        warnings.append(f"未知记录类型 {r[0]:#x}（偏移 {ro:#x}）")
            d = recs if len(ctrl) == 0 else recs[isdata]
            cols["t"].append(d["t_ms"] / 1000.0)
            cols["V"].append(d["V"].copy())
            cols["I"].append(d["I"] * np.float32(1e3))
            cols["Q"].append(d["Q"] * np.float32(1e3))
            cols["E"].append(d["E"] * np.float32(1e3))
            n_data += len(d)
            del d, recs, typ, isdata
            o = end
        else:
            # trailing partial record of a file that is still being written, or padding
            if any(b[o:o + 16]):
                warnings.append(f"偏移 {o:#x} 处有无法识别的 16 字节，已跳过")
            o += 16
    fields = {k: (np.concatenate(v) if v else np.zeros(0, np.float64 if k == "t" else np.float32))
              for k, v in cols.items()}
    cols.clear()
    meta = {"file_size": n, "blocks": blocks, "mass_g": struct.unpack_from("<f", b, 0x1C)[0]}
    trailer = [bl for bl in blocks if bl[0] == 0xCC]
    if trailer:
        tb = bytes(b[trailer[-1][1]:trailer[-1][2]])
        meta["trailer_strings"] = [s.decode("gbk", "replace") for s in tb.split(b"\x00")
                                   if len(s) >= 3 and all(32 <= c < 127 for c in s)]
    return dict(fields=fields, steps=steps, events=events, meta=meta, warnings=warnings)


def _parse_file(path):
    """Parse through a read-only memory map (file pages stay in the OS cache instead of
    a private copy); fall back to reading the whole file if mapping is not possible."""
    size = os.path.getsize(path)
    if size < 0x40 + 16:
        raise CexFormatError("文件太小，不是完整的蓝电 .cex 文件")
    with open(path, "rb") as f:
        try:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        except (OSError, ValueError):
            return parse_cex_bytes(f.read())
    try:
        return parse_cex_bytes(mm)
    finally:
        try:
            mm.close()
        except BufferError:      # a view is still referenced (e.g. by a traceback); GC will release it
            pass


def read_cex(path: str):
    p = _parse_file(path)
    fld, steps, warnings = p["fields"], p["steps"], list(p["warnings"])
    N = len(fld["t"])
    if N == 0:
        raise CexFormatError("文件里没有数据点（测试可能还没开始记录）")
    if not steps:
        raise CexFormatError("没有找到工步记录，无法划分充放电")

    # Logical steps: a 'resume' record (kind 0x25, written after the program was
    # edited during the test) continues the previous step if the mode is unchanged.
    run_of_step, info, sid = [], [], -1
    for s in steps:
        if s["kind"] != 0x25 or sid < 0 or s["mode"] != info[-1]["mode"]:
            sid += 1
            info.append(s)
        run_of_step.append(sid)
    run_id = np.full(N, -1, dtype=np.int64)
    for k, s in enumerate(steps):
        a = s["first_data"]
        b_ = steps[k + 1]["first_data"] if k + 1 < len(steps) else N
        run_id[a:b_] = run_of_step[k]
    keep = run_id >= 0
    if not keep.all():
        warnings.append(f"{int((~keep).sum())} 个数据点出现在第一个工步之前，已忽略")
        fld = {k: v[keep] for k, v in fld.items()}
        run_id = run_id[keep]
    unknown = sorted({s["mode"] for s in info if s["mode_code"] not in MODE_NAMES})
    if unknown:
        warnings.append("包含未解码的工步类型 " + ", ".join(unknown) +
                        "，已按电流方向判断充电/放电/静置；结果请与蓝电软件核对")
    cycle_of_run = {k: s["cycle"] for k, s in enumerate(info)}
    mode_of_run = {k: (s["mode"] if s["mode_code"] in MODE_NAMES else None) for k, s in enumerate(info)}
    start = None
    try:
        start = _dt.datetime.fromtimestamp(steps[0]["unix_start"])
    except (OverflowError, OSError, ValueError):
        pass
    names = p["meta"].get("trailer_strings", [])
    info = {"cell_name": names[0] if names else os.path.splitext(os.path.basename(path))[0],
            "file_size": p["meta"]["file_size"]}
    mass_g = p["meta"].get("mass_g") or 0.0
    if np.isfinite(mass_g) and 0 < mass_g < 100:
        info["mass_mg"] = float(f"{mass_g * 1000:.6g}")     # float32 -> the number typed in LAND
    cell = assemble(path, "LAND .cex",
                    t=fld["t"], V=fld["V"], I=fld["I"], Q=fld["Q"], E=fld["E"],
                    run_id=run_id, cycle_of_run=cycle_of_run, mode_of_run=mode_of_run,
                    start_time=start, warnings=warnings, info=info)
    return cell
