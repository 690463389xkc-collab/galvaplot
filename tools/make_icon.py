"""Draw the app icon (assets/icon.png, icon.ico, icon.icns). Run once; outputs are committed."""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "assets")
S = 1024


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def main():
    os.makedirs(OUT, exist_ok=True)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # vertical gradient in a rounded square
    grad = Image.new("RGBA", (S, S))
    top, bot = (58, 113, 184), (24, 52, 98)
    d = ImageDraw.Draw(grad)
    for y in range(S):
        d.line([(0, y), (S, y)], fill=lerp(top, bot, y / S) + (255,))
    mask = Image.new("L", (S, S), 0)
    m = 96
    ImageDraw.Draw(mask).rounded_rectangle([m, m, S - m, S - m], radius=190, fill=255)
    img.paste(grad, (0, 0), mask)

    # charge (up) and discharge (down) curves, drawn at 2x and downsampled for smooth edges
    K = 2
    lay = Image.new("RGBA", (S * K, S * K), (0, 0, 0, 0))
    dl = ImageDraw.Draw(lay)
    x0, x1, y0, y1 = 250, 790, 730, 300
    x = np.linspace(0, 1, 1500)
    up = 0.08 + 0.72 * x + 0.12 * np.exp(-(1 - x) * 14) - 0.08 * np.exp(-x * 14)
    dn = 0.92 - 0.72 * x - 0.12 * np.exp(-(1 - x) * 14) + 0.08 * np.exp(-x * 14)
    r = 21 * K
    dl.rectangle([200 * K, 262 * K, 216 * K, 776 * K], fill=(255, 255, 255, 140))   # y axis
    dl.rectangle([200 * K, 760 * K, 820 * K, 776 * K], fill=(255, 255, 255, 140))   # x axis
    for curve, col in ((up, (255, 255, 255, 255)), (dn, (255, 196, 92, 255))):
        for a, b in zip(x, curve):
            cx, cy = (x0 + (x1 - x0) * a) * K, (y0 + (y1 - y0) * b) * K
            dl.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    lay = lay.resize((S, S), Image.LANCZOS)
    img.alpha_composite(lay)
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([m, m + 18, S - m, S - m + 18], radius=190, fill=(0, 0, 0, 70))
    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    final = Image.alpha_composite(shadow, img)
    final.save(os.path.join(OUT, "icon.png"))
    final.save(os.path.join(OUT, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    try:
        final.save(os.path.join(OUT, "icon.icns"))
    except Exception as e:  # .icns writing needs a recent Pillow; macOS builds can also use iconutil
        print("icns not written:", e, file=sys.stderr)
    print("written to", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
