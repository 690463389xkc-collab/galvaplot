# PyInstaller spec:  pyinstaller --noconfirm galvaplot.spec
# Windows -> dist/GalvaPlot/GalvaPlot.exe ; macOS -> dist/GalvaPlot.app
import os
import sys

HERE = os.path.abspath(SPECPATH)  # noqa: F821  (SPECPATH is defined by PyInstaller)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
from galvaplot import __version__  # noqa: E402
from collect_licenses import collect  # noqa: E402

# license texts of every bundled component -> build/third_party_licenses (shipped with the app)
LICENSES = collect(os.path.join(HERE, "build", "third_party_licenses"))

excludes = ["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml",
            "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts",
            "PySide6.QtSql", "PySide6.QtPdf", "IPython", "pytest"]

a = Analysis(
    ["run_galvaplot.py"],
    pathex=[],
    datas=[("galvaplot/gui/icon.png", "galvaplot/gui"), (LICENSES, "third_party_licenses"), ("LICENSE", ".")],
    hiddenimports=["openpyxl", "xlrd"],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="GalvaPlot",
    console=False,
    icon="assets/icon.ico" if sys.platform == "win32" else "assets/icon.icns",
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="GalvaPlot", upx=False)
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="GalvaPlot.app",
        icon="assets/icon.icns",
        bundle_identifier="io.github.galvaplot",
        info_plist={
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
