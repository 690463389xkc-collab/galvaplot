"""Main window: file panel (left) + plot panel (right); the whole window accepts drops."""
from __future__ import annotations

import html
import os
import time

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QMainWindow,
                               QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget)

from .. import APP_TITLE, MAX_FILES, REPO, __version__
from .. import updates
from .file_panel import FilePanel
from .plot_panel import PlotPanel

HELP = f"""<h3>GalvaPlot {__version__} · 电池数据一键作图</h3>
<p><b>用法</b>：把蓝电 <code>.cex</code> 或新威 <code>.ndax</code> 文件（最多 {MAX_FILES} 个，可以混用）拖进窗口 → 选图的类型 → 复制或保存。</p>
<ul>
<li><b>改名称</b>：双击左侧“名称”。下标写 <code>AlCl_{{3}}</code>，上标写 <code>Li^{{+}}</code>。</li>
<li><b>颜色/线型</b>：点色块换颜色；平行样可用同一颜色、不同线型。</li>
<li><b>比容量</b>：在“质量 mg”一栏填活性物质质量（新威文件里设置过质量的会自动读入），再把容量单位改成 mAh/g。</li>
<li><b>排布</b>：充放电曲线和 dQ/dV 可选“所有圈+所有电池”，全部画在一张图里（颜色区分电池，线型区分圈数）。</li>
<li><b>右键预览图</b>：在某个子图上点右键，可以单独复制它的数据（直接粘贴到 Excel / Origin）或图片、只显示它。</li>
<li><b>测试条件</b>：写在“图下方注释”里，会印在图的底部。</li>
<li><b>导出数据</b>：生成 Excel，每条曲线两列，可直接导入 Origin。</li>
</ul>
<p><b>循环的定义</b>：蓝电沿用文件里的循环号；新威按工步程序里的循环划分（循环开始前的充放电算第 1 圈，例如首次放电；之后每执行一遍循环算一圈），与蓝电的编号方式一致，可能与 BTSDA 显示的循环号不同。库仑效率默认 = 同一圈的放电容量 ÷ 充电容量（负极半电池可在“更多设置”里改）。</p>
<p><b>关于文件格式</b>：蓝电 .cex 和新威 .ndax 都没有公开格式，本程序的读取方法是逆向得到的，
分别在 143 个和 26 个文件上做过一致性检查（容量与电流积分一致等），但没有与官方软件导出逐点比对。
新威目前只支持 BTS 8.x 写出的 .ndax（内部 v17），不支持旧版 .nda。
遇到 CV、CCCV 等其他工步类型时按电流方向判断充放电。重要数据请与官方软件核对。
读不了的文件欢迎到 GitHub 提交 issue。</p>
<p><b>检查更新</b>：点右下角“检查更新”。程序默认每天启动时最多自动检查一次，只向 GitHub 查询最新版本号（不上传任何数据或文件），可以在检查更新的窗口里关掉。新版本需要自己下载安装，原来的设置会保留。项目主页：<a href="https://github.com/{REPO}">github.com/{REPO}</a></p>
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

        self.update_btn = QPushButton("检查更新")
        self.update_btn.setObjectName("link")
        self.update_btn.setToolTip(f"当前版本 {__version__}；到 GitHub 查看有没有新版本")
        self.update_btn.clicked.connect(self.check_updates)
        self.statusBar().addPermanentWidget(self.update_btn)
        help_btn = QPushButton("帮助")
        help_btn.setObjectName("link")
        help_btn.clicked.connect(self.show_help)
        self.statusBar().addPermanentWidget(help_btn)
        self.checker = updates.UpdateChecker(self) if updates.UpdateChecker else None
        if self.checker:
            self.checker.finished.connect(self._update_result)
        self._manual_check = False
        self._newer = None
        QTimer.singleShot(3000, self._auto_check)
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

    # ------------------------------------------------------------ updates
    def _auto_check(self):
        if not self.checker or os.environ.get("GALVAPLOT_SELFTEST") or os.environ.get("GALVAPLOT_NO_UPDATE_CHECK"):
            return
        if not self.settings.value("update/auto", True, type=bool):
            return
        last = self.settings.value("update/last", 0.0, type=float)
        if time.time() - last < updates.AUTO_INTERVAL_H * 3600:
            return
        self._manual_check = False
        self.checker.check()

    def check_updates(self):
        if self._newer:                      # already known: show it without asking GitHub again
            self._update_dialog(self._newer)
            return
        if not self.checker:
            QDesktopServices.openUrl(QUrl(updates.RELEASES_URL))
            return
        self._manual_check = True
        self.update_btn.setText("正在检查…")
        self.update_btn.setEnabled(False)
        self.checker.check()

    def _update_result(self, res):
        self.update_btn.setEnabled(True)
        self.update_btn.setText("检查更新")
        if res.get("ok"):
            self.settings.setValue("update/last", time.time())
        if res.get("ok") and res.get("newer"):
            self._newer = res
            self.update_btn.setText(f"有新版本 {res['latest']}")
            self.update_btn.setStyleSheet("color: #d7261e; font-weight: 600;")
            self.update_btn.setToolTip("点击查看更新说明和下载")
            if not self._manual_check:
                self.show_message(f"GalvaPlot 有新版本 {res['latest']}（当前 {__version__}），点右下角查看")
        if self._manual_check:
            self._update_dialog(res)
        self._manual_check = False

    def _update_dialog(self, res):
        dlg = QDialog(self)
        dlg.setWindowTitle("检查更新")
        dlg.setMinimumWidth(460)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(10)
        buttons = QHBoxLayout()
        buttons.addStretch(1)

        def link_btn(text, url, primary=False):
            b = QPushButton(text)
            if primary:
                b.setObjectName("primary")
                b.setDefault(True)
            b.clicked.connect(lambda: (QDesktopServices.openUrl(QUrl(url)), dlg.accept()))
            buttons.addWidget(b)

        if res.get("ok") and res.get("newer"):
            text = (f"<p style='font-size:15px'><b>有新版本：{html.escape(res['latest'])}</b>"
                    f"（当前 {__version__}）</p>")
            if res.get("notes"):
                text += ("<p style='color:#374151'>" + html.escape(res["notes"]).replace("\n", "<br>") + "</p>")
            text += ("<p style='color:#4b5563'>下载后像第一次一样安装即可：Windows 双击安装包会替换旧版本；"
                     "macOS 把新的 GalvaPlot 拖进“应用程序”，提示时选“替换”。原来的设置和曲线名称会保留。</p>")
            link_btn("查看更新说明", res["page"])
            link_btn("下载新版本", res["download"], primary=True)
        elif res.get("ok"):
            text = f"<p style='font-size:15px'>已经是最新版本（{__version__}）。</p>"
        else:
            text = (f"<p style='font-size:15px'>暂时连不上 GitHub</p><p style='color:#4b5563'>"
                    f"{html.escape(str(res.get('error') or ''))}<br>可以稍后再试，或直接打开发布页面查看。</p>")
            link_btn("打开发布页面", updates.RELEASES_URL)
        lbl = QLabel(text)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(lbl)
        auto = QCheckBox("启动时自动检查更新（每天最多一次，只访问 GitHub）")
        auto.setChecked(self.settings.value("update/auto", True, type=bool))
        auto.toggled.connect(lambda on: self.settings.setValue("update/auto", bool(on)))
        lay.addWidget(auto)
        close = QPushButton("以后再说" if res.get("newer") else "关闭")
        close.clicked.connect(dlg.reject)
        buttons.insertWidget(1, close)
        lay.addLayout(buttons)
        self._last_update_dialog = dlg          # for tests / screenshots
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
