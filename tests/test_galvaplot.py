"""Tests: python -m unittest discover -s tests -v   (no real data needed)."""
import csv
import datetime as dt
import os
import shutil
import tempfile
import unittest

import matplotlib

matplotlib.use("Agg")
import numpy as np

from galvaplot import analysis as A
from galvaplot.demo import CexWriter, synth_cell, write_demo
from galvaplot.model import CHARGE, DISCHARGE, REST
from galvaplot.plotting import figures as F
from galvaplot.plotting.export import export_xlsx
from galvaplot.plotting.style import PALETTE
from galvaplot.readers import load_file
from galvaplot.readers.land_cex import CexFormatError
from galvaplot.readers.neware_ndax import NdaxFormatError, cycles_from_steps

try:
    from .ndax_writer import cc_step, write_ndax
except ImportError:          # run as `python -m unittest discover -s tests`
    from ndax_writer import cc_step, write_ndax
from galvaplot.textfmt import default_name, rich, shorten_names


class Tmp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="galvaplot_test_")
        cls.demo = write_demo(cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)


class TestCex(Tmp):
    def test_demo_roundtrip(self):
        c = load_file(self.demo[0])
        self.assertEqual(c.source, "LAND .cex")
        self.assertEqual(c.warnings, [])
        self.assertEqual(c.cycles, list(range(1, 41)))
        self.assertEqual([s.kind for s in c.steps[:3]], [REST, CHARGE, DISCHARGE])
        tab = A.cycle_table(c)
        self.assertEqual(len(tab), 40)
        self.assertAlmostEqual(tab[0]["CE"], 86.0, delta=0.3)          # first-cycle loss built into the demo
        self.assertTrue(all(98.5 < r["CE"] < 100.5 for r in tab[1:]))
        self.assertTrue(tab[-1]["complete"])
        # capacity recorded per step equals ∫|I|dt (constant current)
        s = c.steps[1]
        q_int = abs(s.I_mean_mA) * s.duration_s / 3600
        self.assertAlmostEqual(s.capacity_mAh, q_int, delta=0.01 * q_int)
        # average voltage = energy / capacity, inside the voltage window
        self.assertTrue(3.3 < tab[5]["Vavg_dchg"] < tab[5]["Vavg_chg"] < 4.3)

    def test_bad_magic(self):
        p = os.path.join(self.dir, "bad.cex")
        with open(p, "wb") as f:
            f.write(b"PK\x03\x04" + bytes(200))
        with self.assertRaises(CexFormatError):
            load_file(p)

    def test_icex_and_unknown_ext(self):
        for name in ("x.icex", "x.doc"):
            p = os.path.join(self.dir, name)
            open(p, "wb").close()
            with self.assertRaises(ValueError):
                load_file(p)

    def test_truncated_file_still_reads(self):
        src = self.demo[1]
        with open(src, "rb") as f:
            raw = f.read()
        p = os.path.join(self.dir, "truncated.cex")
        with open(p, "wb") as f:   # cut in the middle of a data record, like a test still running
            f.write(raw[: int(len(raw) * 0.6) // 32 * 32 + 13])
        c = load_file(p)
        self.assertGreater(c.n_points, 1000)
        tab = A.cycle_table(c)
        self.assertFalse(tab[-1]["complete"])       # last cycle is cut short
        self.assertTrue(all(r["complete"] for r in tab[:-1]))

    def test_resume_and_unknown_mode(self):
        w = CexWriter()
        t = np.arange(0, 3600, 60.0)
        q = 0.5 * t / 3600                        # mAh at 0.5 mA
        w.step("charge", 1, 1, 0, 0.0005)
        w.points(t[:30] * 1000, 3.5 + q[:30], np.full(30, 0.0005), q[:30] / 1000, q[:30] * 3.6 / 1000)
        w.step("charge", 1, 1, t[30] * 1000, 0.0005, kind=0x25)   # program edited, same step resumes
        w.points(t[30:] * 1000, 3.5 + q[30:], np.full(30, 0.0005), q[30:] / 1000, q[30:] * 3.6 / 1000)
        w.step(0x05, 1, 2, 3600_000, 0.0)          # unknown mode byte with a negative current
        t2 = 3600 + np.arange(0, 1800, 60.0)
        q2 = 0.5 * (t2 - 3600) / 3600
        w.points(t2 * 1000, 3.9 - q2, np.full(len(t2), -0.0005), q2 / 1000, q2 * 3.7 / 1000)
        w.trailer("resume-test", "C:\\data")
        p = os.path.join(self.dir, "resume.cex")
        w.save(p)
        c = load_file(p)
        self.assertEqual(len(c.steps), 2)          # resume merged into the first step
        self.assertEqual([s.kind for s in c.steps], [CHARGE, DISCHARGE])
        self.assertAlmostEqual(c.steps[0].capacity_mAh, q[-1], places=4)
        self.assertTrue(any("未解码" in x for x in c.warnings))
        tab = A.cycle_table(c)
        self.assertAlmostEqual(tab[0]["CE"], 100 * q2[-1] / q[-1], places=3)

    def test_ce_mode_anode(self):
        c = load_file(self.demo[0])
        a = A.cycle_table(c, "dchg/chg")[3]
        b = A.cycle_table(c, "chg/dchg")[3]
        self.assertAlmostEqual(a["CE"] * b["CE"], 1e4, delta=1e-6)


def _export_rows(cell):
    """Per-point rows of a cell, as a LAND-like export would list them."""
    rows = []
    for s in cell.steps:
        state = {"rest": "静置", "charge": "恒流充电", "discharge": "恒流放电"}[s.kind]
        for i in range(s.start, s.stop):
            rows.append((s.cycle, s.number, state, s.kind, float(cell.t[i]), float(cell.V[i]), float(cell.I[i]),
                         float(cell.Q[i]), float(cell.E[i])))
    return rows


def _hms(sec):
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{s:06.3f}"


class TestTabular(Tmp):
    def setUp(self):
        self.cell = load_file(self.demo[2])
        self.ref = A.cycle_table(self.cell)
        self.rows = _export_rows(self.cell)

    def _compare(self, other, tol):
        tab = A.cycle_table(other)
        self.assertEqual(len(tab), len(self.ref))
        for a, b in zip(self.ref, tab):
            self.assertEqual(a["cycle"], b["cycle"])
            self.assertAlmostEqual(a["dchg_mAh"], b["dchg_mAh"], delta=tol * a["dchg_mAh"])
            self.assertAlmostEqual(a["chg_mAh"], b["chg_mAh"], delta=tol * a["chg_mAh"])

    def test_xlsx_chinese_split_sheets(self):
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "工步层"
        ws.append(["循环号", "工步号", "工步状态", "起始电压/V", "终止电压/V", "容量/mAh"])
        ws.append([1, 1, "静置", 3.0, 3.0, 0])
        head = ["记录序号", "循环号", "工步号", "工步状态", "测试时间", "电压/V", "电流/mA", "容量/mAh",
                "比容量/mAh/g", "能量/mWh", "系统时间"]
        half = len(self.rows) // 2
        t0 = dt.datetime(2026, 11, 1, 9, 0, 0)
        for name, part in (("记录层", self.rows[:half]), ("记录层2", self.rows[half:])):
            ws = wb.create_sheet(name)
            ws.append(["电池信息：示例"])
            ws.append(head)
            for k, r in enumerate(part):
                ws.append([k + 1, r[0], r[1], r[2], _hms(r[4]), r[5], r[6], r[7], r[7] / 0.0125, r[8],
                           t0 + dt.timedelta(seconds=float(r[4]))])
        p = os.path.join(self.dir, "export_zh.xlsx")
        wb.save(p)
        c = load_file(p)
        self.assertEqual(c.n_points, self.cell.n_points)
        self._compare(c, 1e-6)
        self.assertEqual(c.start_time, t0)

    def test_csv_english_units(self):
        p = os.path.join(self.dir, "export_en.csv")
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Record", "Cycle", "Step", "State", "TestTime(h)", "Voltage(V)", "Current(A)",
                        "Capacity(Ah)", "Energy(Wh)"])
            qcum = 0.0   # cumulative capacity over the test (some exporters do this)
            last = None
            for k, r in enumerate(self.rows):
                if last is not None and r[1] != last[0]:
                    qcum += last[1]
                state = {"rest": "Rest", "charge": "CC_Chg", "discharge": "CC_DChg"}[r[3]]
                w.writerow([k + 1, r[0], r[1], state, r[4] / 3600, r[5], r[6] / 1000, (qcum + r[7]) / 1000, r[8] / 1000])
                last = (r[1], r[7])
        c = load_file(p)
        self._compare(c, 1e-5)

    def test_csv_minimal_columns(self):
        p = os.path.join(self.dir, "export_min.csv")
        with open(p, "w", newline="", encoding="gbk") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["时间/s", "电压/V", "电流/mA"])
            for r in self.rows:
                w.writerow([f"{r[4]:.3f}", f"{r[5]:.5f}", f"{r[6]:.5f}"])
        c = load_file(p)
        self._compare(c, 0.01)     # capacity integrated from current: within 1 %
        self.assertTrue(any("循环号" in x for x in c.warnings))

    def test_no_record_table(self):
        p = os.path.join(self.dir, "cycles_only.csv")
        with open(p, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows([["循环", "充电容量/mAh", "放电容量/mAh"], [1, 2, 1.9]])
        with self.assertRaises(ValueError):
            load_file(p)


def _li_cl_program(n_loops):
    """rest, first discharge, rest, then (charge, discharge) x n_loops with loop start = step ID 4."""
    steps = [cc_step("rest", 1, 0, 0.5, 0, 3.2, 3.2), cc_step("dchg", 2, 0, 20, 0.5, 3.5, 2.0),
             cc_step("rest", 3, 0, 1, 0, 3.0, 3.0)]
    for k in range(n_loops):
        steps += [cc_step("chg", 4, k, 5, 1.0, 3.8, 4.0), cc_step("dchg", 5, k, 4.5, 1.0, 3.5, 2.0)]
    return steps


class TestNdax(Tmp):
    def test_roundtrip_and_cycles(self):
        p = os.path.join(self.dir, "Li-Cl-test-1_87-7-3-20260816174117.ndax")
        write_ndax(p, _li_cl_program(3), loop_starts=[4])
        c = load_file(p)
        self.assertEqual(c.source, "Neware .ndax")
        self.assertEqual(c.warnings, [])
        self.assertEqual(c.start_time, dt.datetime(2026, 8, 16, 17, 41, 17))   # GB2312-declared XML
        self.assertEqual(c.n_points, 9 * 60)                                   # duplicate index 1 removed
        self.assertEqual([s.kind for s in c.steps[:4]], [REST, DISCHARGE, REST, CHARGE])
        tab = A.cycle_table(c)
        self.assertEqual([r["cycle"] for r in tab], [1, 2, 3, 4])               # first discharge = cycle 1
        self.assertAlmostEqual(tab[0]["dchg_mAh"], 10.0, places=3)
        self.assertAlmostEqual(tab[1]["chg_mAh"], 5.0, places=3)
        self.assertAlmostEqual(tab[1]["CE"], 90.0, places=2)
        self.assertTrue(np.all(np.diff(c.t) >= 0))
        self.assertEqual(default_name(p), "Li-Cl-test-1")

    def test_cycles_before_first_repeat_use_step_xml(self):
        p = os.path.join(self.dir, "one_pass.ndax")
        write_ndax(p, _li_cl_program(1), loop_starts=[4])
        self.assertEqual([r["cycle"] for r in A.cycle_table(load_file(p))], [1, 2])
        p2 = os.path.join(self.dir, "one_pass_noxml.ndax")
        write_ndax(p2, _li_cl_program(1), step_xml=False)
        self.assertEqual([r["cycle"] for r in A.cycle_table(load_file(p2))], [1])   # no loop info at all

    def test_cycles_rest_only_segment_joins_next(self):
        # symmetric-cell style program: rest, then loop from step 2: (dchg, rest, chg, rest)
        loop = np.array([0, 0, 0, 0, 0, 1, 1, 1, 1])
        sid = np.array([1, 2, 3, 4, 5, 2, 3, 4, 5])
        typ = np.array([4, 2, 4, 1, 4, 2, 4, 1, 4])
        self.assertEqual(cycles_from_steps(loop, sid, typ), [1, 1, 1, 1, 1, 2, 2, 2, 2])

    def test_unknown_step_type_by_current(self):
        steps = [cc_step("chg", 1, 0, 2, 1.0, 3.5, 4.2)]
        steps[0]["type"] = 7                         # e.g. a CCCV charge: not verified on real files
        p = os.path.join(self.dir, "cccv.ndax")
        write_ndax(p, steps)
        c = load_file(p)
        self.assertEqual(c.steps[0].kind, CHARGE)
        self.assertTrue(any("未验证" in w for w in c.warnings))
        self.assertAlmostEqual(c.steps[0].capacity_mAh, 2.0, places=3)

    def test_rejects_other_versions_and_non_zip(self):
        p = os.path.join(self.dir, "v16.ndax")
        write_ndax(p, _li_cl_program(1), version=16)
        with self.assertRaises(NdaxFormatError):
            load_file(p)
        p2 = os.path.join(self.dir, "fake.ndax")
        with open(p2, "wb") as f:
            f.write(b"not a zip" * 100)
        with self.assertRaises(NdaxFormatError):
            load_file(p2)
        p3 = os.path.join(self.dir, "old.nda")
        open(p3, "wb").close()
        with self.assertRaises(ValueError):
            load_file(p3)

    def test_figures_mix_land_and_neware(self):
        p = os.path.join(self.dir, "mix.ndax")
        write_ndax(p, _li_cl_program(4), loop_starts=[4])
        ser = [F.Series(load_file(p), "Neware", PALETTE[0]), F.Series(load_file(self.demo[0]), "LAND", PALETTE[1])]
        for kind in F.BUILDERS:
            r = F.build(kind, ser, {})
            self.assertGreater(len(r.fig.axes), 0)


class TestText(unittest.TestCase):
    def test_default_name(self):
        self.assertEqual(default_name("/a/na-cl-kj-1_006_2.cex"), "na-cl-kj-1")
        self.assertEqual(default_name("/a/plain.cex"), "plain")

    def test_shorten(self):
        n = ["20261101-NCM811-LiPF6-cell1", "20261101-NCM811-LiPF6-cell2", "20261103-NCM811-LiPF6+FEC-cell1"]
        self.assertEqual(shorten_names(n), ["LiPF6-cell1", "LiPF6-cell2", "LiPF6+FEC-cell1"])
        self.assertEqual(shorten_names(["a-1", "a-1"]), ["a-1", "a-1"])   # would collide: unchanged

    def test_rich(self):
        self.assertEqual(rich("AlCl_{3}"), r"AlCl$_{\mathrm{3}}$")
        self.assertEqual(rich("Li^{+}"), r"Li$^{\mathrm{+}}$")
        self.assertEqual(rich("$5 only"), r"\$5 only")
        self.assertEqual(rich("plain_1 name"), "plain_1 name")

    def test_parse_cycles(self):
        self.assertEqual(F.parse_cycles("1, 2，5-7;10"), [1, 2, 5, 6, 7, 10])
        self.assertEqual(F.parse_cycles("abc"), [])


class TestFigures(Tmp):
    def setUp(self):
        cells = [load_file(p) for p in self.demo]
        self.series = [F.Series(c, n, PALETTE[i], "solid" if i % 2 == 0 else "dashed", 12.5 if i else None)
                       for i, (c, n) in enumerate(zip(cells, ["A AlCl_{3}", "B", "C 中文", "D"]))]

    def test_all_kinds_and_exports(self):
        cases = [("profiles", {}), ("profiles", dict(p_arrange="by_cell", p_cycles="1-3, 40", cap_unit="%")),
                 ("profiles", dict(cap_unit="mAh/g")),                         # first series has no mass
                 ("cycling", dict(c_metrics=list(F.METRICS), footnote="Electrolyte: 1 M LiPF_{6}\n第二行")),
                 ("cycling", dict(cap_unit="mAh/cm2", area_cm2=1.13, lang="zh", c_from=2, c_to=20)),
                 ("vt", dict(t_arrange="by_cell", t_unit="d")), ("vt", dict(legend="none")),
                 ("dqdv", dict(d_cycles="2, 30", d_show="discharge")), ("dqdv", dict(d_arrange="by_cell")),
                 ("profiles", dict(p_cycles="999"))]
        for kind, o in cases:
            with self.subTest(kind=kind, opts=o):
                r = F.build(kind, self.series, o)
                self.assertGreater(len(r.fig.axes), 0)
                for ext in ("png", "svg", "pdf"):
                    p = os.path.join(self.dir, f"fig.{ext}")
                    F.save(r, p, dpi=80)
                    self.assertGreater(os.path.getsize(p), 1000)
                x = os.path.join(self.dir, "data.xlsx")
                export_xlsx(x, r, self.series, o)
                self.assertGreater(os.path.getsize(x), 1000)
        r = F.build("profiles", self.series, dict(cap_unit="mAh/g"))
        self.assertTrue(any("质量" in n for n in r.notes))
        r = F.build("profiles", self.series, dict(p_cycles="999"))
        self.assertTrue(any("没有数据" in n for n in r.notes))

    def test_panel_selection(self):
        r = F.build("profiles", self.series, dict(p_cycles="1, 2, 5"))
        self.assertEqual([k for k, _ in r.all_panels], ["cycle:1", "cycle:2", "cycle:5"])
        self.assertEqual(len(r.fig.axes), 3)
        r = F.build("profiles", self.series, dict(p_cycles="1, 2, 5", hidden_panels=["cycle:1", "cycle:5"]))
        self.assertEqual([p["title"] for p in r.panels], ["Cycle 2"])          # only b is drawn
        self.assertEqual(len([a for a in r.fig.axes if a.get_visible()]), 1)
        self.assertEqual(len(r.all_panels), 3)                                  # all switches still listed
        r = F.build("profiles", self.series, dict(p_cycles="1, 2, 5", hidden_panels=["cycle:2"]))
        self.assertEqual([p["title"] for p in r.panels], ["Cycle 1", "Cycle 5"])
        self.assertEqual([t.get_text() for t in r.fig.texts if t.get_text() in "ab"], ["a", "b"])   # relettered
        r = F.build("cycling", self.series, dict(c_metrics=["dchg_cap", "CE"], hidden_panels=["metric:dchg_cap", "metric:CE"]))
        self.assertEqual(len(r.panels), 2)                                      # everything off -> everything on
        r = F.build("profiles", self.series, dict(p_cycles="1-20"))
        self.assertEqual(len(r.all_panels), F.MAX_PANELS)
        self.assertTrue(any("最多" in n for n in r.notes))

    def test_export_content(self):
        from openpyxl import load_workbook
        r = F.build("cycling", self.series, dict(c_metrics=["dchg_cap"]))
        p = os.path.join(self.dir, "c.xlsx")
        export_xlsx(p, r, self.series, {})
        wb = load_workbook(p, read_only=True)
        ws = wb[wb.sheetnames[0]]
        rows = list(ws.iter_rows(values_only=True))
        self.assertEqual(rows[0][0], "A AlCl_{3}")
        tab = A.cycle_table(self.series[0].cell)
        self.assertAlmostEqual(rows[2][1], tab[0]["dchg_mAh"], places=9)
        self.assertEqual(sum(1 for n in wb.sheetnames if n.startswith("Cycles")), 4)


if __name__ == "__main__":
    unittest.main()
