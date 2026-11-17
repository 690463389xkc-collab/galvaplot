"""Curve names and annotation text.

Users type plain text. Two shortcuts give chemical formulas without LaTeX:
``AlCl_{3}`` -> AlCl₃ (subscript) and ``Li^{+}`` -> Li⁺ (superscript).
Text between ``$...$`` is passed to matplotlib mathtext unchanged.
"""
from __future__ import annotations

import os
import re

_LAND_SUFFIX = re.compile(r"_\d{3}_\d+$")      # LAND appends _<box>_<channel>, e.g. _006_2
_NEWARE_SUFFIX = re.compile(r"_\d+-\d+-\d+-\d{14}$")   # Neware: _<device>-<unit>-<channel>-<yyyymmddhhmmss>
_SUB = re.compile(r"_\{([^{}$]*)\}")
_SUP = re.compile(r"\^\{([^{}$]*)\}")


def default_name(path: str) -> str:
    stem = os.path.splitext(os.path.basename(path))[0]
    return _NEWARE_SUFFIX.sub("", _LAND_SUFFIX.sub("", stem)) or stem


_DATE = re.compile(r"^(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])$|^\d{4}[.-]\d{1,2}[.-]\d{1,2}$")


def shorten_names(names: list) -> list:
    """Drop date tokens (e.g. 20261101) and tokens shared by every name.

    Tokens are split at '-', '_' and spaces; pure numbers are never dropped
    (they usually number replicate cells). Returns the input unchanged if the
    result would be empty or not unique.
    """
    parts = [re.split(r"([-_ ]+)", n) for n in names]
    tok_sets = [{t.lower() for t in p[0::2] if t} for p in parts]
    common = set.intersection(*tok_sets) if len(names) > 1 else set()
    out = []
    for p in parts:
        keep, sep = [], ""
        for i, t in enumerate(p):
            if i % 2:
                sep = t
                continue
            if not t:
                continue
            drop = bool(_DATE.match(t)) or (t.lower() in common and not t.isdigit())
            if not drop:
                keep.append((sep if keep else "") + t)
            sep = ""
        out.append("".join(keep).strip("-_ "))
    if any(not o for o in out) or len(set(out)) < len(out):
        return list(names)
    return out


def _mathtext_ok(s: str) -> bool:
    try:
        from matplotlib.mathtext import MathTextParser
        p = MathTextParser("path")
        for seg in re.findall(r"\$([^$]+)\$", s):
            p.parse(f"${seg}$")
        return True
    except Exception:
        return False


def rich(s: str) -> str:
    """Convert the _{..}/^{..} shortcuts to mathtext; escape stray dollar signs."""
    if not s:
        return ""
    s = _SUB.sub(lambda m: "$_{\\mathrm{" + _esc(m.group(1)) + "}}$", s)
    s = _SUP.sub(lambda m: "$^{\\mathrm{" + _esc(m.group(1)) + "}}$", s)
    s = s.replace("$$", "")
    if s.count("$") % 2 or not _mathtext_ok(s):
        return s.replace("$", r"\$")
    return s


def _esc(t: str) -> str:
    return t.replace(" ", r"\ ").replace("%", r"\%")
