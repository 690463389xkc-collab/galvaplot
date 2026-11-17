"""Main window: file panel (left) + plot panel (right); the whole window accepts drops."""
from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QMainWindow, QPushButton,
                               QScrollArea, QSplitter, QVBoxLayout, QWidget)

from .. import APP_TITLE, MAX_FILES, __version__
from .file_panel import FilePanel
from .plot_panel import PlotPanel

HELP = f"""<h3>GalvaPlot {__version__} · 电池数据一键作图</h3>
<p><b>用法</b>：把蓝电 <code>.cex</code> 或新威 <code>.ndax</code> 文件（最多 {MAX_FILES} 个，可以混用）拖进窗口 → 选图的类型 → 复制或保存。</p>
<ul>
<li><b>改名称</b>：双击左侧“名称”。下标写 <code>AlCl_{{3}}</code>，上标写 <code>Li^{{+}}</code>。</li>
<li><b>颜色/线型</b>：点色块换颜色；平行样可用同一颜色、不同线型。</li>
<li><b>比容量</b>：在“质量 mg”一栏填活性物质质量，再把容量单位改成 mAh/g。</li>
<li><b>测试条件</b>：写在“图下方注释”里，会印在图的底部。</li>
<li><b>导出数据</b>：生成 Excel，每条曲线两列，可直接导入 Origin。</li>
</ul>
<p><b>循环的定义</b>：蓝电沿用文件里的循环号；新威按工步程序里的循环划分（循环开始前的充放电算第 1 圈，例如首次放电；之后每执行一遍循环算一圈），与蓝电的编号方式一致，可能与 BTSDA 显示的循环号不同。库仑效率默认 = 同一圈的放电容量 ÷ 充电容量（负极半电池可在“更多设置”里改）。</p>
<p><b>关于文件格式</b>：蓝电 .cex 和新威 .ndax 都没有公开格式，本程序的读取方法是逆向得到的，
分别在 143 个和 26 个文件上做过一致性检查（容量与电流积分一致等），但没有与官方软件导出逐点比对。
新威目前只支持 BTS 8.x 写出的 .ndax（内部 v17），不支持旧版 .nda。
遇到 CV、CCCV 等其他工步类型时按电流方向判断充放电。重要数据请与官方软件核对。
读不了的文件欢迎到 GitHub 提交 issue。</p>
<p>本软件与武汉市蓝电电子股份有限公司、深圳市新威尔电子有限公司无关。开源协议：MIT。程序包含的第三方开源组件（其中 Qt / PySide6 按 LGPL-3.0 使用）及其许可证，见安装目录里的 licenses / third_party_licenses 文件夹。</p>
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.settings = QSettings("GalvaPlot", "GalvaPlot")
        self.setAcceptDrops(True)

        root = QWidget()
        root.setObjectName("root")
        lay = QHBoxLayout(root)
        lay.setContentsMargins(12, 12, 12, 6)
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(10)
        self.files = FilePanel(self.settings)
        self.files.setMinimumWidth(320)
        self.plot = PlotPanel(self.settings, self.files.series, self.files.is_loading)
        split.addWidget(self.files)
        split.addWidget(self.plot)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([450, 970])
        lay.addWidget(split)
        self.setCentralWidget(root)

        self.files.changed.connect(self.plot.schedule)
        self.files.message.connect(self.show_message)
        self.plot.message.connect(self.show_message)

        help_btn = QPushButton("帮助")
        help_btn.setObjectName("link")
        help_btn.clicked.connect(self.show_help)
        self.statusBar().addPermanentWidget(help_btn)
        self.statusBar().showMessage("拖入蓝电 .cex 或新威 .ndax 文件开始作图")

        act_open = QAction("打开", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.triggered.connect(self.files.browse)
        act_save = QAction("保存", self)
        act_save.setShortcut(QKeySequence.StandardKey.Save)
        act_save.triggered.connect(self.plot.save_image)
        self.addAction(act_open)
        self.addAction(act_save)

        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            self.resize(1420, 880)

    def show_message(self, text):
        self.statusBar().showMessage(text, 12000)

    def show_help(self):
        # a plain dialog: QMessageBox renders its whole text in bold on macOS
        dlg = QDialog(self)
        dlg.setWindowTitle("帮助")
        dlg.resize(600, 560)
        lay = QVBoxLayout(dlg)
        text = QLabel(HELP)
        text.setTextFormat(Qt.TextFormat.RichText)
        text.setWordWrap(True)
        text.setOpenExternalLinks(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse)
        text.setStyleSheet("QLabel { font-size: 13px; line-height: 150%; padding: 4px 8px; }")
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(text)
        lay.addWidget(area, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(dlg.accept)
        lay.addWidget(buttons)
        dlg.exec()

    # drag & drop anywhere in the window
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.files.big_drop.set_active(True)
            self.files.small_drop.set_active(True)

    def dragLeaveEvent(self, e):
        self.files.big_drop.set_active(False)
        self.files.small_drop.set_active(False)

    def dropEvent(self, e):
        self.files.big_drop.set_active(False)
        self.files.small_drop.set_active(False)
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            e.acceptProposedAction()
            self.files.add_paths(paths)

    def closeEvent(self, e):
        self.settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(e)
