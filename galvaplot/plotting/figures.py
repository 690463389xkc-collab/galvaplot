"""Figure builders. Each returns a FigureResult (figure + plotted data + notes).

No pyplot: figures are plain matplotlib Figure objects with an Agg canvas, so
they can be built in any thread and never open a window.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import matplotlib
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import AutoMinorLocator, MaxNLocator

from .. import analysis as A
from ..model import CHARGE, DISCHARGE
from ..textfmt import rich
from .style import LINESTYLES, has_cjk, rc, ramp

CM = 1 / 2.54

DEFAULTS = dict(
    # common
    lang="en", font_size=14.0, panel_w_cm=16.5, panel_h_cm=12.0, letters=True, legend="auto",
    footnote="", xmin=None, xmax=None, ymin=None, ymax=None, ce_mode="dchg/chg", area_cm2=None,
    ref_cycle=None, include_last=False, cap_unit="mAh", line_width=2.0,
    # voltage profiles
    p_cycles="1, 2, 5", p_show="both", p_arrange="by_cycle",
    # cycling
    c_metrics=["dchg_cap", "CE"], c_from=None, c_to=None,
    # voltage-time
    t_unit="h", t_arrange="overlay",
    # dQ/dV
    d_cycles="2", d_show="both", d_dv_mV=5.0, d_smooth=5, d_arrange="by_cycle",
)

FIG_TYPES = {"profiles": "充放电曲线", "cycling": "循环性能", "vt": "电压–时间", "dqdv": "dQ/dV"}

METRICS = {   # key: (English label, Chinese label, needs capacity unit)
    "dchg_cap": ("Discharge capacity", "放电容量", True),
    "chg_cap": ("Charge capacity", "充电容量", True),
    "CE": ("Coulombic efficiency (%)", "库仑效率 (%)", False),
    "EE": ("Energy efficiency (%)", "能量效率 (%)", False),
    "retention": ("Capacity retention (%)", "容量保持率 (%)", False),
    "Vavg_dchg": ("Average discharge voltage (V)", "平均放电电压 (V)", False),
    "Vavg_chg": ("Average charge voltage (V)", "平均充电电压 (V)", False),
    "dV": ("ΔV (V)", "ΔV (V)", False),
}
METRIC_ZH_SHORT = {"dchg_cap": "放电容量", "chg_cap": "充电容量", "CE": "库仑效率", "EE": "能量效率",
                   "retention": "容量保持率", "Vavg_dchg": "平均放电电压", "Vavg_chg": "平均充电电压",
                   "dV": "充放电电压差 ΔV"}


@dataclass
class Series:
    cell: object
    label: str
    color: str
    ls: str = "solid"
    mass_mg: float | None = None
    _tables: dict = field(default_factory=dict)

    def table(self, ce_mode):
        if ce_mode not in self._tables:
            self._tables[ce_mode] = A.cycle_table(self.cell, ce_mode)
        return self._tables[ce_mode]


@dataclass
class FigureResult:
    fig: Figure
    panels: list            # [{"title", "xlabel", "ylabel", "curves": [(name, x, y)]}]
    notes: list
    rc: dict
    all_panels: list = field(default_factory=list)   # [(key, title)] of every possible sub-plot
    axes: list = field(default_factory=list)         # visible axes, same order as panels
    cjk: bool = False                                # figure text contains Chinese


MAX_PANELS = 12
LETTERS = "abcdefghijklmnopqrstuvwxyz"


def select_panels(items, key, title, opts, notes):
    """Keep the sub-plots the user has switched on (opts["hidden_panels"] = keys switched off).

    Returns (items to draw, [(key, title)] of all candidates). If everything is
    switched off, everything is drawn.
    """
    if len(items) > MAX_PANELS:
        notes.append(f"子图最多 {MAX_PANELS} 个，只画前 {MAX_PANELS} 个")
        items = items[:MAX_PANELS]
    allp = [(key(x), title(x)) for x in items]
    hidden = set(opts.get("hidden_panels") or ())
    shown = [x for x in items if key(x) not in hidden]
    return (shown or list(items)), allp


# ------------------------------------------------------------------ text
def T(opts, en, zh):
    return zh if opts.get("lang") == "zh" else en


def parse_cycles(text) -> list:
    """'1, 2, 5-7' -> [1, 2, 5, 6, 7]"""
    out = []
    for part in re.split(r"[,，;；\s]+", str(text or "").strip()):
        if not part:
            continue
        m = re.match(r"^(\d+)\s*[-–~～]\s*(\d+)$", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out.extend(range(min(a, b), max(a, b) + 1))
        elif part.isdigit():
            out.append(int(part))
    seen, res = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            res.append(c)
    return res[:30]


def cycle_title(opts, c):
    return T(opts, f"Cycle {c}", f"第 {c} 圈")


# ------------------------------------------------------------------ capacity units
def ref_capacity(s: Series, opts):
    tab = s.table(opts["ce_mode"])
    ref = opts.get("ref_cycle")
    if ref:
        r = [x for x in tab if x["cycle"] == int(ref)]
        if r and r[0]["dchg_mAh"] > 0:
            return float(r[0]["dchg_mAh"]), int(ref)
    c = A.first_discharge_cycle(s.cell)
    r = [x for x in tab if x["cycle"] == c]
    if r and r[0]["dchg_mAh"] > 0:
        return float(r[0]["dchg_mAh"]), c
    return None, None


def cap_factor(s: Series, opts):
    """Multiply mAh by this to get the selected unit. Returns (factor, error message or None)."""
    u = opts["cap_unit"]
    if u == "mAh":
        return 1.0, None
    if u == "mAh/g":
        if not s.mass_mg or s.mass_mg <= 0:
            return None, f"“{s.label}”没有填写活性物质质量，无法换算比容量"
        return 1000.0 / s.mass_mg, None
    if u == "mAh/cm2":
        a = opts.get("area_cm2")
        if not a or a <= 0:
            return None, "请在“更多设置”里填写电极面积，才能换算面容量"
        return 1.0 / a, None
    if u == "%":
        q, _ = ref_capacity(s, opts)
        if not q:
            return None, f"“{s.label}”没有可作参考的放电容量"
        return 100.0 / q, None
    return 1.0, None


def cap_unit_text(opts):
    u = opts["cap_unit"]
    return {"mAh": "mAh", "mAh/g": "mAh g$^{-1}$", "mAh/cm2": "mAh cm$^{-2}$", "%": "%"}[u]


def cap_label(opts, kind="Capacity"):
    u = opts["cap_unit"]
    if u == "%":
        ref = opts.get("ref_cycle")
        if ref:
            return T(opts, f"{kind} (% of cycle-{ref} discharge)", f"{_zh_kind(kind)} (第 {ref} 圈放电容量的 %)")
        return T(opts, f"{kind} (% of 1st discharge)", f"{_zh_kind(kind)} (首次放电容量的 %)")
    if u == "mAh/g":
        kind_en = "Specific capacity" if kind == "Capacity" else f"Specific {kind[0].lower() + kind[1:]}"
        return T(opts, f"{kind_en} (mAh g$^{{-1}}$)", f"比{_zh_kind(kind)} (mAh g$^{{-1}}$)")
    if u == "mAh/cm2":
        kind_en = "Areal capacity" if kind == "Capacity" else f"Areal {kind[0].lower() + kind[1:]}"
        return T(opts, f"{kind_en} (mAh cm$^{{-2}}$)", f"面{_zh_kind(kind)} (mAh cm$^{{-2}}$)")
    return T(opts, f"{kind} (mAh)", f"{_zh_kind(kind)} (mAh)")


def _zh_kind(kind):
    return {"Capacity": "容量", "Discharge capacity": "放电容量", "Charge capacity": "充电容量"}.get(kind, kind)


# ------------------------------------------------------------------ layout helpers
def _grid(n):
    if n <= 3:
        return 1, max(n, 1)
    if n == 4:
        return 2, 2
    if n <= 6:
        return 2, 3
    if n <= 9:
        return 3, 3
    return 3, 4


def new_figure(n, opts):
    rows, cols = _grid(n)
    W = opts["panel_w_cm"] * CM * cols
    H = opts["panel_h_cm"] * CM * rows
    fig = Figure(figsize=(W, H))
    FigureCanvasAgg(fig)
    axes = []
    for k in range(rows * cols):
        ax = fig.add_subplot(rows, cols, k + 1)
        if k >= n:
            ax.set_visible(False)
        else:
            axes.append(ax)
    for ax in axes:
        ax.xaxis.set_minor_locator(AutoMinorLocator(2))
        ax.yaxis.set_minor_locator(AutoMinorLocator(2))
    return fig, axes, rows, cols


def _text_width_pt(s, fs):
    w = 0.0
    for ch in re.sub(r"\$[^$]*\$", "xx", s):
        w += fs * (1.0 if ord(ch) > 0x2E80 else 0.55)
    return w


def _wrap(text, fs, width_pt):
    out = []
    for para in text.split("\n"):
        words = para.split(" ")
        line = ""
        for w in words:
            trial = (line + " " + w) if line else w
            if line and _text_width_pt(trial, fs) > width_pt:
                out.append(line)
                line = w
            else:
                line = trial
        out.append(line)
    return out


def _fix_cjk_math(texts):
    """Mixed Chinese + formula strings are drawn by mathtext, which uses only the
    first font of the text's family list: put a CJK font first for those."""
    from .style import _CJK, font_families
    fam = font_families()
    cj = [f for f in fam if f in _CJK]
    if not cj:
        return
    for t in texts:
        if t is None:
            continue
        s = t.get_text()
        if "$" in s and has_cjk(s):
            t.set_fontfamily([cj[0]] + [f for f in fam if f != cj[0]])


def _all_texts(fig, axes):
    out = []
    for ax in axes:
        out += [ax.xaxis.label, ax.yaxis.label, ax.title, ax._left_title, ax._right_title]
        out += list(ax.texts)
        lg = ax.get_legend()
        if lg:
            out += list(lg.get_texts())
    out += list(fig.texts)
    for lg in fig.legends:
        out += list(lg.get_texts())
    return out


def _legend_covers_data(fig, ax, legend) -> bool:
    """True if any plotted data point lies under the legend box (after matplotlib's 'best' placement)."""
    fig.canvas.draw()
    box = legend.get_window_extent(fig.canvas.get_renderer()).padded(2)
    for line in ax.get_lines():
        if line.get_transform() != ax.transData:      # axhline etc. (reference lines) do not count
            continue
        xy = np.asarray(line.get_xydata(), float)
        xy = xy[np.isfinite(xy).all(axis=1)]
        if not len(xy):
            continue
        px = ax.transData.transform(xy)
        inside = ((px[:, 0] >= box.x0) & (px[:, 0] <= box.x1) & (px[:, 1] >= box.y0) & (px[:, 1] <= box.y1))
        if inside.any():
            return True
    return False


def finalize(fig, axes, handles, labels, opts, n_rows=1):
    """Legend, footnote, tight layout and panel letters, growing the figure as needed."""
    s = opts["font_size"] / 14.0
    renderer = fig.canvas.get_renderer()
    _fix_cjk_math(_all_texts(fig, axes))
    W, H0 = fig.get_size_inches()
    n = len(axes)
    letters = bool(opts.get("letters")) and n > 1
    mode = opts.get("legend", "auto")
    auto = mode == "auto"
    if auto:
        mode = "inside" if (n == 1 and len(handles) <= 6) else "below"
    if not handles or (len(handles) == 1 and mode != "none" and n == 1 and len(labels) == 1 and not labels[0]):
        mode = "none"
    fs_leg = 12.5 * s
    fs_foot = 13.5 * s
    if mode == "inside":
        lg = axes[0].legend(handles, labels, loc="best", fontsize=fs_leg * 0.96, handlelength=2.6)
        _fix_cjk_math(lg.get_texts())
        if auto and _legend_covers_data(fig, axes[0], lg):
            lg.remove()          # no free corner: put the legend under the plot instead
            mode = "below"

    foot, h_foot = None, 0.0
    text = (opts.get("footnote") or "").strip()
    if text:
        lines = _wrap(text, fs_foot, W * 72 * 0.94)
        foot = fig.text(0.5, 0.0, "\n".join(rich(l) for l in lines), ha="center", va="bottom",
                        fontsize=fs_foot, linespacing=1.45)
        _fix_cjk_math([foot])
        h_foot = foot.get_window_extent(renderer).height / fig.dpi

    leg, h_leg = None, 0.0
    if mode == "below":
        maxlen = max((_text_width_pt(l, fs_leg) for l in labels), default=0)
        ncol = max(1, min(len(handles), int((W * 72 * 0.94) // (maxlen + fs_leg * 5.5)) or 1, 4))
        ncol = math.ceil(len(handles) / math.ceil(len(handles) / ncol))   # balanced rows, e.g. 4 -> 2 x 2
        while True:
            leg = fig.legend(handles, labels, loc="lower center", ncol=ncol, fontsize=fs_leg,
                             handlelength=2.6, columnspacing=2.0, frameon=False)
            _fix_cjk_math(leg.get_texts())
            wpx = leg.get_window_extent(renderer).width / fig.dpi
            if wpx <= W * 0.98 or ncol == 1:
                break
            leg.remove()
            ncol -= 1
        h_leg = leg.get_window_extent(renderer).height / fig.dpi

    pad, gap = 0.10, 0.14
    letter_h = 19 * s / 72
    top = (letter_h + 0.18) if letters else 0.12
    H = H0 + pad + (h_foot + gap if foot else 0) + (h_leg + gap if leg else 0) + top
    fig.set_size_inches(W, H)
    y = pad
    if foot:
        foot.set_y(y / H)
        y += h_foot + gap
    if leg:
        leg.set_bbox_to_anchor((0.5, y / H), transform=fig.transFigure)
        y += h_leg + gap
    h_pad = 2.8 if (letters and n_rows > 1) else 1.6
    fig.tight_layout(rect=(0, y / H, 1, 1 - top / H), w_pad=2.2, h_pad=h_pad)
    if letters:
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        inv = fig.transFigure.inverted()
        boxes = [ax.get_tightbbox(renderer).transformed(inv) for ax in axes]
        rows = {}
        for ax, bb in zip(axes, boxes):
            key = round(ax.get_position().y1, 3)
            rows[key] = max(rows.get(key, 0), bb.y1)
        for k, (ax, bb) in enumerate(zip(axes, boxes)):
            y1 = rows[round(ax.get_position().y1, 3)]
            fig.text(bb.x0, y1 + 0.06 / H, LETTERS[k], fontsize=19 * s, va="bottom", ha="left")


def apply_limits(axes, opts, x=True, y=True):
    for ax in axes:
        if x and (opts.get("xmin") is not None or opts.get("xmax") is not None):
            ax.set_xlim(left=opts.get("xmin"), right=opts.get("xmax"))
        if y and (opts.get("ymin") is not None or opts.get("ymax") is not None):
            ax.set_ylim(bottom=opts.get("ymin"), top=opts.get("ymax"))


def line_kw(s: Series, opts, lw=None):
    return dict(color=s.color, ls=LINESTYLES.get(s.ls, "-"), lw=lw or opts["line_width"])


def marker_kw(s: Series, opts, n_pts):
    if n_pts > 150:
        ms, lw, ls = 3.0, 0, "none"
    elif n_pts > 40:
        ms, lw, ls = 4.5, 1.2, LINESTYLES.get(s.ls, "-")
    else:
        ms, lw, ls = 6.5, opts["line_width"] * 0.8, LINESTYLES.get(s.ls, "-")
    filled = s.ls == "solid"
    return dict(color=s.color, ls=ls, lw=lw, marker="o", ms=ms, mec=s.color,
                mfc=s.color if filled else "white", mew=1.5)


def legend_line(s: Series, opts):
    return Line2D([], [], **line_kw(s, opts))


CYCLE_LS = ["-", "--", ":", "-."]


def tint(color, f):
    """Mix a colour with white: f = 1 keeps it, f -> 0 makes it pale."""
    from matplotlib.colors import to_hex, to_rgb
    c = np.array(to_rgb(color))
    return to_hex(1 - (1 - c) * f)


def cycle_styles(n):
    """How cycles are told apart when all cells share one panel ("所有圈+所有电池"): line
    style for up to 4 cycles, otherwise shades of the cell colour (pale = early, full = late)."""
    if n <= len(CYCLE_LS):
        return [(ls, 1.0) for ls in CYCLE_LS[:n]]
    return [("-", 0.28 + 0.72 * k / (n - 1)) for k in range(n)]


def overlay_legend(use, cycles, opts):
    """Legend for the all-in-one panel: one entry per cell (colour) + one per cycle (style)."""
    styles = cycle_styles(len(cycles))
    lw = opts["line_width"]
    handles, labels = [], []
    if len(use) > 1 or len(cycles) == 1:
        handles += [Line2D([], [], color=s.color, lw=lw) for s in use]
        labels += [rich(s.label) for s in use]
    if len(cycles) > 1:
        base = use[0].color if len(use) == 1 else "#3a3a3a"
        pairs = list(zip(cycles, styles))
        if len(pairs) > 6:                 # shades: first and last are enough (pale -> full)
            pairs = [pairs[0], pairs[-1]]
        handles += [Line2D([], [], color=tint(base, f), ls=ls, lw=lw) for _, (ls, f) in pairs]
        labels += [cycle_title(opts, c) for c, _ in pairs]
    return handles, labels


def legend_marker(s: Series, opts):
    return Line2D([], [], **marker_kw(s, opts, 10))


# ------------------------------------------------------------------ figure: voltage profiles
def _kinds(show):
    return {"both": (CHARGE, DISCHARGE), "charge": (CHARGE,), "discharge": (DISCHARGE,)}[show]


def fig_profiles(series, opts):
    notes, panels = [], []
    cycles = parse_cycles(opts["p_cycles"])
    if not cycles:
        cycles = [1]
        notes.append("没有输入有效圈数，已画第 1 圈")
    kinds = _kinds(opts["p_show"])
    facs = {}
    for s in series:
        f, err = cap_factor(s, opts)
        if err:
            notes.append(err)
        else:
            facs[id(s)] = f
    use = [s for s in series if id(s) in facs]
    by_cell = opts["p_arrange"] == "by_cell"
    overlay = opts["p_arrange"] == "all"
    if overlay:
        n, allp = 1, []
    elif by_cell:
        cells_p, allp = select_panels(use, lambda x: "cell:" + x.cell.path, lambda x: x.label, opts, notes)
        n = len(cells_p)
    else:
        cyc_p, allp = select_panels(cycles, lambda c: f"cycle:{c}", lambda c: cycle_title(opts, c), opts, notes)
        n = len(cyc_p)
    fig, axes, rows, cols = new_figure(max(n, 1), opts)
    xl, yl = cap_label(opts), T(opts, "Voltage (V)", "电压 (V)")
    handles, labels = [], []
    colors = ramp(len(cycles))
    missing = []
    if overlay:
        ax = axes[0]
        pdata = {"title": T(opts, "All cells", "所有电池"), "xlabel": xl, "ylabel": yl, "curves": []}
        for s in use:
            for c, (ls, f) in zip(cycles, cycle_styles(len(cycles))):
                got = False
                for k in kinds:
                    pr = A.profile(s.cell, c, k)
                    if pr is None:
                        continue
                    got = True
                    q, v = A.decimate(pr[0] * facs[id(s)], pr[1])
                    ax.plot(q, v, color=tint(s.color, f), ls=ls, lw=opts["line_width"])
                    pdata["curves"].append((f"{s.label} | cycle {c} {k}", pr[0] * facs[id(s)], pr[1]))
                if not got:
                    missing.append(f"{s.label} 第 {c} 圈")
        panels.append(pdata)
        handles, labels = overlay_legend(use, cycles, opts)
        if len(cycles) > len(CYCLE_LS):
            notes.append(f"{len(cycles)} 圈用同一颜色由浅到深区分（第 {cycles[0]} 圈最浅）")
    elif by_cell:
        for ax, s in zip(axes, cells_p):
            pdata = {"title": s.label, "xlabel": xl, "ylabel": yl, "curves": []}
            for c, col in zip(cycles, colors):
                for k in kinds:
                    pr = A.profile(s.cell, c, k)
                    if pr is None:
                        continue
                    q, v = A.decimate(pr[0] * facs[id(s)], pr[1])
                    ax.plot(q, v, color=col, lw=opts["line_width"], ls="-")
                    pdata["curves"].append((f"{s.label} | cycle {c} {k}", pr[0] * facs[id(s)], pr[1]))
                if not any(A.profile(s.cell, c, k) is not None for k in kinds):
                    missing.append(f"{s.label} 第 {c} 圈")
            ax.set_title(rich(s.label), fontsize=13.5 * opts["font_size"] / 14)
            panels.append(pdata)
        handles = [Line2D([], [], color=col, lw=opts["line_width"]) for col in colors]
        labels = [cycle_title(opts, c) for c in cycles]
    else:
        for ax, c in zip(axes, cyc_p):
            pdata = {"title": cycle_title(opts, c), "xlabel": xl, "ylabel": yl, "curves": []}
            for s in use:
                got = False
                for k in kinds:
                    pr = A.profile(s.cell, c, k)
                    if pr is None:
                        continue
                    got = True
                    q, v = A.decimate(pr[0] * facs[id(s)], pr[1])
                    ax.plot(q, v, **line_kw(s, opts))
                    pdata["curves"].append((f"{s.label} | {k}", pr[0] * facs[id(s)], pr[1]))
                if not got:
                    missing.append(f"{s.label} 第 {c} 圈")
            ax.set_title(cycle_title(opts, c))
            panels.append(pdata)
        handles = [legend_line(s, opts) for s in use]
        labels = [rich(s.label) for s in use]
    for ax in axes:
        ax.set_xlabel(xl)
    for k, ax in enumerate(axes):
        if k % cols == 0:
            ax.set_ylabel(yl)
    _share_y(axes, cols)
    apply_limits(axes, opts)
    if missing:
        notes.append("没有数据：" + "、".join(missing[:8]) + (" 等" if len(missing) > 8 else ""))
    finalize(fig, axes, handles, labels, opts, rows)
    return FigureResult(fig, panels, notes, rc(opts["font_size"], opts.get("_cjk", False)), allp)


def _share_y(axes, cols):
    """Same y-range in a row of voltage panels (easier comparison); labels only on the left."""
    if len(axes) < 2:
        return
    lo = min(ax.get_ylim()[0] for ax in axes)
    hi = max(ax.get_ylim()[1] for ax in axes)
    for ax in axes:
        ax.set_ylim(lo, hi)


# ------------------------------------------------------------------ figure: cycling
def fig_cycling(series, opts):
    notes, panels = [], []
    metrics = [m for m in opts["c_metrics"] if m in METRICS] or ["dchg_cap"]
    metrics, allp = select_panels(metrics, lambda m: "metric:" + m,
                                  lambda m: T(opts, METRICS[m][0], METRICS[m][1]), opts, notes)
    fig, axes, rows, cols = new_figure(len(metrics), opts)
    cfrom, cto = opts.get("c_from"), opts.get("c_to")
    handles, labels = [], []
    dropped = []
    capfac = {}
    for s in series:
        f, err = cap_factor(s, opts)
        if err and any(METRICS[m][2] for m in metrics):
            notes.append(err)
        capfac[id(s)] = f
    for ax, m in zip(axes, metrics):
        en, zh, is_cap = METRICS[m]
        if is_cap:
            yl = cap_label(opts, en)
        elif m == "retention":
            yl = T(opts, "Capacity retention (%)", "容量保持率 (%)")
        else:
            yl = T(opts, en, zh)
        pdata = {"title": T(opts, en, zh), "xlabel": "Cycle number", "ylabel": yl, "curves": []}
        for s in series:
            tab = s.table(opts["ce_mode"])
            if tab and not tab[-1]["complete"] and not opts.get("include_last"):
                if m == metrics[0]:
                    dropped.append(f"{s.label} 第 {tab[-1]['cycle']} 圈")
                tab = tab[:-1]
            if cfrom:
                tab = [r for r in tab if r["cycle"] >= int(cfrom)]
            if cto:
                tab = [r for r in tab if r["cycle"] <= int(cto)]
            if is_cap and capfac[id(s)] is None:
                continue
            xs, ys = [], []
            qref, _ = ref_capacity(s, opts) if m == "retention" else (None, None)
            for r in tab:
                if m == "dchg_cap":
                    v = r["dchg_mAh"] * capfac[id(s)]
                elif m == "chg_cap":
                    v = r["chg_mAh"] * capfac[id(s)]
                elif m == "retention":
                    v = 100 * r["dchg_mAh"] / qref if qref else float("nan")
                else:
                    v = r[m]
                if v is not None and np.isfinite(v):
                    xs.append(r["cycle"])
                    ys.append(v)
            if xs:
                ax.plot(xs, ys, **marker_kw(s, opts, len(xs)))
            pdata["curves"].append((s.label, np.array(xs, float), np.array(ys, float)))
        if m == "CE":
            ax.axhline(100, color="black", lw=1, ls=(0, (3, 2)), zorder=0)
        ax.set_ylabel(yl)
        ax.set_xlabel(T(opts, "Cycle number", "循环圈数"))
        ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=8, steps=[1, 2, 5, 10]))
        panels.append(pdata)
    if dropped:
        notes.append("已去掉可能未完成的最后一圈：" + "、".join(dropped) + "（可在“更多设置”里勾选保留）")
    handles = [legend_marker(s, opts) for s in series]
    labels = [rich(s.label) for s in series]
    finalize(fig, axes, handles, labels, opts, rows)
    return FigureResult(fig, panels, notes, rc(opts["font_size"], opts.get("_cjk", False)), allp)


# ------------------------------------------------------------------ figure: voltage vs time
TIME_DIV = {"s": 1.0, "min": 60.0, "h": 3600.0, "d": 86400.0}


def fig_vt(series, opts):
    notes, panels = [], []
    by_cell = opts["t_arrange"] == "by_cell"
    allp = []
    if by_cell:
        series, allp = select_panels(series, lambda x: "cell:" + x.cell.path, lambda x: x.label, opts, notes)
    n = len(series) if by_cell else 1
    fig, axes, rows, cols = new_figure(max(n, 1), opts)
    u = opts["t_unit"]
    xl = T(opts, f"Time ({u})", f"时间 ({u})")
    yl = T(opts, "Voltage (V)", "电压 (V)")
    targets = list(zip(axes, series)) if by_cell else [(axes[0], s) for s in series]
    pdata = {"title": "", "xlabel": xl, "ylabel": yl, "curves": []}
    for ax, s in targets:
        x = s.cell.t / TIME_DIV[u]
        xd, yd = A.decimate(x, s.cell.V, 8000)
        kw = line_kw(s, opts, lw=opts["line_width"] * 0.6)
        if by_cell:
            kw["ls"] = "-"      # one curve per panel: dashes would only make it harder to read
        ax.plot(xd, yd, **kw)
        if by_cell:
            ax.set_title(rich(s.label), fontsize=13.5 * opts["font_size"] / 14)
            panels.append({"title": s.label, "xlabel": xl, "ylabel": yl, "curves": [(s.label, xd, yd)]})
        else:
            pdata["curves"].append((s.label, xd, yd))
    if not by_cell:
        panels.append(pdata)
    for k, ax in enumerate(axes):
        ax.set_xlabel(xl)
        if k % cols == 0:
            ax.set_ylabel(yl)
    apply_limits(axes, opts)
    handles = [] if by_cell else [legend_line(s, opts) for s in series]
    labels = [] if by_cell else [rich(s.label) for s in series]
    finalize(fig, axes, handles, labels, opts, rows)
    notes.append("电压–时间图为显示做了抽稀（保留尖峰与转折）；导出数据同为抽稀后的点")
    return FigureResult(fig, panels, notes, rc(opts["font_size"], opts.get("_cjk", False)), allp)


# ------------------------------------------------------------------ figure: dQ/dV
def dqdv_label(opts):
    u = opts["cap_unit"]
    unit = {"mAh": "mAh V$^{-1}$", "mAh/g": "mAh g$^{-1}$ V$^{-1}$", "mAh/cm2": "mAh cm$^{-2}$ V$^{-1}$",
            "%": "% V$^{-1}$"}[u]
    return f"dQ/dV ({unit})"


def fig_dqdv(series, opts):
    notes, panels = [], []
    cycles = parse_cycles(opts["d_cycles"]) or [2]
    kinds = _kinds(opts["d_show"])
    facs = {}
    for s in series:
        f, err = cap_factor(s, opts)
        if err:
            notes.append(err)
        else:
            facs[id(s)] = f
    use = [s for s in series if id(s) in facs]
    by_cell = opts["d_arrange"] == "by_cell"
    overlay = opts["d_arrange"] == "all"
    if overlay:
        n, allp = 1, []
    elif by_cell:
        cells_p, allp = select_panels(use, lambda x: "cell:" + x.cell.path, lambda x: x.label, opts, notes)
        n = len(cells_p)
    else:
        cyc_p, allp = select_panels(cycles, lambda c: f"cycle:{c}", lambda c: cycle_title(opts, c), opts, notes)
        n = len(cyc_p)
    fig, axes, rows, cols = new_figure(max(n, 1), opts)
    xl, yl = T(opts, "Voltage (V)", "电压 (V)"), dqdv_label(opts)
    dv = max(float(opts["d_dv_mV"]), 0.1) / 1000.0
    sm = int(opts["d_smooth"])
    colors = ramp(len(cycles))
    missing = []

    def curve(s, c, k):
        pr = A.profile(s.cell, c, k)
        if pr is None:
            return None
        x, y = A.dqdv(pr[0] * facs[id(s)], pr[1], dv, sm)
        return (x, y) if len(x) else None

    if overlay:
        ax = axes[0]
        pdata = {"title": T(opts, "All cells", "所有电池"), "xlabel": xl, "ylabel": yl, "curves": []}
        for s in use:
            for c, (ls, f) in zip(cycles, cycle_styles(len(cycles))):
                got = False
                for k in kinds:
                    r = curve(s, c, k)
                    if r:
                        got = True
                        ax.plot(r[0], r[1], color=tint(s.color, f), ls=ls, lw=opts["line_width"] * 0.8)
                        pdata["curves"].append((f"{s.label} | cycle {c} {k}", r[0], r[1]))
                if not got:
                    missing.append(f"{s.label} 第 {c} 圈")
        panels.append(pdata)
        handles, labels = overlay_legend(use, cycles, opts)
        if len(cycles) > len(CYCLE_LS):
            notes.append(f"{len(cycles)} 圈用同一颜色由浅到深区分（第 {cycles[0]} 圈最浅）")
    elif by_cell:
        for ax, s in zip(axes, cells_p):
            pdata = {"title": s.label, "xlabel": xl, "ylabel": yl, "curves": []}
            for c, col in zip(cycles, colors):
                got = False
                for k in kinds:
                    r = curve(s, c, k)
                    if r:
                        got = True
                        ax.plot(r[0], r[1], color=col, lw=opts["line_width"] * 0.8)
                        pdata["curves"].append((f"{s.label} | cycle {c} {k}", r[0], r[1]))
                if not got:
                    missing.append(f"{s.label} 第 {c} 圈")
            ax.set_title(rich(s.label), fontsize=13.5 * opts["font_size"] / 14)
            panels.append(pdata)
        handles = [Line2D([], [], color=col, lw=opts["line_width"]) for col in colors]
        labels = [cycle_title(opts, c) for c in cycles]
    else:
        for ax, c in zip(axes, cyc_p):
            pdata = {"title": cycle_title(opts, c), "xlabel": xl, "ylabel": yl, "curves": []}
            for s in use:
                got = False
                for k in kinds:
                    r = curve(s, c, k)
                    if r:
                        got = True
                        ax.plot(r[0], r[1], **line_kw(s, opts, lw=opts["line_width"] * 0.8))
                        pdata["curves"].append((f"{s.label} | {k}", r[0], r[1]))
                if not got:
                    missing.append(f"{s.label} 第 {c} 圈")
            ax.set_title(cycle_title(opts, c))
            panels.append(pdata)
        handles = [legend_line(s, opts) for s in use]
        labels = [rich(s.label) for s in use]
    for ax in axes:
        ax.axhline(0, color="#999999", lw=0.8, zorder=0)
        ax.set_xlabel(xl)
    for k, ax in enumerate(axes):
        if k % cols == 0:
            ax.set_ylabel(yl)
    apply_limits(axes, opts)
    if missing:
        notes.append("没有数据：" + "、".join(missing[:8]) + (" 等" if len(missing) > 8 else ""))
    notes.append(f"dQ/dV：每 {opts['d_dv_mV']:g} mV 取点差分，{sm} 点滑动平均；放电为负值")
    finalize(fig, axes, handles, labels, opts, rows)
    return FigureResult(fig, panels, notes, rc(opts["font_size"], opts.get("_cjk", False)), allp)


BUILDERS = {"profiles": fig_profiles, "cycling": fig_cycling, "vt": fig_vt, "dqdv": fig_dqdv}


def build(kind, series, opts) -> FigureResult:
    o = dict(DEFAULTS)
    o.update({k: v for k, v in (opts or {}).items()})
    cjk = o["lang"] == "zh" or has_cjk(o.get("footnote")) or any(has_cjk(s.label) for s in series)
    o["_cjk"] = cjk
    with matplotlib.rc_context(rc(o["font_size"], cjk)):
        if not series:
            fig = Figure(figsize=(o["panel_w_cm"] * CM, o["panel_h_cm"] * CM))
            FigureCanvasAgg(fig)
            return FigureResult(fig, [], ["请先添加数据文件"], rc(o["font_size"]))
        res = BUILDERS[kind](series, o)
    res.axes = [ax for ax in res.fig.axes if ax.get_visible()]
    res.cjk = cjk
    return res


def rich_plain(t) -> str:
    """Text for a menu or table: mathtext markup removed."""
    return re.sub(r"\$|\\mathrm|[{}]", "", t or "").replace("\\", "")


def panel_text(panel) -> str:
    """One sub-plot's data as tab-separated text (pastes into Excel / Origin): two columns
    per curve; row 1 = curve name, row 2 = axis titles with units."""
    clean = rich_plain

    def num(v):
        v = float(v)
        return f"{v:.7g}" if math.isfinite(v) else ""

    cols = []
    for name, x, y in panel["curves"]:
        cols.append([clean(name), clean(panel["xlabel"])] + [num(v) for v in x])
        cols.append([clean(name), clean(panel["ylabel"])] + [num(v) for v in y])
    if not cols:
        return ""
    n = max(len(c) for c in cols)
    return "\n".join("\t".join(c[r] if r < len(c) else "" for c in cols) for r in range(n)) + "\n"


def render_png(res: FigureResult, dpi: float) -> bytes:
    import io
    buf = io.BytesIO()
    with matplotlib.rc_context(res.rc):
        res.fig.savefig(buf, format="png", dpi=dpi)
    return buf.getvalue()


def vector_rc(res: FigureResult, path: str) -> dict:
    """rcParams for saving. PDF/EPS embed fonts as TrueType (Type 42: text stays editable),
    except when the figure has Chinese text set in a font with CFF outlines (macOS PingFang):
    those glyphs are embedded as Type 3, which every viewer draws correctly."""
    rc = dict(res.rc)
    if path.lower().endswith((".pdf", ".eps", ".ps")) and res.cjk:
        from .style import cjk_family, outline_is_cff
        fam = rc.get("font.family") or []
        cj = cjk_family(fam if isinstance(fam, (list, tuple)) else [fam])
        if cj and outline_is_cff(cj):
            rc["pdf.fonttype"] = rc["ps.fonttype"] = 3
    return rc


def save(res: FigureResult, path: str, dpi: int = 300):
    with matplotlib.rc_context(vector_rc(res, path)):
        res.fig.savefig(path, dpi=dpi)
