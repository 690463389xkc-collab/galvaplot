"""Install a downloaded update in place ("立即更新").

Why: the app is not signed by Apple / Microsoft, so a version downloaded with a web browser
is stopped by Gatekeeper / SmartScreen on first launch, every time. Files that GalvaPlot
downloads itself carry no "downloaded from the internet" mark, so an update installed from
inside the app opens without that prompt. In exchange the app checks the download against
the SHA-256 digest GitHub publishes for the release asset before installing anything.

Flow (GUI in gui/main_window.py):
  1. install_target() decides whether this copy can update itself (packaged build, known
     install location, writable) and where;
  2. the GUI downloads the asset and calls sha256_file() == asset["sha256"];
  3. start_install() starts a small helper that waits for the app to quit, replaces it and
     opens the new version; the GUI then quits.

macOS: the helper is a /bin/sh script: mount the .dmg read-only, copy GalvaPlot.app next to
the installed one, swap the two (the old one is put back if anything fails), open it.
Windows: only for copies installed with the Setup program (unins000.exe next to the exe);
the new Setup runs with /SILENT and reopens the app (/RELAUNCH=1, see installer/galvaplot.iss).
The portable zip and source checkouts get the download page instead.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile

LOG_NAME = "galvaplot_update.log"


def sha256_file(path, chunk=1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _original_path_mac(app_path):
    """Real location of an app that macOS runs from a randomized read-only copy
    ("App Translocation", used for quarantined apps that were not moved by Finder)."""
    if "/AppTranslocation/" not in app_path:
        return app_path
    try:
        import ctypes
        import ctypes.util
        cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
        sec = ctypes.cdll.LoadLibrary(ctypes.util.find_library("Security"))
        cf.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
        cf.CFURLCreateFromFileSystemRepresentation.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                                                ctypes.c_long, ctypes.c_bool]
        cf.CFURLGetFileSystemRepresentation.restype = ctypes.c_bool
        cf.CFURLGetFileSystemRepresentation.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_char_p, ctypes.c_long]
        cf.CFRelease.argtypes = [ctypes.c_void_p]
        sec.SecTranslocateCreateOriginalPathForURL.restype = ctypes.c_void_p
        sec.SecTranslocateCreateOriginalPathForURL.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        raw = app_path.encode("utf-8")
        url = cf.CFURLCreateFromFileSystemRepresentation(None, raw, len(raw), True)
        if not url:
            return None
        orig = sec.SecTranslocateCreateOriginalPathForURL(url, None)
        cf.CFRelease(url)
        if not orig:
            return None
        buf = ctypes.create_string_buffer(4096)
        ok = cf.CFURLGetFileSystemRepresentation(orig, True, buf, len(buf))
        cf.CFRelease(orig)
        return buf.value.decode("utf-8") if ok else None
    except Exception:
        return None


def install_target(executable=None, platform=None, frozen=None):
    """(target, None) if this copy can update itself, else (None, reason in Chinese).

    target: the .app bundle (macOS) or the install folder (Windows)."""
    executable = executable or sys.executable
    platform = platform or sys.platform
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if not frozen:
        return None, "从源码运行时请用 git pull 更新"
    if platform == "darwin":
        app = os.path.dirname(os.path.dirname(os.path.dirname(executable)))   # X.app/Contents/MacOS/X
        if not app.endswith(".app"):
            return None, "找不到程序所在的位置"
        app = _original_path_mac(app)
        if not app or not os.path.isdir(app):
            return None, "找不到程序所在的位置"
        parent = os.path.dirname(app)
        if parent.startswith("/Volumes/") and parent.count("/") == 2:
            return None, "程序是从安装盘里直接打开的，请先把它拖进“应用程序”"
        if not (os.access(parent, os.W_OK) and os.access(app, os.W_OK)):
            return None, f"没有写入 {parent} 的权限"
        return app, None
    if platform == "win32":
        folder = os.path.dirname(executable)
        if not os.path.exists(os.path.join(folder, "unins000.exe")):
            return None, "免安装版请下载新的压缩包并解压替换"
        return folder, None
    return None, "这个系统暂时没有安装包"


MAC_SCRIPT = r'''#!/bin/sh
# GalvaPlot updater: wait for the app to quit, replace it, open the new version.
pid="$1"; dmg="$2"; target="$3"; relaunch="$4"
echo "update $(date): $dmg -> $target"
i=0
while kill -0 "$pid" 2>/dev/null && [ $i -lt 240 ]; do sleep 0.25; i=$((i+1)); done
mnt="$(mktemp -d "${TMPDIR:-/tmp}/galvaplot_update.XXXXXX")"
if ! hdiutil attach -nobrowse -readonly -noverify -noautoopen -mountpoint "$mnt" "$dmg"; then
    echo "mount failed"; [ "$relaunch" = 1 ] && open "$target"; exit 1
fi
dir="$(dirname "$target")"
new="$dir/.GalvaPlot-update-$$.app"
old="$dir/.GalvaPlot-previous-$$.app"
if ! ditto "$mnt/GalvaPlot.app" "$new"; then
    echo "copy failed"; rm -rf "$new"; hdiutil detach "$mnt" -quiet; [ "$relaunch" = 1 ] && open "$target"; exit 1
fi
hdiutil detach "$mnt" -quiet || hdiutil detach "$mnt" -force -quiet
rmdir "$mnt" 2>/dev/null
if mv "$target" "$old" && mv "$new" "$target"; then
    rm -rf "$old"
    rm -f "$dmg"
    echo "done"
else
    echo "swap failed, keeping the old version"
    [ -d "$old" ] && [ ! -d "$target" ] && mv "$old" "$target"
    rm -rf "$new"
fi
[ "$relaunch" = 1 ] && open "$target"
exit 0
'''


def _log_path():
    return os.path.join(tempfile.gettempdir(), LOG_NAME)


def start_install(package, target, platform=None, relaunch=True):
    """Start the helper that installs `package` after this process has quit.
    Returns the helper's Popen; raises OSError if it cannot be started."""
    platform = platform or sys.platform
    log = open(_log_path(), "a", encoding="utf-8")
    if platform == "darwin":
        script = os.path.join(tempfile.gettempdir(), "galvaplot_update.sh")
        with open(script, "w", encoding="utf-8") as f:
            f.write(MAC_SCRIPT)
        cmd = ["/bin/sh", script, str(os.getpid()), package, target, "1" if relaunch else "0"]
        return subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                start_new_session=True, close_fds=True)
    if platform == "win32":
        cmd = [package, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]
        if relaunch:
            cmd.append("/RELAUNCH=1")
        flags = 0x00000008 | 0x00000200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        return subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                creationflags=flags, close_fds=True)
    raise OSError("unsupported platform")
