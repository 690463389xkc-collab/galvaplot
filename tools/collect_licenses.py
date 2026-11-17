"""Collect the license texts of every third-party component bundled into the packaged app.

Called from galvaplot.spec at build time (also runnable by hand):
    python tools/collect_licenses.py [output_dir]
Writes one folder per component plus THIRD_PARTY_NOTICES.txt. The component list is
GalvaPlot's runtime requirements and everything they require (from the installed
package metadata), plus Python itself. Qt / PySide6 / shiboken6 wheels carry no license
files, so their LGPL-3.0 / GPL-3.0 texts come from the repository's licenses/ folder.
"""
import importlib.metadata as md
import os
import re
import shutil
import sys
import sysconfig

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOP = ["numpy", "matplotlib", "PySide6-Essentials", "openpyxl", "xlrd"]
QT_DISTS = {"pyside6-essentials", "shiboken6"}
LICENSE_RE = re.compile(r"(^|/)(licen[cs]e|copying|notice)[^/]*$", re.I)

QT_NOTE = """Qt for Python (PySide6, shiboken6) and the Qt 6 libraries
-------------------------------------------------------------
GalvaPlot uses Qt for Python and Qt 6 under the GNU Lesser General Public License
version 3 (LGPL-3.0); the license texts are in Qt-PySide6/ (LGPL-3.0.txt and the
GPL-3.0.txt it refers to). The Qt libraries are shipped as separate shared libraries
in the program folder and are not modified, so you can replace them with your own
build of the same version.
Source code: Qt for Python  https://download.qt.io/official_releases/QtForPython/
             (git: https://code.qt.io/cgit/pyside/pyside-setup.git)
             Qt 6           https://download.qt.io/official_releases/qt/
"""


def _norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def _closure(names):
    try:
        from packaging.requirements import Requirement
    except ImportError:          # packaging is a matplotlib dependency, but be safe
        Requirement = None
    seen, todo, out = set(), list(names), []
    while todo:
        n = todo.pop(0)
        key = _norm(n)
        if key in seen:
            continue
        seen.add(key)
        try:
            d = md.distribution(n)
        except md.PackageNotFoundError:
            continue
        out.append(d)
        for r in d.requires or []:
            if Requirement is not None:
                req = Requirement(r)
                if req.marker is not None and not req.marker.evaluate({"extra": ""}):
                    continue
                todo.append(req.name)
            elif "extra ==" not in r:
                todo.append(re.split(r"[ ;<>=!~\[(]", r, 1)[0])
    return out


def _summary(d):
    m = d.metadata
    lic = m.get("License-Expression") or ""
    if not lic:      # trove classifiers are cleaner than free-text License fields
        cls = [c.split("::")[-1].strip() for c in (m.get_all("Classifier") or []) if c.startswith("License ::")]
        lic = "; ".join(cls)
    if not lic:
        first = (m.get("License") or "").strip().splitlines()[:1]
        first = first[0].strip() if first else ""
        ok = first and len(first) <= 60 and re.search(r"[A-Za-z]", first) and not first.lower().startswith("copyright")
        lic = first if ok else "see license files"
    home = m.get("Home-page") or ""
    if not home:
        urls = m.get_all("Project-URL") or []
        home = urls[0].split(",", 1)[-1].strip() if urls else ""
    return lic, home


def _python_license():
    cands = [os.path.join(sysconfig.get_paths()["stdlib"], "LICENSE.txt"),
             os.path.join(sys.base_prefix, "LICENSE.txt"),
             os.path.join(sys.base_prefix, "lib", f"python{sys.version_info[0]}.{sys.version_info[1]}", "LICENSE.txt")]
    return next((p for p in cands if os.path.isfile(p)), None)


def collect(out):
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    lines = ["GalvaPlot - third-party components",
             "===================================",
             "",
             "GalvaPlot itself is released under the MIT License (LICENSE).",
             "The packaged program also contains the components below; each folder next to",
             "this file holds the license texts shipped with that component.",
             ""]
    py = _python_license()
    pyver = sys.version.split()[0]
    if py:
        os.makedirs(os.path.join(out, f"Python-{pyver}"))
        shutil.copy(py, os.path.join(out, f"Python-{pyver}", "LICENSE.txt"))
    lines.append(f"- Python {pyver} - PSF License Agreement - https://www.python.org/")
    missing = []
    for d in sorted(_closure(TOP), key=lambda x: _norm(x.metadata["Name"])):
        name, ver = d.metadata["Name"], d.version
        lic, home = _summary(d)
        lines.append(f"- {name} {ver} - {lic} - {home}")
        folder = os.path.join(out, f"{name}-{ver}")
        os.makedirs(folder, exist_ok=True)
        n = 0
        for f in d.files or []:
            p = str(f).replace("\\", "/")
            if LICENSE_RE.search(p):
                src = d.locate_file(f)
                if os.path.isfile(src):
                    shutil.copy(src, os.path.join(folder, p.replace("/", "__")))
                    n += 1
        if _norm(name) in QT_DISTS:
            for t in ("LGPL-3.0.txt", "GPL-3.0.txt"):
                shutil.copy(os.path.join(ROOT, "licenses", t), os.path.join(folder, t))
                n += 1
        if n == 0:
            missing.append(name)
    qt = os.path.join(out, "Qt-PySide6")
    os.makedirs(qt)
    for t in ("LGPL-3.0.txt", "GPL-3.0.txt"):
        shutil.copy(os.path.join(ROOT, "licenses", t), os.path.join(qt, t))
    lines += ["", QT_NOTE,
              "The program was packaged with PyInstaller, whose bootloader license (GPL-2.0 with",
              "an exception) explicitly allows distributing the packaged program under any license."]
    if missing:
        lines += ["", "No license file was found in the installed metadata of: " + ", ".join(missing) +
                  ". See the project pages listed above."]
    with open(os.path.join(out, "THIRD_PARTY_NOTICES.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return out


if __name__ == "__main__":
    dest = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "build", "third_party_licenses")
    print("written:", collect(dest))
