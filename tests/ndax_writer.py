"""Minimal writer for the .ndax layout read by galvaplot.readers.neware_ndax (tests only).

steps: list of dict(type=1|2|4|..., sid=int, loop=int, t=array_s_within_step, V=array, I=array_A)
"""
import struct
import zipfile

import numpy as np

PAGE, HDR = 4096, 132


def _ndc(ftype, page_type, rec_len, records: bytes, version=17):
    head = bytearray(PAGE)
    head[0], head[2], head[4], head[12] = ftype, version, 1, 8
    out = bytearray(head)
    cap = (PAGE - HDR) // rec_len
    n_total = len(records) // rec_len
    for a in range(0, n_total, cap):
        n = min(cap, n_total - a)
        pg = bytearray(PAGE)
        struct.pack_into("<HH", pg, 0, page_type, n)
        bits = np.zeros(((n + 7) // 8) * 8, np.uint8)
        bits[:n] = 1
        bm = np.packbits(bits, bitorder="little").tobytes()
        pg[4:4 + len(bm)] = bm
        pg[HDR:HDR + n * rec_len] = records[a * rec_len:(a + n) * rec_len]
        out += pg
    return bytes(out)


def write_ndax(path, steps, start="2026-08-16 17:41:17", loop_starts=(), version=17, step_xml=True,
               unix0=1786873277, scq=None):
    """scq: active mass as BTS stores it in Step.xml <Head_Info><SCQ> (micrograms)."""
    data, run, step = bytearray(), bytearray(), bytearray()
    idx, t0_ms = 1, 0
    first = True
    for k, s in enumerate(steps):
        t_ms = np.round(np.asarray(s["t"], float) * 1000).astype(np.int64)
        V = np.asarray(s["V"], np.float32)
        I = np.asarray(s["I"], np.float32)
        q = np.r_[0, np.cumsum(0.5 * (np.abs(I[1:]) + np.abs(I[:-1])) * np.diff(t_ms) / 1000 / 3600)]
        e = np.r_[0, np.cumsum(0.5 * (np.abs(I[1:] * V[1:]) + np.abs(I[:-1] * V[:-1])) * np.diff(t_ms) / 1000 / 3600)]
        rec = bytearray(100)
        struct.pack_into("<II", rec, 0, s["loop"], s["sid"])
        rec[24] = s["type"]
        struct.pack_into("<qI", rec, 25, t0_ms, idx)
        step += rec
        for j in range(len(t_ms)):
            data += struct.pack("<ff", V[j], I[j])
            chg = s["type"] == 1 or (s["type"] not in (1, 2, 4) and I[j] > 0)
            dchg = s["type"] == 2 or (s["type"] not in (1, 2, 4) and I[j] < 0)
            r = bytearray(100)
            struct.pack_into("<I", r, 0, int(t_ms[j]))
            struct.pack_into("<ffff", r, 5, q[j] if chg else 0, q[j] if dchg else 0, e[j] if chg else 0, e[j] if dchg else 0)
            struct.pack_into("<IIII", r, 29, 0, unix0 + int((t0_ms + t_ms[j]) // 1000), k + 1, idx)
            if first:          # the real files write data point 1 twice
                run += r
                first = False
            run += r
            idx += 1
        t0_ms += int(t_ms[-1])
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("data.ndc", _ndc(1, 2, 8, bytes(data), version))
        z.writestr("data_runInfo.ndc", _ndc(18, 19, 100, bytes(run), version))
        z.writestr("data_step.ndc", _ndc(7, 8, 100, bytes(step), version))
        ti = (f'<?xml version="1.0" encoding="GB2312"?>\n<root><config type="Test Info File">'
              f'<TestInfo StartTime="{start}" StepName="测试程序.xml" /></config></root>')
        z.writestr("TestInfo.xml", ti.encode("gb18030"))
        if step_xml:
            body = "".join(f'<Step{n} Step_ID="{n}" Step_Type="5"><Limit><Other><Start_Step Value="{ls}" />'
                           f'<Cycle_Count Value="10" /></Other></Limit></Step{n}>' for n, ls in enumerate(loop_starts, 90))
            head = ('<Head_Info><Operate Value="65" /><Scale Value="1" /><RateType Value="102" />'
                    + (f'<SCQ Value="{scq}" /><SCQ_F Value="{scq * 1e-8:.3G}" />' if scq else "")
                    + '</Head_Info>')
            z.writestr("Step.xml", f'<?xml version="1.0" encoding="GB2312"?><root><config>{head}<Step_Info>{body}'
                                   f'</Step_Info></config></root>'.encode("gb18030"))
        z.writestr("VersionInfo.xml", '<?xml version="1.0" encoding="utf-8"?><root/>')


def cc_step(kind, sid, loop, hours, i_mA, v0, v1, n=60):
    """Constant-current (or rest) step with a linear voltage ramp."""
    t = np.linspace(0, hours * 3600, n)
    I = np.full(n, {"chg": 1, "dchg": -1, "rest": 0}[kind] * i_mA / 1000)
    typ = {"chg": 1, "dchg": 2, "rest": 4}[kind]
    return dict(type=typ, sid=sid, loop=loop, t=t, V=np.linspace(v0, v1, n), I=I)
