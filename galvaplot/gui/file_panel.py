"""Left panel: drop zone + table of loaded files (show, colour, line style, name, mass)."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile

from PySide6.QtCore import QObject, QRunnable, QSettings, QSize, Qt, QThreadPool, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QColorDialog, QComboBox, QFileDialog, QFrame,
                               QHBoxLayout, QHeaderView, QLabel, QMenu, QMessageBox, QPushButton,
                               QStackedWidget, QTableWidget, QTableWidgetItem, QToolButton,
                               QVBoxLayout, QWidget)

from .. import MAX_FILES
from ..plotting.figures import Series
from ..plotting.style import LINESTYLE_LABELS, PALETTE, PALETTE_NAMES
from ..readers import SUPPORTED_EXT, load_file
from ..textfmt import default_name, shorten_names

FILE_FILTER = "电池数据 (*.cex *.ndax *.xlsx *.xls *.csv *.txt);;蓝电 .cex (*.cex);;新威 .ndax (*.ndax);;所有文件 (*)"
NAME_TIP = ("双击修改名称（会显示在图例里）。\n"
            "下标：AlCl_{3} → AlCl₃　上标：Li^{+} → Li⁺\n"
            "也可以直接写 LaTeX，例如 $\\mathrm{LiPF_6}$")


class _Signals(QObject):
    done = Signal(str, object, str)


class _LoadTask(QRunnable):
    def __init__(self, path, signals):
        super().__init__()
        self.path, self.signals = path, signals

    def run(self):
        try:
            cell = load_file(self.path)
            self.signals.done.emit(self.path, cell, "")
        except Exception as e:  # report any reader failure to the user, never crash
            self.signals.done.emit(self.path, None, f"{type(e).__name__}: {e}" if not str(e).strip() else str(e))


class Item:
    def __init__(self, path, color):
        self.path = path
        self.cell = None
        self.default = default_name(path)
        self.label = self.default
        self.color = color
        self.ls = "solid"
        self.mass = None
        self.visible = True
        self.loading = True


def _swatch(color, size=16):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor("#00000030"), 1))
    p.setBrush(QColor(color))
    p.drawRoundedRect(1, 1, size - 2, size - 2, 4, 4)
    p.end()
    return QIcon(pm)


class DropZone(QFrame):
    clicked = Signal()

    def __init__(self, big=True):
        super().__init__()
        self.setObjectName("dropzone")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if big:
            icon = QLabel("⤓")
            icon.setStyleSheet("font-size: 40px; color: #8a97ab;")
            icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            t1 = QLabel("把电池数据文件拖到这里")
            t1.setStyleSheet("font-size: 16px; font-weight: 600;")
            t1.setAlignment(Qt.AlignmentFlag.AlignCenter)
            t2 = QLabel(f"蓝电 .cex · 新威 .ndax\n或点击选择文件 · 最多 {MAX_FILES} 个，也可以拖入整个文件夹\n导出的 Excel / CSV 也能读（实验功能）")
            t2.setObjectName("muted")
            t2.setWordWrap(True)
            t2.setAlignment(Qt.AlignmentFlag.AlignCenter)
            for w in (icon, t1, t2):
                lay.addWidget(w)
            self.setMinimumHeight(220)
        else:
            t = QLabel("＋ 拖入或点击添加文件")
            t.setObjectName("muted")
            t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(t)
            lay.setContentsMargins(6, 6, 6, 6)

    def mousePressEvent(self, e):
        self.clicked.emit()

    def set_active(self, on):
        self.setProperty("active", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class FilePanel(QWidget):
    changed = Signal()
    message = Signal(str)

    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        self.items: list[Item] = []
        self.pool = QThreadPool.globalInstance()
        self.signals = _Signals()
        self.signals.done.connect(self._loaded)
        self._building = False

        card = QFrame()
        card.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        head = QHBoxLayout()
        t = QLabel("数据文件")
        t.setObjectName("title")
        self.count = QLabel(f"0 / {MAX_FILES}")
        self.count.setObjectName("muted")
        self.demo_btn = QPushButton("示例数据")
        self.demo_btn.setObjectName("link")
        self.demo_btn.setToolTip("加载 4 个合成的示例文件，先试试效果")
        self.demo_btn.clicked.connect(self.load_demo)
        add = QPushButton("添加文件…")
        add.setObjectName("small")
        add.clicked.connect(self.browse)
        head.addWidget(t)
        head.addWidget(self.count)
        head.addStretch(1)
        head.addWidget(self.demo_btn)
        head.addWidget(add)
        lay.addLayout(head)

        self.stack = QStackedWidget()
        self.big_drop = DropZone(big=True)
        self.big_drop.clicked.connect(self.browse)
        self.stack.addWidget(self.big_drop)

        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(6)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["显示", "颜色", "线型", "名称", "质量 mg"])
        self.table.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.table.setWordWrap(False)
        hh = self.table.horizontalHeader()
        for c, w in ((0, 38), (1, 40), (2, 70), (4, 64)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(c, w)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeaderItem(4).setToolTip("活性物质质量（mg），用于计算比容量 mAh/g；不需要可留空")
        self.table.horizontalHeaderItem(3).setToolTip(NAME_TIP)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked |
                                   QAbstractItemView.EditTrigger.EditKeyPressed |
                                   QAbstractItemView.EditTrigger.SelectedClicked)
        self.table.itemChanged.connect(self._item_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        pl.addWidget(self.table, 1)
        hint = QLabel("双击名称可修改（图例即用此名）· 质量用于比容量 · 右键更多操作")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        pl.addWidget(hint)

        btns = QHBoxLayout()
        self.up_btn = QPushButton("上移")
        self.down_btn = QPushButton("下移")
        self.del_btn = QPushButton("移除")
        self.short_btn = QPushButton("精简名称")
        self.short_btn.setToolTip("去掉所有文件名里都有的部分和日期，例如\n"
                                  "20261101-NCM811-EC-DMC-cell1 → DMC-cell1\n"
                                  "右键某一行可以恢复原名")
        for b in (self.up_btn, self.down_btn, self.del_btn, self.short_btn):
            b.setObjectName("small")
        self.up_btn.clicked.connect(lambda: self._move(-1))
        self.down_btn.clicked.connect(lambda: self._move(1))
        self.del_btn.clicked.connect(self._remove_selected)
        self.short_btn.clicked.connect(self._shorten)
        btns.addWidget(self.up_btn)
        btns.addWidget(self.down_btn)
        btns.addWidget(self.del_btn)
        btns.addStretch(1)
        btns.addWidget(self.short_btn)
        pl.addLayout(btns)
        self.small_drop = DropZone(big=False)
        self.small_drop.clicked.connect(self.browse)
        pl.addWidget(self.small_drop)
        self.stack.addWidget(page)
        lay.addWidget(self.stack, 1)

    # ------------------------------------------------------------ adding files
    def browse(self):
        last = self.settings.value("last_dir", os.path.expanduser("~"))
        paths, _ = QFileDialog.getOpenFileNames(self, "选择电池数据文件", str(last), FILE_FILTER)
        if paths:
            self.settings.setValue("last_dir", os.path.dirname(paths[0]))
            self.add_paths(paths)

    def load_demo(self):
        from ..demo import write_demo
        folder = os.path.join(tempfile.gettempdir(), "galvaplot_demo")
        paths = write_demo(folder)
        self.add_paths(paths)
        self.message.emit("已加载合成示例数据（不是真实测试数据），名称可双击修改")

    def add_paths(self, paths):
        expanded = []
        for p in paths:
            if os.path.isdir(p):
                inside = sorted(os.path.join(p, f) for f in os.listdir(p)
                                if f.lower().endswith((".cex", ".ndax")))
                expanded.extend(inside)
            else:
                expanded.append(p)
        have = {os.path.abspath(i.path) for i in self.items}
        skipped_type, skipped_dup, skipped_full = [], [], []
        for p in expanded:
            ap = os.path.abspath(p)
            ext = os.path.splitext(p)[1].lower()
            if ext not in SUPPORTED_EXT and ext != ".icex":
                skipped_type.append(os.path.basename(p))
                continue
            if ap in have:
                skipped_dup.append(os.path.basename(p))
                continue
            if len(self.items) >= MAX_FILES:
                skipped_full.append(os.path.basename(p))
                continue
            it = Item(ap, self._next_color())
            self._restore(it)
            self.items.append(it)
            have.add(ap)
            self.pool.start(_LoadTask(ap, self.signals))
        msgs = []
        if skipped_full:
            msgs.append(f"最多 {MAX_FILES} 个文件，未添加：{', '.join(skipped_full[:3])}{' 等' if len(skipped_full) > 3 else ''}")
        if skipped_dup:
            msgs.append(f"已在列表中：{', '.join(skipped_dup[:3])}")
        if skipped_type:
            msgs.append(f"不支持的文件：{', '.join(skipped_type[:3])}")
        if msgs:
            self.message.emit("；".join(msgs))
        self._rebuild()

    def _next_color(self):
        used = {i.color for i in self.items}
        for c in PALETTE:
            if c not in used:
                return c
        return PALETTE[len(self.items) % len(PALETTE)]

    def _loaded(self, path, cell, err):
        it = next((i for i in self.items if i.path == path), None)
        if it is None:
            return
        if cell is None:
            self.items.remove(it)
            self._rebuild()
            box = QMessageBox(QMessageBox.Icon.Warning, "无法读取文件",
                              f"无法读取 {os.path.basename(path)}", QMessageBox.StandardButton.Ok, self)
            # short bold headline + normal-weight details (macOS draws the main text in bold)
            box.setInformativeText(f"{err}\n\n如果这是蓝电 .cex 或新威 .ndax 文件，欢迎在 GitHub 提交 issue"
                                   "（可附上文件），我们会尽快适配。")
            box.exec()
            return
        it.cell, it.loading = cell, False
        self._rebuild()
        if cell.warnings:
            self.message.emit(f"{it.label}：" + "；".join(cell.warnings[:2]))
        self.changed.emit()

    # ------------------------------------------------------------ table
    def _rebuild(self):
        self._building = True
        self.table.setRowCount(len(self.items))
        for r, it in enumerate(self.items):
            vis = QTableWidgetItem()
            vis.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            vis.setCheckState(Qt.CheckState.Checked if it.visible else Qt.CheckState.Unchecked)
            self.table.setItem(r, 0, vis)

            cb = QToolButton()
            cb.setIcon(_swatch(it.color, 18))
            cb.setIconSize(QSize(18, 18))
            cb.setAutoRaise(True)
            cb.setToolTip("点击换颜色")
            cb.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            cb.setMenu(self._color_menu(it))
            cb.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0; }")
            self.table.setCellWidget(r, 1, cb)

            ls = QComboBox()
            for key, glyph in (("solid", "——"), ("dashed", "– –"), ("dotted", "···"), ("dashdot", "–·–")):
                ls.addItem(glyph, key)
                ls.setItemData(ls.count() - 1, LINESTYLE_LABELS[key], Qt.ItemDataRole.ToolTipRole)
            ls.setCurrentIndex(["solid", "dashed", "dotted", "dashdot"].index(it.ls))
            ls.currentIndexChanged.connect(lambda _i, it=it, w=ls: self._set(it, "ls", w.currentData()))
            ls.setStyleSheet("QComboBox { border: none; padding: 0 16px 0 4px; background: transparent; }"
                             "QComboBox::drop-down { width: 16px; }")
            self.table.setCellWidget(r, 2, ls)

            name = QTableWidgetItem("读取中…" if it.loading else it.label)
            if it.loading:
                name.setFlags(Qt.ItemFlag.ItemIsEnabled)
                name.setForeground(QColor("#9aa1ab"))
            name.setToolTip(self._tooltip(it))
            self.table.setItem(r, 3, name)

            mass = QTableWidgetItem("" if it.mass is None else f"{it.mass:g}")
            mass.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            mass.setToolTip("活性物质质量（mg），用于比容量 mAh/g；不需要可留空")
            self.table.setItem(r, 4, mass)
        self._building = False
        self.count.setText(f"{len(self.items)} / {MAX_FILES}")
        self.stack.setCurrentIndex(1 if self.items else 0)
        self.small_drop.setVisible(len(self.items) < MAX_FILES)
        self.demo_btn.setVisible(not self.items)

    def _tooltip(self, it: Item):
        lines = [it.path]
        c = it.cell
        if c is not None:
            lines.append(f"来源：{c.source}　数据点：{c.n_points:,}　工步：{len(c.steps)}")
            cyc = c.cycles
            if cyc:
                lines.append(f"循环：{cyc[0]}–{cyc[-1]}　时长：{c.duration_h:.1f} h")
            if c.start_time:
                lines.append(f"开始时间：{c.start_time:%Y-%m-%d %H:%M}")
            for w in c.warnings[:4]:
                lines.append("⚠ " + w)
        lines.append("")
        lines.append(NAME_TIP)
        return "\n".join(lines)

    def _color_menu(self, it):
        m = QMenu(self)
        for c, cname in zip(PALETTE, PALETTE_NAMES):
            a = QAction(_swatch(c), cname, m)
            a.triggered.connect(lambda _=False, c=c, it=it: self._set(it, "color", c, rebuild=True))
            m.addAction(a)
        m.addSeparator()
        other = QAction("其他颜色…", m)
        other.triggered.connect(lambda _=False, it=it: self._pick_color(it))
        m.addAction(other)
        return m

    def _pick_color(self, it):
        col = QColorDialog.getColor(QColor(it.color), self, "选择曲线颜色")
        if col.isValid():
            self._set(it, "color", col.name(), rebuild=True)

    def _set(self, it, key, value, rebuild=False):
        setattr(it, key, value)
        self._remember(it)
        if rebuild:
            self._rebuild()
        self.changed.emit()

    def _item_changed(self, cell_item):
        if self._building:
            return
        r, c = cell_item.row(), cell_item.column()
        if r >= len(self.items):
            return
        it = self.items[r]
        if c == 0:
            it.visible = cell_item.checkState() == Qt.CheckState.Checked
        elif c == 3 and not it.loading:
            txt = cell_item.text().strip()
            it.label = txt or it.default
            if not txt:
                self._building = True
                cell_item.setText(it.label)
                self._building = False
        elif c == 4:
            txt = cell_item.text().strip().replace(",", ".")
            try:
                v = float(txt) if txt else None
                it.mass = v if (v is None or v > 0) else None
            except ValueError:
                it.mass = None
                self._building = True
                cell_item.setText("")
                self._building = False
                self.message.emit("质量请填数字（单位 mg）")
        else:
            return
        self._remember(it)
        self.changed.emit()

    def _context_menu(self, pos):
        r = self.table.rowAt(pos.y())
        if r < 0:
            return
        it = self.items[r]
        m = QMenu(self)
        m.addAction("恢复原文件名", lambda: self._set(it, "label", it.default, rebuild=True))
        m.addAction("在文件夹中显示", lambda: self._reveal(it.path))
        m.addSeparator()
        m.addAction("移除", lambda: self._remove(r))
        m.exec(self.table.viewport().mapToGlobal(pos))

    def _reveal(self, path):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    def _move(self, d):
        r = self.table.currentRow()
        j = r + d
        if r < 0 or not (0 <= j < len(self.items)):
            return
        self.items[r], self.items[j] = self.items[j], self.items[r]
        self._rebuild()
        self.table.selectRow(j)
        self.changed.emit()

    def _remove(self, r):
        if 0 <= r < len(self.items):
            del self.items[r]
            self._rebuild()
            self.changed.emit()

    def _remove_selected(self):
        self._remove(self.table.currentRow())

    def _shorten(self):
        ok = [i for i in self.items if not i.loading]
        new = shorten_names([i.label for i in ok])
        if new == [i.label for i in ok]:
            self.message.emit("名称已经没有可以精简的公共部分，可以双击名称直接修改")
            return
        for i, n in zip(ok, new):
            i.label = n
            self._remember(i)
        self._rebuild()
        self.changed.emit()

    def clear(self):
        self.items.clear()
        self._rebuild()
        self.changed.emit()

    # ------------------------------------------------------------ persistence (per file path)
    def _key(self, path):
        return "files/" + hashlib.md5(path.encode("utf-8")).hexdigest()

    def _remember(self, it):
        d = dict(label=it.label, color=it.color, ls=it.ls, mass=it.mass)
        self.settings.setValue(self._key(it.path), json.dumps(d))

    def _restore(self, it):
        raw = self.settings.value(self._key(it.path))
        if not raw:
            return
        try:
            d = json.loads(raw)
        except (TypeError, ValueError):
            return
        it.label = d.get("label") or it.label
        it.ls = d.get("ls") if d.get("ls") in ("solid", "dashed", "dotted", "dashdot") else it.ls
        it.mass = d.get("mass")
        col = d.get("color")
        if col and col not in {i.color for i in self.items}:
            it.color = col

    # ------------------------------------------------------------ output
    def series(self):
        out = []
        for it in self.items:
            if it.cell is None or not it.visible:
                continue
            if not hasattr(it, "_series") or it._series.cell is not it.cell:
                it._series = Series(it.cell, it.label, it.color, it.ls, it.mass)
            s = it._series
            s.label, s.color, s.ls, s.mass_mg = it.label, it.color, it.ls, it.mass
            out.append(s)
        return out

    def is_loading(self):
        return any(i.loading for i in self.items)
