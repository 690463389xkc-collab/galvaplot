"""Draw the macOS disk-image background and the README "first launch" picture.

    python tools/make_dmg_art.py

Writes assets/dmg/background.png (640x480), background@2x.png (1280x960) and
docs/first-launch-macos.png. Then run tools/make_dmg_template.sh (needs Finder) to
turn the background into assets/dmg/template.dmg, which tools/make_dmg.sh uses.

The unsigned app is stopped by Gatekeeper on first launch; the prominent button in that
dialog is "Move to Trash", so the picture says plainly which button to press.
Needs a Mac (system font Hiragino Sans GB) and Pillow.
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"     # index 0 = W3, 2 = W6 (bold)

BG = "#f7f8fa"
TEXT = "#1f2328"
MUTED = "#5b6470"
ACCENT = "#2f5f9e"
RED = "#d7261e"
GREEN = "#2e9a48"
MAC_BLUE = "#3478f6"


class Canvas:
    def __init__(self, w, h, scale):
        self.s = scale
        self.im = Image.new("RGB", (w * scale, h * scale), BG)
        self.d = ImageDraw.Draw(self.im)

    def font(self, size, bold=False):
        return ImageFont.truetype(FONT, round(size * self.s), index=2 if bold else 0)

    def text(self, xy, s, size, color=TEXT, bold=False, anchor="la"):
        x, y = xy
        self.d.text((x * self.s, y * self.s), s, font=self.font(size, bold), fill=color, anchor=anchor)

    def width(self, s, size, bold=False):
        return self.d.textlength(s, font=self.font(size, bold)) / self.s

    def rrect(self, box, r, fill=None, outline=None, width=1):
        x0, y0, x1, y1 = box
        self.d.rounded_rectangle([x0 * self.s, y0 * self.s, x1 * self.s, y1 * self.s], radius=r * self.s,
                                 fill=fill, outline=outline, width=max(1, round(width * self.s)))

    def line(self, pts, color, width):
        self.d.line([(x * self.s, y * self.s) for x, y in pts], fill=color, width=max(1, round(width * self.s)),
                    joint="curve")

    def circle(self, cx, cy, r, fill):
        self.d.ellipse([(cx - r) * self.s, (cy - r) * self.s, (cx + r) * self.s, (cy + r) * self.s], fill=fill)

    def arrow(self, x0, x1, y, color, width=3, head=11):
        self.line([(x0, y), (x1 - head * 0.6, y)], color, width)
        s = self.s
        self.d.polygon([((x1) * s, y * s), ((x1 - head) * s, (y - head * 0.62) * s),
                        ((x1 - head) * s, (y + head * 0.62) * s)], fill=color)


def check(c, cx, cy, color=GREEN):
    c.circle(cx, cy, 9, color)
    c.line([(cx - 4.2, cy + 0.2), (cx - 1.2, cy + 3.4), (cx + 4.6, cy - 3.6)], "white", 2.2)


def cross(c, cx, cy, color=RED):
    c.circle(cx, cy, 9, color)
    c.line([(cx - 3.6, cy - 3.6), (cx + 3.6, cy + 3.6)], "white", 2.2)
    c.line([(cx - 3.6, cy + 3.6), (cx + 3.6, cy - 3.6)], "white", 2.2)


def button(c, x, y, label, primary):
    """macOS dialog button: blue default button or grey one. Returns its right edge."""
    w = c.width(label, 13) + 28
    c.rrect((x, y, x + w, y + 28), 14, fill=MAC_BLUE if primary else "#e3e5e8")
    c.text((x + w / 2, y + 14), label, 13, "white" if primary else TEXT, anchor="mm")
    return x + w


def steps(c, x, y, width):
    """The three first-launch steps; returns the y below them."""
    c.text((x, y), "第一次打开时（只需一次）", 17, TEXT, bold=True)
    y += 34

    def num(n, yy):
        c.circle(x + 10, yy + 9, 10, ACCENT)
        c.text((x + 10, yy + 9), str(n), 12, "white", bold=True, anchor="mm")

    tx = x + 30
    num(1, y)
    c.text((tx, y), "双击 GalvaPlot。系统提示“无法验证 / Not Opened”时：", 14)
    y += 30
    r = button(c, tx, y, "移到废纸篓  Move to Trash", True)
    cross(c, r + 16, y + 14)
    c.text((r + 31, y + 14), "不要点", 13, RED, bold=True, anchor="lm")
    bx = r + 31 + c.width("不要点", 13, True) + 26
    r2 = button(c, bx, y, "完成  Done", False)
    check(c, r2 + 16, y + 14)
    c.text((r2 + 31, y + 14), "点这个", 13, GREEN, bold=True, anchor="lm")
    y += 44
    num(2, y)
    c.text((tx, y), "打开「系统设置 → 隐私与安全性」，在“安全性”一栏", 14)
    c.text((tx, y + 22), "点「仍要打开 Open Anyway」，输入开机密码", 14)
    y += 52
    num(3, y)
    c.text((tx, y), "再双击 GalvaPlot 就能打开，以后不会再提示", 14)
    return y + 26


def background(scale):
    W, H = 640, 480
    c = Canvas(W, H, scale)
    # icons are drawn by Finder at (160, 140) and (480, 140), 112 pt
    c.arrow(244, 396, 140, ACCENT, 3, 13)
    c.text((320, 116), "拖进去安装", 14, ACCENT, bold=True, anchor="mm")
    c.text((320, 162), "Drag to Applications", 12, MUTED, anchor="mm")
    c.line([(32, 252), (W - 32, 252)], "#dde1e6", 1)
    steps(c, 36, 268, W - 72)
    return c.im


def readme_picture(scale=2):
    W, H = 600, 210
    c = Canvas(W, H, scale)
    c.rrect((1, 1, W - 1, H - 1), 10, outline="#dde1e6", width=1)
    steps(c, 22, 18, W - 44)
    return c.im


def main():
    out = os.path.join(ROOT, "assets", "dmg")
    os.makedirs(out, exist_ok=True)
    background(1).save(os.path.join(out, "background.png"))
    background(2).save(os.path.join(out, "background@2x.png"))
    readme_picture().save(os.path.join(ROOT, "docs", "first-launch-macos.png"))
    print("written:", out, "and docs/first-launch-macos.png")


if __name__ == "__main__":
    main()
