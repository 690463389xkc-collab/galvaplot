"""Check GitHub for a newer release.

Only one request is made: GET https://api.github.com/repos/<REPO>/releases/latest
(no account, no data about the user or their files; GitHub sees the IP address and the
User-Agent "GalvaPlot/<version>"). Nothing is downloaded or installed automatically: the
user is pointed to the download.
"""
from __future__ import annotations

import json
import os
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


def asset_info(assets, system=None, machine=None):
    """The package for this computer as {name, url, size, sha256}, or None.

    sha256 comes from the "digest" GitHub publishes for every release asset; it is None
    when GitHub did not give one (then the app does not install the file by itself)."""
    system = system or sys.platform
    machine = (machine or platform.machine()).lower()
    if system == "win32":
        want = ("-windows-setup.exe",)
    elif system == "darwin" and machine in ("arm64", "aarch64"):
        want = ("-macos-applesilicon.dmg",)
    else:
        return None
    for a in assets or ():
        name = str(a.get("name", ""))
        if name.lower().endswith(want) and a.get("browser_download_url"):
            m = re.fullmatch(r"sha256:([0-9a-fA-F]{64})", str(a.get("digest") or ""))
            return {"name": name, "url": a["browser_download_url"], "size": int(a.get("size") or 0),
                    "sha256": m.group(1).lower() if m else None}
    return None


def pick_asset(assets, system=None, machine=None):
    """Download URL of the package for this computer, or None (then the release page is used)."""
    a = asset_info(assets, system, machine)
    return a["url"] if a else None


def current_version():
    """The running version. GALVAPLOT_FAKE_VERSION pretends to be older (for testing updates)."""
    return os.environ.get("GALVAPLOT_FAKE_VERSION") or __version__


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


def interpret(payload: bytes, current=None) -> dict:
    """Turn the API answer into {ok, newer, latest, current, page, download, asset, notes}
    (or ok=False, error)."""
    current = current or current_version()
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
            "asset": asset_info(d.get("assets")), "notes": notes_excerpt(d.get("body"))}


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
            req.setRawHeader(b"User-Agent", f"GalvaPlot/{__version__}".encode())   # the real version
            token = os.environ.get("GALVAPLOT_GITHUB_TOKEN")      # CI only: avoids the shared rate limit
            if token:
                req.setRawHeader(b"Authorization", f"Bearer {token}".encode())
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

    class Downloader(QObject):
        """Download one file to `dest`; progress(received, total) and finished(path, error)."""
        progress = Signal(int, int)
        finished = Signal(str, str)

        def __init__(self, parent=None):
            super().__init__(parent)
            self.nam = QNetworkAccessManager(self)
            self.reply = None
            self.file = None
            self.dest = ""
            self.aborted = False

        def get(self, url, dest):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            self.dest, self.aborted = dest, False
            self.file = open(dest + ".part", "wb")
            req = QNetworkRequest(QUrl(url))
            req.setRawHeader(b"User-Agent", f"GalvaPlot/{__version__}".encode())
            req.setTransferTimeout(60000)              # per stalled transfer, not in total
            self.reply = self.nam.get(req)               # GitHub redirects https -> https: followed
            self.reply.readyRead.connect(self._read)
            self.reply.downloadProgress.connect(lambda got, total: self.progress.emit(int(got), int(total)))
            self.reply.finished.connect(self._done)

        def abort(self):
            if self.reply is not None and not self.aborted:
                self.aborted = True
                self.reply.abort()

        def _read(self):
            if self.file:
                self.file.write(bytes(self.reply.readAll().data()))

        def _done(self):
            reply, self.reply = self.reply, None
            self._read_rest(reply)
            self.file.close()
            self.file = None
            status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            err = ""
            if self.aborted:
                err = "已取消"
            elif reply.error() != QNetworkReply.NetworkError.NoError:
                err = reply.errorString() or "网络错误"
            elif status and int(status) >= 400:
                err = f"服务器返回错误 {status}"
            reply.deleteLater()
            part = self.dest + ".part"
            if err:
                try:
                    os.remove(part)
                except OSError:
                    pass
                self.finished.emit("", err)
                return
            os.replace(part, self.dest)
            self.finished.emit(self.dest, "")

        def _read_rest(self, reply):
            if self.file and reply is not None:
                rest = bytes(reply.readAll().data())
                if rest:
                    self.file.write(rest)
except ImportError:                   # pragma: no cover
    UpdateChecker = Downloader = None
