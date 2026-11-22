"""Tests: python -m unittest discover -s tests -v   (no real data needed)."""
import csv
import datetime as dt
import os
import sys
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

    def test_active_mass_from_header(self):
        for mass, want in ((2.43, 2.43), (0.0, None), (12.5, 12.5)):
            w = CexWriter(mass_mg=mass)
            t = np.arange(0, 3600, 60.0)
            q = 0.243 * t / 3600
            w.step("charge", 1, 1, 0, 0.000243)
            w.points(t * 1000, 3.5 + q, np.full(len(t), 0.000243), q / 1000, q * 3.6 / 1000)
            p = os.path.join(self.dir, f"mass_{mass}.cex")
            w.save(p)
            c = load_file(p)
            self.assertEqual(c.info.get("mass_mg"), want)
        self.assertNotIn("mass_mg", load_file(self.demo[0]).info)        # demo files have no mass

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

    def test_active_mass_from_step_xml(self):
        p = os.path.join(self.dir, "with_mass.ndax")
        write_ndax(p, _li_cl_program(1), loop_starts=[4], scq=3150)
        self.assertAlmostEqual(load_file(p).info["mass_mg"], 3.15)
        p2 = os.path.join(self.dir, "no_mass.ndax")
        write_ndax(p2, _li_cl_program(1), loop_starts=[4])
        self.assertIsNone(load_file(p2).info["mass_mg"])

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
        # EPS (slow with Chinese text, so only twice): with and without Chinese text
        for o in ({"footnote": "1 M LiPF_{6}，第二行"}, {"legend": "none"}):
            r = F.build("vt", self.series, o)
            p = os.path.join(self.dir, "fig.eps")
            F.save(r, p, dpi=80)
            with open(p, "rb") as f:
                eps = f.read()
            self.assertTrue(eps.startswith(b"%!PS-Adobe-3.0 EPSF-3.0"))
            self.assertIn(b"%%BoundingBox", eps)
            # the file uses the font embedding vector_rc() chose for this machine's fonts
            want = F.vector_rc(r, p)["ps.fonttype"]
            self.assertIn(b"/FontType %d" % want, eps)
            self.assertNotIn(b"/FontType %d" % (45 - want), eps)
        r = F.build("profiles", self.series, dict(p_cycles="999"))
        self.assertTrue(any("没有数据" in n for n in r.notes))

    def test_all_cycles_all_cells_in_one_panel(self):
        ser = self.series
        for kind, key, cyc in (("profiles", "p", "1, 2, 5"), ("dqdv", "d", "2, 3")):
            r = F.build(kind, ser, {f"{key}_arrange": "all", f"{key}_cycles": cyc})
            self.assertEqual(len(r.panels), 1)
            self.assertEqual(len(r.axes), 1)
            self.assertEqual(r.all_panels, [])
            n_cyc = len(F.parse_cycles(cyc))
            n_kinds = 2
            self.assertEqual(len(r.panels[0]["curves"]), len(ser) * n_cyc * n_kinds)
        styles = F.cycle_styles(3)
        self.assertEqual([ls for ls, _ in styles], ["-", "--", ":"])
        shades = F.cycle_styles(8)
        self.assertTrue(all(ls == "-" for ls, _ in shades))
        self.assertLess(shades[0][1], shades[-1][1])
        self.assertEqual(F.tint("#000000", 1.0), "#000000")
        self.assertEqual(F.tint("#000000", 0.0), "#ffffff")

    def test_voltage_time_cycles(self):
        ser = self.series
        cell = ser[0].cell
        # whole test (no cycles): as before, one curve per cell starting at t = 0
        r = F.build("vt", ser, {})
        self.assertEqual(len(r.panels[0]["curves"]), len(ser))
        self.assertAlmostEqual(r.panels[0]["curves"][0][1][0], 0.0)
        # one cycle: timed from its own first point, includes its rest steps, title = cycle
        idx = A.cycle_points(cell, 3)
        self.assertEqual(sorted({s.cycle for s in cell.steps if s.start <= idx[0] < s.stop}), [3])
        self.assertTrue(np.all(np.diff(idx) == 1))
        r = F.build("vt", ser[:1], dict(t_cycles="3", t_unit="s"))
        name, x, y = r.panels[0]["curves"][0]
        self.assertEqual(name, "A AlCl_{3} | cycle 3")
        self.assertAlmostEqual(x[0], 0.0)
        self.assertAlmostEqual(x[-1], cell.t[idx[-1]] - cell.t[idx[0]], places=3)
        self.assertEqual(r.panels[0]["title"], "Cycle 3")
        self.assertFalse(any("抽稀" in n for n in r.notes))               # few points: nothing thinned
        # several cycles overlaid from zero: one curve per cell and cycle
        r = F.build("vt", ser, dict(t_cycles="1, 2, 5"))
        self.assertEqual(len(r.panels[0]["curves"]), len(ser) * 3)
        self.assertTrue(all(abs(c[1][0]) < 1e-9 for c in r.panels[0]["curves"]))
        # consecutive cycles joined, timed from the first chosen cycle / from the start of the test
        r = F.build("vt", ser[:1], dict(t_cycles="2-4, 7", t_zero="first", t_unit="s"))
        names = [c[0] for c in r.panels[0]["curves"]]
        self.assertEqual(names, ["A AlCl_{3} | cycles 2–4", "A AlCl_{3} | cycle 7"])
        t2 = cell.t[A.cycle_points(cell, 2)[0]]
        self.assertAlmostEqual(r.panels[0]["curves"][0][1][0], 0.0)
        self.assertAlmostEqual(r.panels[0]["curves"][1][1][0], cell.t[A.cycle_points(cell, 7)[0]] - t2, places=3)
        r = F.build("vt", ser[:1], dict(t_cycles="2-4", t_zero="test", t_unit="s"))
        self.assertAlmostEqual(r.panels[0]["curves"][0][1][0], t2, places=3)
        # one panel per cycle; one panel per cell with cycles coloured
        r = F.build("vt", ser, dict(t_cycles="1, 2, 5", t_arrange="by_cycle"))
        self.assertEqual([k for k, _ in r.all_panels], ["cycle:1", "cycle:2", "cycle:5"])
        self.assertEqual([len(p["curves"]) for p in r.panels], [len(ser)] * 3)
        r = F.build("vt", ser, dict(t_cycles="1, 2", t_arrange="by_cell"))
        self.assertEqual(len(r.panels), len(ser))
        self.assertEqual(len(r.panels[0]["curves"]), 2)
        r = F.build("vt", ser, dict(t_arrange="by_cycle"))                 # needs cycles: falls back
        self.assertEqual(len(r.panels), 1)
        self.assertTrue(any("圈数" in n for n in r.notes))
        r = F.build("vt", ser, dict(t_cycles="2, 999"))
        self.assertTrue(any("没有数据" in n and "999" in n for n in r.notes))
        self.assertEqual(len(r.panels[0]["curves"]), len(ser))
        r = F.build("vt", ser, dict(t_cycles="1, 2, 999", legend="below"))      # no legend entry for 999
        texts = [t.get_text() for lg in r.fig.legends for t in lg.get_texts()]
        self.assertIn("Cycle 2", texts)
        self.assertNotIn("Cycle 999", texts)

    def test_font_embedding_choice(self):
        from galvaplot.plotting import style as S
        r = F.build("vt", self.series[:1], {})
        r.rc = dict(r.rc, **{"font.family": ["DejaVu Sans"]})
        r.cjk = False
        self.assertEqual(F.vector_rc(r, "a.eps").get("ps.fonttype"), 42)     # DejaVu: TrueType with names
        self.assertEqual(F.vector_rc(r, "a.pdf").get("pdf.fonttype"), 42)
        self.assertNotIn("ps.fonttype", F.vector_rc(r, "a.png") if "ps.fonttype" not in r.rc else {})
        from matplotlib import font_manager
        names = {f.name for f in font_manager.fontManager.ttflist}
        for fam in ("Kai", "Arial", "Microsoft YaHei"):       # fonts without glyph names, if present
            if fam in names and not S.type42_ok_for_eps(fam):
                r.rc = dict(r.rc, **{"font.family": [fam]})
                self.assertEqual(F.vector_rc(r, "a.eps")["ps.fonttype"], 3, fam)
        if "PingFang SC" in names:                            # CFF outlines
            r.rc = dict(r.rc, **{"font.family": ["Arial", "PingFang SC"]})
            r.cjk = True
            self.assertEqual(F.vector_rc(r, "a.pdf")["pdf.fonttype"], 3)
            self.assertEqual(F.vector_rc(r, "a.pdf")["ps.fonttype"], 3)      # matplotlib needs both
            self.assertEqual(F.vector_rc(r, "a.eps")["ps.fonttype"], 3)

    def test_panel_text_and_axes(self):
        ser = self.series
        r = F.build("profiles", ser, {"p_cycles": "1, 2", "p_arrange": "by_cycle"})
        self.assertEqual(len(r.axes), len(r.panels))
        txt = F.panel_text(r.panels[1])
        rows = txt.rstrip("\n").split("\n")
        n_cols = 2 * len(r.panels[1]["curves"])
        self.assertTrue(all(len(row.split("\t")) == n_cols for row in rows))
        head2 = rows[1].split("\t")
        self.assertTrue(head2[0].startswith("Capacity") and head2[1].startswith("Voltage"))
        name, x, y = r.panels[1]["curves"][0]
        self.assertAlmostEqual(float(rows[2].split("\t")[0]), float(x[0]), places=4)
        self.assertAlmostEqual(float(rows[2].split("\t")[1]), float(y[0]), places=4)
        self.assertNotIn("$", txt)

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


class TestUpdates(unittest.TestCase):
    def test_versions(self):
        from galvaplot import updates as U
        self.assertEqual(U.parse_version("v0.2.10"), (0, 2, 10))
        self.assertEqual(U.parse_version("1.0"), (1, 0, 0))
        self.assertIsNone(U.parse_version("latest"))
        self.assertTrue(U.is_newer("v0.10.0", "0.9.9"))
        self.assertFalse(U.is_newer("v0.2.0", "0.2.0"))
        self.assertFalse(U.is_newer("garbage", "0.2.0"))

    def test_interpret_and_assets(self):
        import json as _json
        from galvaplot import updates as U
        assets = [{"name": "GalvaPlot-9.0.0-Windows-Setup.exe", "browser_download_url": "https://x/setup.exe"},
                  {"name": "GalvaPlot-9.0.0-Windows-x64-portable.zip", "browser_download_url": "https://x/p.zip"},
                  {"name": "GalvaPlot-9.0.0-macOS-AppleSilicon.dmg", "browser_download_url": "https://x/a.dmg"}]
        self.assertEqual(U.pick_asset(assets, "win32", "AMD64"), "https://x/setup.exe")
        self.assertEqual(U.pick_asset(assets, "darwin", "arm64"), "https://x/a.dmg")
        self.assertIsNone(U.pick_asset(assets, "darwin", "x86_64"))      # no Intel build: release page
        self.assertIsNone(U.pick_asset(assets, "linux", "x86_64"))
        body = "## GalvaPlot v9 · 标题\n\n- **新功能** `x`\n| a | b |\n---\n**English** — skip"
        r = U.interpret(_json.dumps({"tag_name": "v9.0.0", "html_url": "https://x/rel", "body": body,
                                     "assets": assets}).encode(), current="0.2.0")
        self.assertTrue(r["ok"] and r["newer"])
        self.assertEqual(r["latest"], "9.0.0")
        self.assertEqual(r["notes"], "GalvaPlot v9 · 标题\n- 新功能 x")
        self.assertIn(r["download"], ("https://x/setup.exe", "https://x/a.dmg", "https://x/rel"))
        r = U.interpret(b'{"tag_name": "v0.2.0"}', current="0.2.0")
        self.assertTrue(r["ok"] and not r["newer"])
        self.assertFalse(U.interpret(b'{"message": "Not Found"}')["ok"])
        self.assertFalse(U.interpret(b"<html>")["ok"])


class TestSelfUpdate(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_asset_digest(self):
        from galvaplot import updates as U
        h = "ab" * 32
        assets = [{"name": "GalvaPlot-9.0.0-macOS-AppleSilicon.dmg", "browser_download_url": "https://x/a.dmg",
                   "size": 123, "digest": "sha256:" + h.upper()},
                  {"name": "GalvaPlot-9.0.0-Windows-Setup.exe", "browser_download_url": "https://x/s.exe"}]
        a = U.asset_info(assets, "darwin", "arm64")
        self.assertEqual((a["url"], a["size"], a["sha256"]), ("https://x/a.dmg", 123, h))
        self.assertIsNone(U.asset_info(assets, "win32", "AMD64")["sha256"])      # no digest: no self-install
        os.environ["GALVAPLOT_FAKE_VERSION"] = "0.0.1"
        try:
            self.assertEqual(U.current_version(), "0.0.1")
            self.assertTrue(U.interpret(b'{"tag_name": "v0.1.0"}')["newer"])
        finally:
            del os.environ["GALVAPLOT_FAKE_VERSION"]

    def test_install_target(self):
        from galvaplot import self_update as SU
        self.assertIsNone(SU.install_target(frozen=False)[0])
        app = os.path.join(self.dir, "GalvaPlot.app")
        os.makedirs(os.path.join(app, "Contents", "MacOS"))
        exe = os.path.join(app, "Contents", "MacOS", "GalvaPlot")
        self.assertEqual(SU.install_target(exe, "darwin", True), (app, None))
        self.assertIsNone(SU.install_target(os.path.join(self.dir, "x", "y", "z"), "darwin", True)[0])
        win = os.path.join(self.dir, "win")
        os.makedirs(win)
        exe = os.path.join(win, "GalvaPlot.exe")
        self.assertIsNone(SU.install_target(exe, "win32", True)[0])               # portable: no
        open(os.path.join(win, "unins000.exe"), "w").close()
        self.assertEqual(SU.install_target(exe, "win32", True), (win, None))
        self.assertIsNone(SU.install_target(exe, "linux", True)[0])

    def test_windows_command(self):
        from galvaplot import self_update as SU
        cmd = SU.windows_command(r"C:\Temp\GalvaPlot-9.0.0-Windows-Setup.exe")
        self.assertEqual(cmd[0], r"C:\Temp\GalvaPlot-9.0.0-Windows-Setup.exe")
        self.assertIn("/SILENT", cmd)
        self.assertIn("/FORCECLOSEAPPLICATIONS", cmd)
        self.assertIn("/RELAUNCH=1", cmd)
        self.assertIn("/LOG=" + SU.setup_log_path(), cmd)                       # Inno Setup writes a log
        self.assertNotIn("/RELAUNCH=1", SU.windows_command("x.exe", relaunch=False))

    def test_sha256_file(self):
        import hashlib
        from galvaplot import self_update as SU
        p = os.path.join(self.dir, "f.bin")
        data = os.urandom(3_000_000)
        with open(p, "wb") as f:
            f.write(data)
        self.assertEqual(SU.sha256_file(p, chunk=65536), hashlib.sha256(data).hexdigest())

    @unittest.skipUnless(sys.platform == "darwin", "needs hdiutil")
    def test_mac_swap_script(self):
        import subprocess
        from galvaplot import self_update as SU

        def fake_app(root, version):
            c = os.path.join(root, "GalvaPlot.app", "Contents")
            os.makedirs(c)
            with open(os.path.join(c, "version.txt"), "w") as f:
                f.write(version)

        stage = os.path.join(self.dir, "stage")
        fake_app(stage, "new")
        dmg = os.path.join(self.dir, "new.dmg")
        subprocess.run(["hdiutil", "create", "-quiet", "-volname", "GalvaPlotTest", "-srcfolder", stage,
                        "-fs", "HFS+", "-format", "UDZO", dmg], check=True)
        apps = os.path.join(self.dir, "Applications")
        fake_app(apps, "old")
        target = os.path.join(apps, "GalvaPlot.app")
        script = os.path.join(self.dir, "u.sh")
        with open(script, "w") as f:
            f.write(SU.MAC_SCRIPT)
        dead = subprocess.Popen(["true"])
        dead.wait()
        r = subprocess.run(["/bin/sh", script, str(dead.pid), dmg, target, "0"], capture_output=True, text=True,
                           timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(os.path.join(target, "Contents", "version.txt")) as f:
            self.assertEqual(f.read(), "new")
        self.assertFalse(os.path.exists(dmg))                                   # downloaded file removed
        self.assertEqual(sorted(os.listdir(apps)), ["GalvaPlot.app"])          # no leftovers
        # a broken package keeps the installed version
        with open(dmg, "wb") as f:
            f.write(b"not a disk image")
        r = subprocess.run(["/bin/sh", script, str(dead.pid), dmg, target, "0"], capture_output=True, text=True,
                           timeout=120)
        with open(os.path.join(target, "Contents", "version.txt")) as f:
            self.assertEqual(f.read(), "new")


@unittest.skipUnless(sys.platform == "darwin", "GUI check run locally (CI Linux has no display libraries)")
class TestPreviewMenu(Tmp):
    def test_every_menu_action_does_something(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QPoint, QSettings
        from PySide6.QtWidgets import QApplication
        from galvaplot.gui.plot_panel import PlotPanel
        app = QApplication.instance() or QApplication([])
        settings = QSettings(os.path.join(self.dir, "s.ini"), QSettings.Format.IniFormat)
        cells = [load_file(p) for p in self.demo[:2]]
        series = [F.Series(c, f"cell {i}", PALETTE[i], "solid", 2.0) for i, c in enumerate(cells)]
        panel = PlotPanel(settings, lambda: series, lambda: False)
        panel.resize(900, 700)
        panel.show()
        panel.set_kind("profiles")
        panel.redraw()
        app.processEvents()
        acts = {a.text(): a for a in panel._build_preview_menu(QPoint(5, 5)).actions() if a.text()}
        self.assertFalse(panel.more_dlg.isVisible())
        acts["更多设置（坐标范围、字号、图例…）"].trigger()           # used to do nothing
        app.processEvents()
        self.assertTrue(panel.more_dlg.isVisible())
        panel.more_dlg.hide()
        # the single-panel arrangement: "复制数据" puts the plotted data on the clipboard
        panel.opts["p_arrange"] = "all"
        panel.redraw()
        app.processEvents()
        centre = QPoint(panel.preview.width() // 2, panel.preview.height() // 2)
        acts = {a.text(): a for a in panel._build_preview_menu(centre).actions() if a.text()}
        QApplication.clipboard().setText("")
        acts["复制数据"].trigger()
        self.assertIn("Capacity (mAh)", QApplication.clipboard().text())
        panel.close()


def _ghostscript():
    gs = os.environ.get("GALVAPLOT_GS") or shutil.which("gs")
    return gs if gs and os.path.exists(gs) else None


@unittest.skipUnless(_ghostscript(), "needs Ghostscript (set GALVAPLOT_GS)")
class TestVectorFontsRender(Tmp):
    """PDF/EPS drawn by Ghostscript must show as much text "ink" as the PNG: catches fonts
    that only macOS Preview can display (missing Chinese glyphs elsewhere)."""

    def _ink(self, png):
        from PIL import Image
        import numpy as np
        im = np.asarray(Image.open(png).convert("L"))
        return int((im < 128).sum())

    def _report(self, src, out, args, ratio):
        """Print what is needed to understand a failure on a CI machine."""
        import subprocess
        import numpy as np
        from PIL import Image
        im = np.asarray(Image.open(out).convert("L"))
        print(f"\n--- {os.path.basename(src)}: ink ratio {ratio:.2f}; image {im.shape}, "
              f"min {im.min()}, pixels < 250: {(im < 250).sum()}")
        with open(src, "rb") as f:
            data = f.read()
        lines = data.split(b"\n")
        print("--- head:", b" | ".join(lines[:14]).decode("latin-1")[:1500])
        for key in (b"%%BoundingBox", b"/FontType", b"/FontName", b"/sfnts", b"/CharStrings", b"glyphshow", b"findfont"):
            hits = [ln for ln in lines if key in ln][:4]
            print(f"--- {key.decode()} x{sum(1 for ln in lines if key in ln)}:", b" | ".join(hits).decode("latin-1")[:400])
        verbose = [a for a in args if a != "-q"]
        r = subprocess.run(verbose, capture_output=True, text=True, timeout=120)
        print("--- gs:", (r.stdout + r.stderr)[-3000:])

    def test_chinese_and_latin_text(self):
        import subprocess
        import matplotlib
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure
        from galvaplot.plotting.style import rc
        for cjk, text in ((True, "电压 AlCl$_{3}$ 第 1 圈 Li$^{+}$"), (False, "Voltage AlCl$_{3}$ Li$^{+}$ 1.0")):
            params = rc(14, cjk)
            with matplotlib.rc_context(params):          # as in figures.build()
                fig = Figure(figsize=(5, 1.2))
                FigureCanvasAgg(fig)
                t = fig.text(0.04, 0.35, text, fontsize=26)
                F._fix_cjk_math([t])
            res = F.FigureResult(fig, [], [], params)
            res.cjk = cjk
            ref = os.path.join(self.dir, "ref.png")
            F.save(res, ref, dpi=100)
            for ext in ("pdf", "eps"):
                with self.subTest(cjk=cjk, fmt=ext):
                    src = os.path.join(self.dir, f"t.{ext}")
                    out = os.path.join(self.dir, f"t_{ext}.png")
                    F.save(res, src, dpi=100)
                    args = [_ghostscript(), "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pnggray", "-r100",
                            "-dTextAlphaBits=4", "-dGraphicsAlphaBits=4", "-sOutputFile=" + out]
                    args += (["-dEPSCrop"] if ext == "eps" else []) + [src]
                    p = subprocess.run(args, capture_output=True, text=True, timeout=120)
                    self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                    self.assertNotIn("Error", p.stdout + p.stderr)
                    ratio = self._ink(out) / self._ink(ref)
                    if not 0.8 < ratio < 1.35:
                        self._report(src, out, args, ratio)
                    # missing glyphs drop this to about 0.5; Type 3 glyphs come out slightly heavier
                    self.assertGreater(ratio, 0.8, f"{ext}: text ink {ratio:.2f} of the PNG")
                    self.assertLess(ratio, 1.35, f"{ext}: text ink {ratio:.2f} of the PNG")

if __name__ == "__main__":
    unittest.main()
