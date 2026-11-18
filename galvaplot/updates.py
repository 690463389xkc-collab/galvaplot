"""Check GitHub for a newer release.

Only one request is made: GET https://api.github.com/repos/<REPO>/releases/latest
(no account, no data about the user or their files; GitHub sees the IP address and the
User-Agent "GalvaPlot/<version>"). Nothing is downloaded or installed automatically: the
user is pointed to the download.
"""
from __future__ import annotations

import json
import platform
import re
import sys

from . import REPO, __version__

API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
AUTO_INTERVAL_H = 20          # automatic check at most about once a day


def parse_version(text):
    """'v0.2.10' -> (0, 2, 10); None if there is no version number in the text."""
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", str(text or ""))
    if not m:
        return None
    return tuple(int(g or 0) for g in m.groups())


def is_newer(latest, current=__version__):
    a, b = parse_version(latest), parse_version(current)
    return bool(a and b and a > b)


def pick_asset(assets, system=None, machine=None):
    """Download URL of the package for this computer, or None (then the release page is used)."""
    system = system or sys.platform
    machine = (machine or platform.machine()).lower()
    if system == "win32":
        want = ("-windows-setup.exe",)
    elif system == "darwin" and machine in ("arm64", "aarch64"):
        want = ("-macos-applesilicon.dmg",)
    else:
        return None
    for a in assets or ():
        name = str(a.get("name", "")).lower()
        if name.endswith(want) and a.get("browser_download_url"):
            return a["browser_download_url"]
    return None


def notes_excerpt(body, max_lines=8):
    """First lines of the release notes as plain text (Markdown markup dropped)."""
    out = []
    for line in str(body or "").splitlines():
        s = line.strip()
        if s.startswith("---") or s.lower().startswith("**english**"):
            break                      # the Chinese part is enough here
        if not s or s.startswith("|"):
            continue
        s = re.sub(r"^#+\s*", "", s)
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
        s = re.sub(r"`([^`]*)`", r"\1", s)
        s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
        out.append(s)
        if len(out) >= max_lines:
            out.append("…")
            break
    return "\n".join(out)


def interpret(payload: bytes, current=__version__) -> dict:
    """Turn the API answer into {ok, newer, latest, page, download, notes} (or ok=False, error)."""
    try:
        d = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return {"ok": False, "error": "GitHub 返回的内容无法解析"}
    tag = d.get("tag_name") if isinstance(d, dict) else None
    if not tag or parse_version(tag) is None:
        msg = d.get("message") if isinstance(d, dict) else None
        return {"ok": False, "error": msg or "没有找到发布版本"}
    page = d.get("html_url") or RELEASES_URL
    return {"ok": True, "newer": is_newer(tag, current), "latest": tag.lstrip("vV"), "current": current,
            "page": page, "download": pick_asset(d.get("assets")) or page,
            "notes": notes_excerpt(d.get("body"))}


try:                                  # the Qt part (not needed by the tests above)
    from PySide6.QtCore import QObject, QUrl, Signal
    from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

    class UpdateChecker(QObject):
        """Asynchronous check; emits finished(dict) once (see interpret())."""
        finished = Signal(dict)

        def __init__(self, parent=None):
            super().__init__(parent)
            self.nam = QNetworkAccessManager(self)
            self.busy = False

        def check(self):
            if self.busy:
                return
            self.busy = True
            req = QNetworkRequest(QUrl(API_URL))
            req.setRawHeader(b"Accept", b"application/vnd.github+json")
            req.setRawHeader(b"User-Agent", f"GalvaPlot/{__version__}".encode())
            req.setTransferTimeout(12000)
            reply = self.nam.get(req)
            reply.finished.connect(lambda: self._done(reply))

        def _done(self, reply):
            self.busy = False
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            if reply.error() != QNetworkReply.NetworkError.NoError and not status:
                res = {"ok": False, "error": reply.errorString() or "网络错误"}
            elif status == 403:
                res = {"ok": False, "error": "GitHub 暂时限制了访问次数（每小时 60 次），请稍后再试"}
            elif status == 404:
                res = {"ok": False, "error": "还没有发布版本"}
            elif status and int(status) >= 400:
                res = {"ok": False, "error": f"GitHub 返回错误 {status}"}
            else:
                res = interpret(bytes(reply.readAll().data()))
            reply.deleteLater()
            self.finished.emit(res)
except ImportError:                   # pragma: no cover
    UpdateChecker = None
