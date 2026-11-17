"""Application entry point."""
from __future__ import annotations

import os
import sys


def _persistent_mpl_cache():
    """In a packaged build, PyInstaller points matplotlib at a temporary config dir that is
    deleted on exit, so the font cache would be rebuilt on every launch (10–20 s). Use a
    per-user cache dir instead. Returns True if the font cache already exists there."""
    if not getattr(sys, "frozen", False):
        return True
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Caches")
    elif sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    d = os.path.join(base, "GalvaPlot", "matplotlib")
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".write_test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
    except OSError:
        return False             # keep PyInstaller's temporary dir
    os.environ["MPLCONFIGDIR"] = d
    return any(f.startswith("fontlist-") for f in os.listdir(d))


def _splash_pixmap(icon):
    """White card with the icon and a dark message (readable on any desktop)."""
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
    pm = QPixmap(380, 210)
    pm.fill(QColor("#ffffff"))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    if icon:
        p.drawPixmap(QRect(150, 18, 80, 80), QPixmap(icon))
    p.setPen(QColor("#1f2328"))
    f = QFont()
    f.setPointSize(15)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRect(0, 104, 380, 30), Qt.AlignmentFlag.AlignCenter, "GalvaPlot")
    f.setPointSize(12)
    f.setBold(False)
    p.setFont(f)
    p.setPen(QColor("#4b5563"))
    p.drawText(QRect(10, 138, 360, 56), Qt.AlignmentFlag.AlignCenter,
               "首次启动：正在建立字体缓存\n大约需要 10–30 秒，以后打开会很快")
    p.setPen(QColor("#d0d5dc"))
    p.drawRect(0, 0, 379, 209)
    p.end()
    return pm


def main(argv=None):
    cache_ready = _persistent_mpl_cache()      # must run before matplotlib is imported
    import matplotlib
    matplotlib.use("Agg")
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QSplashScreen

    from .. import APP_NAME

    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("GalvaPlot")
    icon = _icon_path()
    if icon:
        app.setWindowIcon(QIcon(icon))
    splash = None
    if not cache_ready:      # first launch: building the font cache takes a while
        splash = QSplashScreen(_splash_pixmap(icon))
        splash.show()
        app.processEvents()

    from . import theme
    from .main_window import MainWindow   # imports matplotlib's font manager (builds the cache once)

    theme.apply(app)
    w = MainWindow()
    w.show()
    if splash:
        splash.finish(w)
    files = [a for a in argv[1:] if os.path.exists(a)]
    out = os.environ.get("GALVAPLOT_SELFTEST")
    if out:
        _selftest(app, w, files, out)
    elif files:
        w.files.add_paths(files)
    return app.exec()


def _selftest(app, w, files, out):
    """Smoke test of a packaged build: load files (or the demo), draw every figure type,
    save them to `out`, then quit with status 0 (ok) or 1. Used by CI after packaging."""
    from PySide6.QtCore import QTimer

    from ..plotting import figures as F
    from .plot_panel import KINDS

    os.makedirs(out, exist_ok=True)
    if files:
        w.files.add_paths(files)
    else:
        w.files.load_demo()
    timer = QTimer(w)
    state = {"waited": 0}

    def step():
        state["waited"] += 1
        if w.files.is_loading() and state["waited"] < 600:
            return
        timer.stop()
        ok = bool(w.files.series())
        try:
            for key, _ in KINDS:
                w.plot.set_kind(key)
                w.plot.redraw()
                F.save(w.plot.result, os.path.join(out, f"{key}.png"), dpi=100)
            w.grab().save(os.path.join(out, "window.png"))
        except Exception as e:  # report and fail
            print("SELFTEST FAILED:", repr(e), flush=True)
            ok = False
        with open(os.path.join(out, "selftest.txt"), "w", encoding="utf-8") as f:
            f.write("ok\n" if ok else "failed\n")
        print("SELFTEST", "OK" if ok else "FAILED", flush=True)
        app.exit(0 if ok else 1)

    timer.timeout.connect(step)
    timer.start(100)


def _icon_path():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
    return p if os.path.exists(p) else None


if __name__ == "__main__":
    sys.exit(main())
