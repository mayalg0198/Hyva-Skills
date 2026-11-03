#!/usr/bin/env python3
"""Numeric visual diff between the Figma screenshot and the page screenshot (needs Pillow).

Usage: pixel_diff.py FIGMA.png WEB.png [--tol 24] [--max-pct 2.0] [--out diff.png] [--grid 8]

Resizes WEB to FIGMA's width (aspect kept) and compares the common height. Prints % of differing
pixels (per-channel tolerance --tol), the height mismatch, and the worst grid cells as pixel boxes —
so the model reads 5 lines instead of looking at images. Writes the diff image only when the
threshold is exceeded. Exit 1 over threshold; 3 when Pillow is missing (fall back to eyeballing).
"""
import argparse
import sys

try:
    from PIL import Image, ImageChops
except ImportError:
    print("Pillow missing: pip install pillow (or compare screenshots visually)")
    sys.exit(3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("figma")
    ap.add_argument("web")
    ap.add_argument("--tol", type=int, default=24)
    ap.add_argument("--max-pct", type=float, default=2.0)
    ap.add_argument("--out", default="diff.png")
    ap.add_argument("--grid", type=int, default=8)
    a = ap.parse_args()
    f = Image.open(a.figma).convert("RGB")
    w = Image.open(a.web).convert("RGB")
    if w.width != f.width:
        w = w.resize((f.width, round(w.height * f.width / w.width)))
    h = min(f.height, w.height)
    f, w = f.crop((0, 0, f.width, h)), w.crop((0, 0, w.width, h))
    diff = ImageChops.difference(f, w)
    mask = diff.point(lambda v: 255 if v > a.tol else 0).convert("L")
    bad = sum(1 for p in mask.getdata() if p)
    total = f.width * h
    pct = 100 * bad / total
    gx, gy = f.width / a.grid, h / a.grid
    cells = []
    for j in range(a.grid):
        for i in range(a.grid):
            box = (round(i * gx), round(j * gy), round((i + 1) * gx), round((j + 1) * gy))
            c = mask.crop(box)
            n = sum(1 for p in c.getdata() if p)
            if n:
                cells.append((100 * n / ((box[2] - box[0]) * (box[3] - box[1])), box))
    cells.sort(reverse=True)
    print(f"visual diff: {pct:.2f}% pixels differ (tol {a.tol}), compared {f.width}x{h}, "
          f"height figma/web: {Image.open(a.figma).height}/{Image.open(a.web).height}"
          + ("  <- HEIGHT MISMATCH" if abs(Image.open(a.figma).height - Image.open(a.web).height) > 8 else ""))
    for p, b in cells[:5]:
        print(f"  worst cell {p:5.1f}% at x{b[0]}-{b[2]} y{b[1]}-{b[3]}")
    if pct > a.max_pct:
        Image.blend(f, mask.convert("RGB").point(lambda v: v), 0.0)
        out = w.copy()
        out.paste((255, 0, 0), mask=mask)
        out.save(a.out)
        print(f"over {a.max_pct}% -> diff image: {a.out}")
        sys.exit(1)
    print("within threshold")


if __name__ == "__main__":
    main()
