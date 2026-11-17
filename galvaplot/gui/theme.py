"""Light, quiet Qt theme (Fusion + a small stylesheet) shared by Windows and macOS."""
from PySide6.QtGui import QColor, QPalette

ACCENT = "#2f5f9e"
ACCENT_DARK = "#244b7e"
BG = "#f4f5f7"
CARD = "#ffffff"
BORDER = "#e1e4e8"
TEXT = "#1f2328"
MUTED = "#6b7280"

QSS = f"""
QWidget {{ color: {TEXT}; font-size: 13px; }}
QMainWindow, #root {{ background: {BG}; }}
#card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; }}
#title {{ font-size: 15px; font-weight: 600; }}
#muted {{ color: {MUTED}; }}
#notes {{ color: {MUTED}; font-size: 12px; }}
#hint {{ color: {MUTED}; font-size: 12px; }}

QPushButton {{ padding: 6px 12px; border: 1px solid #cfd5dd; border-radius: 6px; background: {CARD}; }}
QPushButton:hover {{ background: #f0f3f7; }}
QPushButton:pressed {{ background: #e4e9f0; }}
QPushButton:disabled {{ color: #a0a7b1; border-color: #e3e6ea; }}
QPushButton#primary {{ background: {ACCENT}; color: white; border: 1px solid {ACCENT}; font-weight: 600; }}
QPushButton#primary:hover {{ background: {ACCENT_DARK}; }}
QPushButton#primary:disabled {{ background: #9fb3cf; border-color: #9fb3cf; }}
QPushButton#link {{ border: none; background: transparent; color: {ACCENT}; padding: 4px 6px; }}
QPushButton#link:hover {{ text-decoration: underline; }}
QPushButton#small {{ padding: 4px 8px; font-size: 12px; }}

QPushButton#seg {{ padding: 8px 18px; border: 1px solid #cfd5dd; border-radius: 0; background: {CARD}; font-weight: 500; }}
QPushButton#seg:checked {{ background: {ACCENT}; color: white; border-color: {ACCENT}; }}
QPushButton#segFirst {{ padding: 8px 18px; border: 1px solid #cfd5dd; border-top-left-radius: 7px; border-bottom-left-radius: 7px; border-top-right-radius: 0; border-bottom-right-radius: 0; background: {CARD}; font-weight: 500; }}
QPushButton#segFirst:checked {{ background: {ACCENT}; color: white; border-color: {ACCENT}; }}
QPushButton#segLast {{ padding: 8px 18px; border: 1px solid #cfd5dd; border-top-right-radius: 7px; border-bottom-right-radius: 7px; border-top-left-radius: 0; border-bottom-left-radius: 0; background: {CARD}; font-weight: 500; }}
QPushButton#segLast:checked {{ background: {ACCENT}; color: white; border-color: {ACCENT}; }}

QLineEdit, QComboBox, QPlainTextEdit {{
    border: 1px solid #cfd5dd; border-radius: 5px; padding: 3px 6px; background: white;
    selection-background-color: {ACCENT}; }}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {ACCENT}; }}

/* Spin boxes: once the frame is styled, Qt also needs the buttons and arrows styled,
   otherwise the arrows are not drawn. The arrow images are painted at start-up. */
QAbstractSpinBox {{ border: 1px solid #cfd5dd; border-radius: 5px; padding: 3px 22px 3px 6px;
    background: white; selection-background-color: {ACCENT}; }}
QAbstractSpinBox:focus {{ border-color: {ACCENT}; }}
QAbstractSpinBox QLineEdit {{ border: none; padding: 0; margin: 0; background: transparent; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ subcontrol-origin: padding; width: 18px;
    border: none; border-left: 1px solid #e1e4e8; background: #f3f5f8; }}
QAbstractSpinBox::up-button {{ subcontrol-position: top right; border-top-right-radius: 4px; }}
QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; border-bottom-right-radius: 4px;
    border-top: 1px solid #e1e4e8; }}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{ background: #e7eef8; }}
QAbstractSpinBox::up-button:pressed, QAbstractSpinBox::down-button:pressed {{ background: #d3e0f2; }}
QAbstractSpinBox::up-arrow {{ image: url(__UP__); width: 9px; height: 6px; }}
QAbstractSpinBox::down-arrow {{ image: url(__DOWN__); width: 9px; height: 6px; }}
QAbstractSpinBox::up-arrow:disabled, QAbstractSpinBox::up-arrow:off {{ image: url(__UP_OFF__); }}
QAbstractSpinBox::down-arrow:disabled, QAbstractSpinBox::down-arrow:off {{ image: url(__DOWN_OFF__); }}
QComboBox {{ padding-right: 22px; }}
QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: top right; width: 20px; border: none; }}
QComboBox::down-arrow {{ image: url(__DOWN__); width: 9px; height: 6px; }}
QComboBox::down-arrow:disabled {{ image: url(__DOWN_OFF__); }}
QComboBox QAbstractItemView {{ background: white; border: 1px solid {BORDER}; outline: 0;
    selection-background-color: #e7eef8; selection-color: {TEXT}; }}

/* disabled controls must look disabled */
QLineEdit:disabled, QComboBox:disabled, QAbstractSpinBox:disabled, QPlainTextEdit:disabled {{
    color: #a0a7b1; background: #f5f6f8; border-color: #e1e4e8; }}
QLabel:disabled, QCheckBox:disabled {{ color: #a0a7b1; }}

/* check boxes (also the "show" column of the file table): drawn here instead of by the
   platform style, whose frame can disappear (e.g. under macOS dark mode) */
QCheckBox::indicator, QTableView::indicator {{ width: 14px; height: 14px; border: 1px solid #8f99a6;
    border-radius: 3px; background: white; }}
QCheckBox::indicator:hover, QTableView::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked, QTableView::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT};
    image: url(__CHECK__); }}
QCheckBox::indicator:disabled {{ background: #f0f1f3; border-color: #d5d9de; }}
QCheckBox::indicator:checked:disabled {{ background: #9fb3cf; border-color: #9fb3cf; }}

QMenu {{ background: white; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 4px 18px 4px 8px; border-radius: 4px; }}
QMenu::item:selected {{ background: #e7eef8; color: {TEXT}; }}

QTableWidget {{ border: none; background: white; gridline-color: transparent;
    selection-background-color: #e7eef8; selection-color: {TEXT}; outline: 0; }}
QTableWidget::item {{ padding: 2px 4px; border-bottom: 1px solid #f0f1f3; }}
QHeaderView::section {{ background: white; border: none; border-bottom: 1px solid {BORDER};
    padding: 5px 4px; color: {MUTED}; font-weight: 600; font-size: 12px; }}

#dropzone {{ border: 2px dashed #b9c3d1; border-radius: 10px; background: #fafbfc; }}
#dropzone[active="true"] {{ border-color: {ACCENT}; background: #eef3fa; }}
#preview {{ background: white; border: 1px solid {BORDER}; border-radius: 10px; }}
QPushButton#panelBtn {{ min-width: 26px; max-width: 26px; min-height: 24px; max-height: 24px; padding: 0;
    border: 1px solid #cfd5dd; border-radius: 6px; background: white; color: #9aa1ab; font-weight: 600; font-size: 13px; }}
QPushButton#panelBtn:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton#panelBtn:checked {{ background: {ACCENT}; border-color: {ACCENT}; color: white; }}
QGroupBox {{ border: 1px solid {BORDER}; border-radius: 8px; margin-top: 10px; padding: 10px 8px 6px 8px; background: #fbfbfc; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {MUTED}; }}
QStatusBar {{ background: {BG}; color: {MUTED}; }}
QToolTip {{ background: white; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px; }}
QCheckBox {{ spacing: 6px; }}
QScrollArea {{ border: none; background: transparent; }}
"""


def _arrow_images():
    """Paint small chevron arrows (4x resolution, sharp on high-DPI screens) and return their paths."""
    import os
    import tempfile

    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QImage, QPainter, QPen

    d = os.path.join(tempfile.gettempdir(), "galvaplot_ui")
    os.makedirs(d, exist_ok=True)
    out = {}
    for name, up, color in (("up", True, "#4b5563"), ("down", False, "#4b5563"),
                            ("up_off", True, "#c3c8cf"), ("down_off", False, "#c3c8cf")):
        img = QImage(36, 24, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(color), 4.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        y0, y1 = (19, 5) if up else (5, 19)
        p.drawPolyline([QPointF(5, y0), QPointF(18, y1), QPointF(31, y0)])
        p.end()
        path = os.path.join(d, f"{name}.png")
        img.save(path)
        out[name] = path.replace("\\", "/")
    # white tick for checked check boxes (14 px box, drawn at 4x)
    img = QImage(56, 56, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#ffffff"), 7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawPolyline([QPointF(13, 29), QPointF(24, 40), QPointF(44, 17)])
    p.end()
    path = os.path.join(d, "check.png")
    img.save(path)
    out["check"] = path.replace("\\", "/")
    return out


def apply(app):
    app.setStyle("Fusion")
    # The app has one light design: do not follow the system's dark mode (Qt >= 6.8).
    try:
        from PySide6.QtCore import Qt
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except AttributeError:
        pass
    pal = QPalette()
    for role, col in [(QPalette.ColorRole.Window, BG), (QPalette.ColorRole.WindowText, TEXT),
                      (QPalette.ColorRole.Base, "#ffffff"), (QPalette.ColorRole.AlternateBase, "#f7f8fa"),
                      (QPalette.ColorRole.Text, TEXT), (QPalette.ColorRole.Button, "#ffffff"),
                      (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.Highlight, ACCENT),
                      (QPalette.ColorRole.HighlightedText, "#ffffff"), (QPalette.ColorRole.ToolTipBase, "#ffffff"),
                      (QPalette.ColorRole.ToolTipText, TEXT), (QPalette.ColorRole.PlaceholderText, "#9aa1ab")]:
        pal.setColor(role, QColor(col))
    app.setPalette(pal)
    qss = QSS
    try:
        a = _arrow_images()
        for key, name in (("__UP_OFF__", "up_off"), ("__DOWN_OFF__", "down_off"), ("__UP__", "up"),
                          ("__DOWN__", "down"), ("__CHECK__", "check")):
            qss = qss.replace(key, a[name])
    except OSError:      # no writable temp dir: drop the rules that need images
        qss = "\n".join(l for l in qss.splitlines() if "url(__" not in l)
    app.setStyleSheet(qss)
