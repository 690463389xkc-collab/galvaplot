"""Figure style: fonts, rcParams, colours, line styles."""
from __future__ import annotations

import logging
from functools import lru_cache

logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
logging.getLogger("fontTools").setLevel(logging.ERROR)   # font subsetting chatter when saving PDF/SVG

# Categorical order checked for colour-vision deficiency (OKLab ΔE, Machado 2009):
# adjacent pairs ≥ 15 under normal vision; first slots match common journal style.
PALETTE = ["#1a1a1a", "#2f5f9e", "#d7261e", "#e8890c", "#d660a0",
           "#9c5a2e", "#1fa3b5", "#7b4fa8", "#2e9a48", "#808080"]
PALETTE_NAMES = ["黑", "蓝", "红", "橙", "粉", "棕", "青", "紫", "绿", "灰"]

LINESTYLES = {
    "solid": "-",
    "dashed": (0, (4, 2.2)),
    "dotted": (0, (1, 1.6)),
    "dashdot": (0, (5, 2, 1.2, 2)),
}
LINESTYLE_LABELS = {"solid": "实线", "dashed": "虚线", "dotted": "点线", "dashdot": "点划线"}

# single-hue ramp (light -> dark) for "cycle number" colouring
RAMP_LIGHT, RAMP_DARK = "#86a9d6", "#0b2347"

_LATIN = ["Arial", "Helvetica", "Liberation Sans", "Arimo"]
_CJK = ["Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", "Heiti SC", "STHeiti", "SimHei",
        "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei", "Arial Unicode MS"]


@lru_cache(maxsize=1)
def font_families():
    from matplotlib import font_manager
    have = {f.name for f in font_manager.fontManager.ttflist}
    fam = [f for f in _LATIN if f in have][:1] + [f for f in _CJK if f in have] + ["DejaVu Sans"]
    return fam


_CFF_CACHE = {}


def outline_is_cff(family) -> bool:
    """True if the font file behind `family` has CFF (PostScript) outlines, e.g. macOS
    PingFang. Such fonts cannot be embedded as TrueType (Type 42) in PDF/EPS: Ghostscript,
    Acrobat and Illustrator then show missing or wrong glyphs, although macOS Preview copes."""
    if family in _CFF_CACHE:
        return _CFF_CACHE[family]
    cff = False
    try:
        from fontTools.ttLib import TTFont
        from matplotlib import font_manager
        path = font_manager.findfont(font_manager.FontProperties(family=family), fallback_to_default=False)
        kw = {"fontNumber": 0} if path.lower().endswith((".ttc", ".otc")) else {}
        with TTFont(path, lazy=True, **kw) as f:
            cff = "CFF " in f or "CFF2" in f
    except Exception:
        cff = False
    _CFF_CACHE[family] = cff
    return cff


def cjk_family(families):
    """The Chinese font matplotlib falls back to for CJK characters (first CJK family)."""
    return next((f for f in families if f in _CJK), None)


def has_cjk(text) -> bool:
    return any(ord(ch) >= 0x2E80 for ch in str(text or ""))


def rc(font_size: float = 14.0, cjk: bool = False) -> dict:
    """rcParams for a figure. cjk=True: mathtext uses the CJK font, because
    mathtext has no per-glyph fallback and Chinese text next to a formula
    would otherwise render as empty boxes."""
    s = font_size / 14.0
    fam = font_families()
    latin = fam[0] if fam[0] != "DejaVu Sans" else None
    if cjk and len(fam) > 1:
        cj = [f for f in fam if f in _CJK]
        if cj:
            latin = cj[0]
    d = {
        "font.family": fam,
        "font.size": 14 * s, "axes.labelsize": 15 * s, "axes.titlesize": 14 * s,
        "xtick.labelsize": 14 * s, "ytick.labelsize": 14 * s, "legend.fontsize": 12.5 * s,
        "axes.linewidth": 1.2, "axes.grid": False, "axes.unicode_minus": True,
        "axes.titlepad": 8,
        "xtick.direction": "in", "ytick.direction": "in",
        "xtick.major.size": 5, "ytick.major.size": 5, "xtick.minor.size": 2.8, "ytick.minor.size": 2.8,
        "xtick.major.width": 1.2, "ytick.major.width": 1.2, "xtick.minor.width": 1.0, "ytick.minor.width": 1.0,
        "xtick.major.pad": 6, "ytick.major.pad": 6, "xtick.minor.visible": True, "ytick.minor.visible": True,
        "legend.frameon": False, "legend.handlelength": 2.6, "lines.linewidth": 2.0,
        "savefig.facecolor": "white", "figure.facecolor": "white", "axes.facecolor": "white",
        "svg.fonttype": "path", "pdf.fonttype": 42, "ps.fonttype": 42,   # PDF/EPS: embedded TrueType, editable text
    }
    if latin:
        d.update({"mathtext.fontset": "custom", "mathtext.rm": latin, "mathtext.it": f"{latin}:italic",
                  "mathtext.bf": f"{latin}:bold", "mathtext.sf": latin})
    else:
        d["mathtext.fontset"] = "dejavusans"
    return d


def ramp(n: int) -> list:
    """n colours from light to dark along one hue."""
    import numpy as np
    from matplotlib.colors import to_rgb, to_hex
    a, b = np.array(to_rgb(RAMP_LIGHT)), np.array(to_rgb(RAMP_DARK))
    if n <= 1:
        return [to_hex(b)]
    return [to_hex(a + (b - a) * k / (n - 1)) for k in range(n)]
