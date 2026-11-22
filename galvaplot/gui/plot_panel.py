"""Right panel: figure type, options, live preview and export buttons."""
from __future__ import annotations

import json
import os
import traceback

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication, QImage, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFrame,
                               QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMenu, QPlainTextEdit,
                               QPushButton, QSizePolicy, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from ..plotting import figures as F
from ..plotting.export import export_xlsx

KINDS = [("profiles", "充放电曲线"), ("cycling", "循环性能"), ("vt", "电压–时间"), ("dqdv", "dQ/dV")]
FILE_STEM = {"profiles": "voltage_profiles", "cycling": "cycling", "vt": "voltage_time", "dqdv": "dQdV"}
CAP_UNITS = [("mAh", "mAh"), ("mAh/g（比容量）", "mAh/g"), ("mAh/cm²（面容量）", "mAh/cm2"),
             ("%（相对参考圈）", "%")]


def _flt(text):
    t = (text or "").strip().replace(",", ".")
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


class PreviewLabel(QLabel):
    resized = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("previewImg")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setMinimumSize(320, 240)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.resized.emit()


ARRANGE_TIP = ("每圈一个子图：比较不同电池\n每个电池一个子图：比较同一电池的不同圈\n"
               "所有圈+所有电池：全部画在一张图里，颜色区分电池，线型区分圈数（超过 4 圈时用深浅区分）")


VT_ZERO_TIP = ("填了圈数时，横轴从哪里开始计时：\n"
               "每圈从 0 开始：各圈从 0 开始叠在一起比较\n"
               "从所选第一圈开始：所选各圈按先后连成一条，横轴从 0 开始\n"
               "测试开始：横轴是从测试开始算起的时间")
VT_ARRANGE_TIP = ("叠加：所有电池画在一张图里\n每个电池一个子图\n"
                  "每圈一个子图：要先填圈数，每圈一张图比较不同电池")


class PlotPanel(QWidget):
    message = Signal(str)

    def __init__(self, settings: QSettings, get_series, is_loading):
        super().__init__()
        self.settings = settings
        self.get_series = get_series
        self.is_loading = is_loading
        self.result = None
        self.series_cache = []
        self.opts = dict(F.DEFAULTS)
        self.opts["dpi"] = 300
        try:
            saved = json.loads(settings.value("opts", "{}") or "{}")
            self.opts.update({k: v for k, v in saved.items() if k in self.opts})
        except (TypeError, ValueError):
            pass
        self.kind = settings.value("kind", "profiles")
        if self.kind not in dict(KINDS):
            self.kind = "profiles"

        self._redraw_timer = QTimer(self)
        self._redraw_timer.setSingleShot(True)
        self._redraw_timer.setInterval(250)
        self._redraw_timer.timeout.connect(self.redraw)
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(120)
        self._render_timer.timeout.connect(self._render_preview)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        # ---- top bar: figure type + actions
        top = QHBoxLayout()
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        seg = QHBoxLayout()
        seg.setSpacing(0)
        for k, (key, text) in enumerate(KINDS):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setObjectName("segFirst" if k == 0 else "segLast" if k == len(KINDS) - 1 else "seg")
            b.setChecked(key == self.kind)
            b.clicked.connect(lambda _=False, key=key: self.set_kind(key))
            self.group.addButton(b)
            seg.addWidget(b)
        top.addLayout(seg)
        top.addStretch(1)
        lay.addLayout(top)
        self.copy_btn = QPushButton("复制图片")
        self.copy_btn.setToolTip("复制 300 dpi 图片到剪贴板，可直接粘贴到 PPT / Word")
        self.save_btn = QPushButton("保存图片…")
        self.save_btn.setObjectName("primary")
        self.save_btn.setToolTip("保存为 PNG / SVG / PDF / EPS / TIFF")
        self.data_btn = QPushButton("导出数据…")
        self.data_btn.setToolTip("把这张图的数据和每个电池的逐圈数据导出为 Excel（可直接导入 Origin）")
        self.all_btn = QPushButton("一键导出全部")
        self.all_btn.setToolTip("按当前设置把 4 种图（PNG + SVG）和数据一次性保存到一个文件夹")
        self.copy_btn.clicked.connect(self.copy_image)
        self.save_btn.clicked.connect(self.save_image)
        self.data_btn.clicked.connect(self.export_data)
        self.all_btn.clicked.connect(self.export_all)

        # ---- options card
        self.card = self._build_options()
        lay.addWidget(self.card)

        # ---- preview
        # preview card: sub-plot switches (a, b, c ...) at the top left, figure below
        self.hidden = {k: set() for k, _ in KINDS}      # sub-plots switched off, per figure type
        self._panel_keys, self._panel_btns = [], []
        card = QFrame()
        card.setObjectName("preview")
        pv = QVBoxLayout(card)
        pv.setContentsMargins(10, 8, 10, 8)
        pv.setSpacing(2)
        self.panel_bar = QWidget()
        pb = QHBoxLayout(self.panel_bar)
        pb.setContentsMargins(0, 0, 0, 0)
        pb.setSpacing(4)
        lab = QLabel("显示子图")
        lab.setObjectName("hint")
        pb.addWidget(lab)
        self.panel_btn_row = QHBoxLayout()
        self.panel_btn_row.setSpacing(4)
        pb.addLayout(self.panel_btn_row)
        show_all = QPushButton("全部")
        show_all.setObjectName("link")
        show_all.setToolTip("显示全部子图")
        show_all.clicked.connect(self._show_all_panels)
        pb.addWidget(show_all)
        pb.addStretch(1)
        self.panel_bar.setVisible(False)
        pv.addWidget(self.panel_bar)
        self.preview = PreviewLabel()
        self.preview.resized.connect(lambda: self._render_timer.start())
        self.preview.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.preview.customContextMenuRequested.connect(self._preview_menu)
        self.preview.setToolTip("右键：复制某个子图的数据或图片、只显示某个子图等")
        pv.addWidget(self.preview, 1)
        lay.addWidget(card, 1)
        self.notes = QLabel("")
        self.notes.setObjectName("notes")
        self.notes.setWordWrap(True)
        self.notes.setMinimumWidth(120)
        bottom = QHBoxLayout()
        bottom.addWidget(self.notes, 1)
        for b in (self.copy_btn, self.data_btn, self.all_btn, self.save_btn):
            bottom.addWidget(b)
        lay.addLayout(bottom)

        self.set_kind(self.kind)
        self._update_enabled()

    def _build_options(self):
        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 10, 14, 10)
        cl.setSpacing(8)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._opts_profiles())
        self.stack.addWidget(self._opts_cycling())
        self.stack.addWidget(self._opts_vt())
        self.stack.addWidget(self._opts_dqdv())
        self.stack.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        cl.addWidget(self.stack)

        common = QHBoxLayout()
        self.unit_label = QLabel("容量单位")
        self.unit_label.setToolTip("mAh/g 需在左侧填质量；mAh/cm² 需在“更多设置”填面积；% 以参考圈放电容量为 100%")
        self.unit_combo = self._combo("cap_unit", CAP_UNITS)
        common.addWidget(self.unit_label)
        common.addWidget(self.unit_combo)
        common.addSpacing(14)
        common.addWidget(QLabel("图中文字"))
        common.addWidget(self._combo("lang", [("English", "en"), ("中文", "zh")]))
        common.addStretch(1)
        self.foot = QPlainTextEdit(self.opts.get("footnote") or "")
        self.foot.setPlaceholderText("可写测试条件，例如：Cathode: NCM811; Electrolyte: 1 M LiPF_{6} in EC/DMC; 0.1 C, 25 °C（可换行）")
        self.foot.setFixedHeight(46)
        self.foot.setMinimumWidth(150)
        self.foot.setToolTip("显示在图的最下方，可换行。下标写 LiPF_{6}，上标写 Li^{+}")
        self.foot.textChanged.connect(lambda: self._set("footnote", self.foot.toPlainText()))
        self.more_btn = QPushButton("更多设置…")
        self.more_btn.setObjectName("link")
        self.more_btn.setToolTip("字号、尺寸、坐标范围、图例、库仑效率定义、参考圈、面积、分辨率")
        self.more_btn.clicked.connect(self._show_more)
        common.addWidget(self.more_btn)
        cl.addLayout(common)
        foot_row = QHBoxLayout()
        foot_lab = QLabel("图下方注释")
        foot_lab.setToolTip(self.foot.toolTip())
        foot_row.addWidget(foot_lab)
        foot_row.addWidget(self.foot, 1)
        cl.addLayout(foot_row)

        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)   # never squeezed
        self.more_dlg = QDialog(self)
        self.more_dlg.setWindowTitle("更多设置")
        dl = QVBoxLayout(self.more_dlg)
        dl.addWidget(self._advanced())
        tip = QLabel("修改后主窗口的预览会立即更新")
        tip.setObjectName("hint")
        dl.addWidget(tip)
        return card

    # ------------------------------------------------------------ option widgets
    def _set(self, key, value):
        self.opts[key] = value
        self.settings.setValue("opts", json.dumps(self.opts))
        self.schedule()

    def _combo(self, key, items, tip=None):
        w = QComboBox()
        if tip:
            w.setToolTip(tip)
        for text, val in items:
            w.addItem(text, val)
        vals = [v for _, v in items]
        if self.opts.get(key) in vals:
            w.setCurrentIndex(vals.index(self.opts[key]))
        w.currentIndexChanged.connect(lambda _i: self._set(key, w.currentData()))
        return w

    def _line(self, key, placeholder, width=None, tip=None, as_float=False):
        v = self.opts.get(key)
        w = QLineEdit("" if v is None else str(v))
        w.setPlaceholderText(placeholder)
        if width:
            w.setFixedWidth(width)
        if tip:
            w.setToolTip(tip)
        if as_float:
            w.textChanged.connect(lambda t: self._set(key, _flt(t)))
        else:
            w.textChanged.connect(lambda t: self._set(key, t))
        return w

    def _spin(self, key, lo, hi, auto_text=None, tip=None):
        w = QSpinBox()
        w.setRange(lo, hi)
        if auto_text:
            w.setSpecialValueText(auto_text)
        v = self.opts.get(key)
        w.setValue(int(v) if v else lo)
        if tip:
            w.setToolTip(tip)
        w.valueChanged.connect(lambda x: self._set(key, (None if (auto_text and x == lo) else x)))
        return w

    def _dspin(self, key, lo, hi, step, dec, suffix="", tip=None):
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setSingleStep(step)
        w.setDecimals(dec)
        if suffix:
            w.setSuffix(suffix)
        w.setValue(float(self.opts.get(key) or lo))
        if tip:
            w.setToolTip(tip)
        w.valueChanged.connect(lambda x: self._set(key, x))
        return w

    def _check(self, key, text, tip=None):
        w = QCheckBox(text)
        w.setChecked(bool(self.opts.get(key)))
        if tip:
            w.setToolTip(tip)
        w.toggled.connect(lambda on: self._set(key, on))
        return w

    @staticmethod
    def _row(*widgets):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        for x in widgets:
            if x == "|":
                h.addSpacing(14)
            elif isinstance(x, str):
                h.addWidget(QLabel(x))
            else:
                h.addWidget(x)
        h.addStretch(1)
        return w

    def _opts_profiles(self):
        return self._row("圈数", self._line("p_cycles", "如 1, 2, 5 或 1-10", 150,
                                             "要画的循环圈数，用逗号分隔，可写范围 1-10"),
                         "|", "显示", self._combo("p_show", [("充电 + 放电", "both"), ("仅放电", "discharge"), ("仅充电", "charge")]),
                         "|", "排布", self._combo("p_arrange", [("每圈一个子图", "by_cycle"), ("每个电池一个子图", "by_cell"),
                                                        ("所有圈+所有电池", "all")],
                                                    ARRANGE_TIP))

    def _opts_cycling(self):
        box = QWidget()
        g = QGridLayout(box)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(4)
        g.addWidget(QLabel("指标"), 0, 0)
        self.metric_boxes = {}
        order = ["dchg_cap", "chg_cap", "CE", "EE", "retention", "Vavg_dchg", "Vavg_chg", "dV"]
        for k, key in enumerate(order):
            cb = QCheckBox(F.METRIC_ZH_SHORT[key])
            cb.setChecked(key in self.opts["c_metrics"])
            cb.toggled.connect(self._metrics_changed)
            if key == "dV":
                cb.setToolTip("平均充电电压 − 平均放电电压（电压滞后/极化）")
            if key == "retention":
                cb.setToolTip("放电容量 ÷ 参考圈放电容量（默认首次放电，可在“更多设置”里改）")
            self.metric_boxes[key] = cb
            g.addWidget(cb, k // 4, 1 + k % 4)
        hint = QLabel("（选 1–4 个效果最好）")
        hint.setObjectName("hint")
        rng = self._row("圈数范围", self._spin("c_from", 0, 100000, "从头"), "到", self._spin("c_to", 0, 100000, "最后"), hint)
        g.addWidget(rng, 2, 0, 1, 6)
        g.setColumnStretch(5, 1)
        return box

    def _metrics_changed(self):
        order = ["dchg_cap", "chg_cap", "CE", "EE", "retention", "Vavg_dchg", "Vavg_chg", "dV"]
        sel = [k for k in order if self.metric_boxes[k].isChecked()]
        if not sel:
            self.message.emit("至少选一个指标")
        self._set("c_metrics", sel)

    def _opts_vt(self):
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        cyc = self._line("t_cycles", "留空 = 整个测试", 150,
                         "只画这几圈的电压–时间曲线，如 2 或 1, 50, 100 或 1-5；留空画整个测试")
        self.t_zero = self._combo("t_zero", [(t, k) for k, t in F.T_ZERO.items()], VT_ZERO_TIP)
        v.addWidget(self._row("圈数", cyc,
                              "|", "排布", self._combo("t_arrange", [("叠加", "overlay"), ("每个电池一个子图", "by_cell"),
                                                              ("每圈一个子图", "by_cycle")], VT_ARRANGE_TIP)))
        self.t_zero_label = QLabel("时间起点")
        self.t_zero_label.setToolTip(VT_ZERO_TIP)
        v.addWidget(self._row("时间单位", self._combo("t_unit", [("小时 h", "h"), ("分钟 min", "min"), ("秒 s", "s"), ("天 d", "d")]),
                              "|", self.t_zero_label, self.t_zero))
        cyc.textChanged.connect(self._vt_zero_enabled)
        self._vt_zero_enabled(cyc.text())
        return box

    def _vt_zero_enabled(self, text):
        on = bool(F.parse_cycles(text))
        self.t_zero.setEnabled(on)
        self.t_zero_label.setEnabled(on)

    def _opts_dqdv(self):
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        v.addWidget(self._row("圈数", self._line("d_cycles", "如 2, 10", 110),
                              "|", "显示", self._combo("d_show", [("充电 + 放电", "both"), ("仅放电", "discharge"), ("仅充电", "charge")]),
                              "|", "排布", self._combo("d_arrange", [("每圈一个子图", "by_cycle"), ("每个电池一个子图", "by_cell"),
                                                        ("所有圈+所有电池", "all")], ARRANGE_TIP)))
        v.addWidget(self._row("电压间隔", self._dspin("d_dv_mV", 0.5, 100, 0.5, 1, " mV", "每隔多少 mV 取一个点做差分；越大越平滑"),
                              "|", "平滑点数", self._spin("d_smooth", 1, 51, None, "滑动平均点数，1 = 不平滑")))
        return box

    def _advanced(self):
        box = QWidget()
        g = QGridLayout(box)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(6)
        xr = self._row(self._line("xmin", "自动", 64, as_float=True), "–", self._line("xmax", "自动", 64, as_float=True))
        yr = self._row(self._line("ymin", "自动", 64, as_float=True), "–", self._line("ymax", "自动", 64, as_float=True))
        pw, ph = self._dspin("panel_w_cm", 5, 40, 0.5, 1, " cm"), self._dspin("panel_h_cm", 4, 40, 0.5, 1, " cm")
        pw.setFixedWidth(90)
        ph.setFixedWidth(90)
        size = self._row(pw, "×", ph)
        items = [
            ("字号", self._dspin("font_size", 8, 28, 0.5, 1, " pt", "坐标轴数字的字号；其余文字按比例缩放")),
            ("每个子图尺寸", size),
            ("线宽", self._dspin("line_width", 0.5, 5, 0.25, 2)),
            ("图例", self._combo("legend", [("自动", "auto"), ("图内", "inside"), ("图下方", "below"), ("不显示", "none")])),
            ("X 范围", xr),
            ("Y 范围", yr),
            ("库仑效率", self._combo("ce_mode", [("放电 ÷ 充电", "dchg/chg"), ("充电 ÷ 放电", "chg/dchg")],
                                    "放电 ÷ 充电：正极半电池、全电池、Li/Na–Cl₂ 等\n充电 ÷ 放电：负极半电池（先嵌锂/放电）")),
            ("参考圈", self._spin("ref_cycle", 0, 100000, "首次放电", "“相对 %”和“容量保持率”以这一圈的放电容量为 100%")),
            ("电极面积", self._line("area_cm2", "cm²，面容量用", 110, as_float=True)),
            ("导出分辨率", self._spin("dpi", 100, 1200, None, "PNG/TIFF 的 dpi")),
        ]
        for k, (lab, w) in enumerate(items):
            r, c = divmod(k, 2)
            if isinstance(w, (QSpinBox, QDoubleSpinBox)):
                w.setFixedWidth(110)
            g.addWidget(QLabel(lab), r, 2 * c)
            g.addWidget(w, r, 2 * c + 1, Qt.AlignmentFlag.AlignLeft)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)
        r = (len(items) + 1) // 2
        g.addWidget(self._row(self._check("letters", "多子图时加 a/b/c 编号"), "|",
                              self._check("include_last", "保留可能未完成的最后一圈",
                                          "默认去掉测试还在进行（或中途停止）的最后一圈，避免曲线末端出现假的掉点")),
                    r, 0, 1, 4)
        reset = QPushButton("恢复默认设置")
        reset.setObjectName("link")
        reset.clicked.connect(self._reset)
        g.addWidget(reset, r + 1, 3, Qt.AlignmentFlag.AlignRight)
        return box

    def _show_more(self):
        self.more_dlg.show()
        self.more_dlg.raise_()
        self.more_dlg.activateWindow()

    def _reset(self):
        self.settings.remove("opts")
        self.opts = dict(F.DEFAULTS)
        self.opts["dpi"] = 300
        lay = self.layout()
        idx = lay.indexOf(self.card)
        old, old_dlg = self.card, self.more_dlg
        self.card = self._build_options()
        old_dlg.close()
        old_dlg.deleteLater()
        lay.insertWidget(idx, self.card)
        old.setParent(None)
        old.deleteLater()
        self.set_kind(self.kind)
        self._show_more()
        self.message.emit("已恢复默认设置")

    # ------------------------------------------------------------ state
    def set_kind(self, key):
        self.kind = key
        for btn, (k, _t) in zip(self.group.buttons(), KINDS):
            btn.setChecked(k == key)
        self.settings.setValue("kind", key)
        self.stack.setCurrentIndex([k for k, _ in KINDS].index(key))
        # only the visible page counts for the height (no empty rows, no clipped rows)
        for i in range(self.stack.count()):
            self.stack.widget(i).setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Preferred if i == self.stack.currentIndex() else QSizePolicy.Policy.Ignored)
        self.stack.updateGeometry()
        if hasattr(self, "card"):
            self.card.updateGeometry()
        uses_cap = key in ("profiles", "cycling", "dqdv")
        self.unit_label.setEnabled(uses_cap)
        self.unit_combo.setEnabled(uses_cap)
        self.schedule()

    def schedule(self):
        self._redraw_timer.start()

    def _update_enabled(self, has=False):
        for b in (self.copy_btn, self.save_btn, self.data_btn, self.all_btn):
            b.setEnabled(has)

    def redraw(self):
        series = self.get_series()
        self.series_cache = series
        if not series:
            self.result = None
            self._update_enabled(False)
            self.preview.setPixmap(QPixmap())
            self.preview.setText("正在读取文件…" if self.is_loading() else
                                 "← 先把 .cex（蓝电）或 .ndax（新威）文件拖进来\n\n（或点左上角“示例数据”试一试）")
            self.preview.setStyleSheet("color: #8a93a0; font-size: 16px;")
            self.notes.setText("")
            self.panel_bar.setVisible(False)
            return
        try:
            res = F.build(self.kind, series, self._opts_for(self.kind))
        except Exception as e:
            traceback.print_exc()
            self.result = None
            self._update_enabled(False)
            self.preview.setPixmap(QPixmap())
            self.preview.setText(f"作图出错：{e}\n\n请检查设置（例如坐标范围），或在 GitHub 提交 issue。")
            return
        self.preview.setStyleSheet("")
        self.result = res
        self._update_enabled(True)
        notes = list(res.notes)
        self._update_panel_bar(res.all_panels)
        n_all = len(res.all_panels)
        n_off = len(self.hidden[self.kind])
        if n_all >= 2 and n_off:
            notes.insert(0, f"显示 {n_all - n_off} / {n_all} 个子图（复制、保存、导出的也是这几个，编号重新从 a 排）")
        if self.is_loading():
            notes.insert(0, "还有文件正在读取…")
        self.notes.setText("　·　".join(notes))
        self._render_preview()

    # ------------------------------------------------------------ sub-plot switches
    def _opts_for(self, kind):
        o = dict(self.opts)
        o["hidden_panels"] = sorted(self.hidden[kind])
        return o

    def _update_panel_bar(self, all_panels):
        keys = [k for k, _ in all_panels]
        self.hidden[self.kind] &= set(keys)          # forget switches for sub-plots that no longer exist
        if keys != self._panel_keys:
            for b in self._panel_btns:
                self.panel_btn_row.removeWidget(b)
                b.deleteLater()
            self._panel_btns = []
            for i, (key, _title) in enumerate(all_panels):
                b = QPushButton(F.LETTERS[i])
                b.setObjectName("panelBtn")
                b.setCheckable(True)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.toggled.connect(lambda on, key=key: self._toggle_panel(key, on))
                self.panel_btn_row.addWidget(b)
                self._panel_btns.append(b)
            self._panel_keys = keys
        for b, (key, title) in zip(self._panel_btns, all_panels):
            b.blockSignals(True)
            b.setChecked(key not in self.hidden[self.kind])
            b.blockSignals(False)
            b.setToolTip(f"{title}\n点击显示/隐藏这个子图")
        self.panel_bar.setVisible(len(keys) >= 2)

    def _toggle_panel(self, key, on):
        h = self.hidden[self.kind]
        if on:
            h.discard(key)
        else:
            if sum(1 for k in self._panel_keys if k not in h) <= 1:   # keep at least one sub-plot
                btn = self._panel_btns[self._panel_keys.index(key)]
                btn.blockSignals(True)
                btn.setChecked(True)
                btn.blockSignals(False)
                self.message.emit("至少要显示一个子图")
                return
            h.add(key)
        self.schedule()

    def _show_all_panels(self):
        self.hidden[self.kind].clear()
        self.schedule()

    def _render_preview(self):
        if self.result is None:
            return
        W, H = self.result.fig.get_size_inches()
        m = 16
        aw, ah = max(self.preview.width() - m, 50), max(self.preview.height() - m, 50)
        dpr = self.devicePixelRatioF()
        dpi = max(20.0, min(aw / W, ah / H, 220.0)) * dpr
        img = QImage()
        img.loadFromData(F.render_png(self.result, dpi), "PNG")
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(dpr)
        self.preview.setText("")
        self.preview.setPixmap(pm)

    # ------------------------------------------------------------ right-click menu on the preview
    def _panel_at(self, pos):
        """Index (into result.panels) of the sub-plot under a point of the preview, or None."""
        res = self.result
        pm = self.preview.pixmap()
        if res is None or pm is None or pm.isNull() or not res.panels or len(res.axes) != len(res.panels):
            return None
        dpr = pm.devicePixelRatio() or 1.0
        pw, ph = pm.width() / dpr, pm.height() / dpr
        cr = self.preview.contentsRect()
        fx = (pos.x() - cr.x() - (cr.width() - pw) / 2) / pw
        fy = 1 - (pos.y() - cr.y() - (cr.height() - ph) / 2) / ph
        if not (0 <= fx <= 1 and 0 <= fy <= 1):
            return None
        if len(res.axes) == 1:
            return 0
        fig = res.fig
        W, H = fig.bbox.width, fig.bbox.height
        try:
            renderer = fig.canvas.get_renderer()
            boxes = [ax.get_tightbbox(renderer) for ax in res.axes]   # includes tick labels and titles
        except Exception:
            boxes = [ax.get_window_extent() for ax in res.axes]
        mx, my = 0.2 * fig.dpi / W, 0.2 * fig.dpi / H        # 0.2 inch of slack around each panel
        hits = [i for i, b in enumerate(boxes)
                if b.x0 / W - mx <= fx <= b.x1 / W + mx and b.y0 / H - my <= fy <= b.y1 / H + my]
        if not hits:
            return None

        def dist(i):        # overlapping boxes: the panel whose plot area is closest
            p = res.axes[i].get_position()
            return max(p.x0 - fx, 0, fx - p.x1) + max(p.y0 - fy, 0, fy - p.y1)
        return min(hits, key=dist)

    def _shown_keys(self):
        keys = [k for k, _ in (self.result.all_panels if self.result else [])]
        return [k for k in keys if k not in self.hidden[self.kind]] or keys

    def _single_panel(self, i):
        """FigureResult with only sub-plot i (no letter), or the current one if it has one panel."""
        res = self.result
        if len(res.panels) == 1:
            return res
        shown = self._shown_keys()
        if i >= len(shown):
            return None
        o = self._opts_for(self.kind)
        o["hidden_panels"] = [k for k, _ in res.all_panels if k != shown[i]]
        try:
            return F.build(self.kind, self.series_cache, o)
        except Exception as e:
            traceback.print_exc()
            self.message.emit(f"作图出错：{e}")
            return None

    def _panel_name(self, i):
        res = self.result
        title = res.panels[i].get("title") or ""
        return f"{F.LETTERS[i]} 图" if len(res.panels) > 1 else (title or "此图")

    def copy_panel_data(self, i):
        p = self.result.panels[i]
        text = F.panel_text(p)
        if not text:
            self.message.emit("这个子图没有数据")
            return
        QGuiApplication.clipboard().setText(text)
        n = len(p["curves"])
        self.message.emit(f"已复制 {self._panel_name(i)}的数据（{n} 条曲线，每条两列），可直接粘贴到 Excel / Origin")

    def _copy_panel_image(self, i):
        r = self._single_panel(i)
        if r is not None:
            self.copy_image(r)
            self.message.emit(f"已复制 {self._panel_name(i)}（单独一张，不带字母编号），可直接粘贴到 PPT / Word")

    def _save_panel(self, i):
        r = self._single_panel(i)
        if r is not None:
            self.save_image(r, f"_{F.LETTERS[i]}")

    def _only_panel(self, i):
        shown = self._shown_keys()
        if i < len(shown):
            self.hidden[self.kind] = {k for k, _ in self.result.all_panels if k != shown[i]}
            self.schedule()

    def _hide_panel(self, i):
        shown = self._shown_keys()
        if i < len(shown) and len(shown) > 1:
            self.hidden[self.kind].add(shown[i])
            self.schedule()

    def _preview_menu(self, pos):
        m = self._build_preview_menu(pos)
        if m is not None:
            m.exec(self.preview.mapToGlobal(pos))

    def _build_preview_menu(self, pos):
        if not self.result or not self.result.panels:
            return None
        i = self._panel_at(pos)
        multi = len(self.result.panels) > 1
        m = QMenu(self)
        if i is not None:
            if multi:
                head = m.addAction(f"{F.LETTERS[i]} 图 · {F.rich_plain(self.result.panels[i].get('title') or '')}")
                head.setEnabled(False)
            m.addAction("复制此子图数据" if multi else "复制数据", lambda: self.copy_panel_data(i))
            if multi:
                m.addAction("复制此子图图片", lambda: self._copy_panel_image(i))
                m.addAction("保存此子图…", lambda: self._save_panel(i))
                m.addSeparator()
                m.addAction("只显示此子图", lambda: self._only_panel(i))
                m.addAction("隐藏此子图", lambda: self._hide_panel(i))
        elif multi:
            hint = m.addAction("（在某个子图上右键，可单独复制它的数据）")
            hint.setEnabled(False)
        if self.hidden[self.kind] and len(self.result.all_panels) >= 2:
            m.addAction("显示全部子图", self._show_all_panels)
        m.addSeparator()
        m.addAction("复制整张图片" if multi else "复制图片", self.copy_image)
        m.addAction("保存图片…", self.save_image)
        m.addAction("导出全部数据（Excel）…", self.export_data)
        m.addSeparator()
        m.addAction("更多设置（坐标范围、字号、图例…）", self._show_more)
        return m

    # ------------------------------------------------------------ actions
    def copy_image(self, res=None):
        res = res or self.result
        if not res:
            return
        img = QImage()
        img.loadFromData(F.render_png(res, int(self.opts.get("dpi") or 300)), "PNG")
        QGuiApplication.clipboard().setImage(img)
        self.message.emit("已复制到剪贴板，可直接粘贴到 PPT / Word")

    def _ask_path(self, title, name, filters):
        last = self.settings.value("save_dir", os.path.expanduser("~/Desktop"))
        path, flt = QFileDialog.getSaveFileName(self, title, os.path.join(str(last), name), filters)
        if path:
            self.settings.setValue("save_dir", os.path.dirname(path))
        return path, flt

    def save_image(self, res=None, suffix=""):
        res = res or self.result
        if not res:
            return
        path, flt = self._ask_path("保存图片", FILE_STEM[self.kind] + suffix + ".png",
                                   "PNG 图片 (*.png);;SVG 矢量图 (*.svg);;PDF (*.pdf);;EPS 矢量图 (*.eps);;TIFF (*.tif)")
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in (".png", ".svg", ".pdf", ".eps", ".tif", ".tiff"):
            ext = {"SVG": ".svg", "PDF": ".pdf", "EPS": ".eps", "TIFF": ".tif"}.get(flt.split()[0] if flt else "", ".png")
            path += ext
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            F.save(res, path, dpi=int(self.opts.get("dpi") or 300))
        except Exception as e:
            self.message.emit(f"保存失败：{e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.message.emit(f"已保存：{path}")

    def export_data(self):
        if not self.result:
            return
        path, _ = self._ask_path("导出数据", FILE_STEM[self.kind] + "_data.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            export_xlsx(path, self.result, self.series_cache, self.opts)
        except Exception as e:
            self.message.emit(f"导出失败：{e}")
            return
        self.message.emit(f"已导出：{path}")

    def export_all(self):
        series = self.get_series()
        if not series:
            return
        last = self.settings.value("save_dir", os.path.expanduser("~/Desktop"))
        folder = QFileDialog.getExistingDirectory(self, "选择保存文件夹", str(last))
        if not folder:
            return
        self.settings.setValue("save_dir", folder)
        dpi = int(self.opts.get("dpi") or 300)
        done, failed = [], []
        for k, (key, text) in enumerate(KINDS, start=1):
            stem = os.path.join(folder, f"{k}_{FILE_STEM[key]}")
            try:
                res = F.build(key, series, self._opts_for(key))
                F.save(res, stem + ".png", dpi=dpi)
                F.save(res, stem + ".svg", dpi=dpi)
                export_xlsx(stem + "_data.xlsx", res, series, self.opts)
                done.append(text)
            except Exception as e:
                traceback.print_exc()
                failed.append(f"{text}（{e}）")
        msg = f"已导出 {len(done)} 种图到 {folder}"
        if failed:
            msg += "；失败：" + "、".join(failed)
        self.message.emit(msg)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
