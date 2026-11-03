#!/usr/bin/env python3
"""Map Figma values to the project's own design tokens / valid Tailwind classes.

Usage:
  tokens.py text  --size 32 [--lh 40] [--weight 700] [--bp lg] [--top 3]
  tokens.py color --hex '#e84127'
  tokens.py space --px 50 [--prop mt]            # valid class for the project's Tailwind major
  tokens.py batch SPEC.json                      # spec.json from condense.py / figma_api.py
  common: [--theme VENDOR/THEME] [--tailwind-dir DIR] [--tw 3|4]

`text` parses the theme CSS (.class {..}, @utility name {..}, @apply text-xl md:text-2xl, nested
@screen/@media min-width, TW4 --text-* theme vars) and compares effective font-size / line-height /
weight at the breakpoint. `color` matches hex to --color-* vars and tailwind.config.js hex colours
(exact, else nearest by CIE76 dE). Limits: values built with calc()/clamp(), Tailwind default palette
references (colors.blue[600]) and plugin-generated utilities are not resolved -> reported as unparsed.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

BPS = ["base", "sm", "md", "lg", "xl", "2xl"]
BP_PX = {640: "sm", 768: "md", 1024: "lg", 1280: "xl", 1536: "2xl"}
TEXT = {"xs": (12, 16), "sm": (14, 20), "base": (16, 24), "lg": (18, 28), "xl": (20, 28), "2xl": (24, 32),
        "3xl": (30, 36), "4xl": (36, 40), "5xl": (48, 48), "6xl": (60, 60), "7xl": (72, 72), "8xl": (96, 96),
        "9xl": (128, 128)}
WEIGHT = {"thin": 100, "extralight": 200, "light": 300, "normal": 400, "medium": 500, "semibold": 600,
          "bold": 700, "extrabold": 800, "black": 900}
LEADING = {"none": 1, "tight": 1.25, "snug": 1.375, "normal": 1.5, "relaxed": 1.625, "loose": 2}
TW3_SCALE = [0, 1, 2, 4, 6, 8, 10, 12, 14, 16, 20, 24, 28, 32, 36, 40, 44, 48, 52, 56, 60, 64, 72, 80, 96, 112, 128,
             144, 160, 176, 192, 208, 224, 240, 256, 288, 320, 384]


# ------------------------------------------------------------------ css parsing

def walk(css: str):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out, frames, buf = [], [], ""
    for ch in css:
        if ch == "{":
            frames.append({"h": buf.strip(), "d": []})
            buf = ""
        elif ch == "}":
            if buf.strip() and frames:
                frames[-1]["d"].append(buf.strip())
            buf = ""
            if frames:
                f = frames.pop()
                out.append(([x["h"] for x in frames] + [f["h"]], f["d"]))
        elif ch == ";":
            if frames and buf.strip():
                frames[-1]["d"].append(buf.strip())
            buf = ""
        else:
            buf += ch
    return out


def to_px(v, theme):
    if v is None:
        return None
    v = v.strip()
    m = re.match(r"var\((--[\w-]+)(?:\s*,[^)]*)?\)$", v)
    if m:
        return to_px(theme.get(m.group(1)), theme)
    m = re.match(r"^(-?[\d.]+)(px|rem|em)?$", v)
    if not m:
        return None
    n = float(m.group(1))
    return n * 16 if m.group(2) in ("rem", "em") else n


def bp_of(headers):
    bp = "base"
    for h in headers:
        m = re.match(r"@screen\s+([\w]+)", h)
        if m and m.group(1) in BPS:
            bp = m.group(1)
        m = re.search(r"min-width:\s*([\d.]+)(px|rem)", h)
        if m:
            px = float(m.group(1)) * (16 if m.group(2) == "rem" else 1)
            names = [(abs(k - px), v) for k, v in BP_PX.items()]
            bp = min(names)[1]
    return bp


def theme_vars(files):
    tv = {}
    for f in files:
        for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", _lib.read(f)):
            tv.setdefault(k, v.strip())
    return tv


def apply_tokens(tokens, theme, rec):
    """Fold @apply utilities into rec = {bp: {size, lh, weight}}."""
    for tok in tokens.split():
        tok = tok.rstrip("!").lstrip("!")
        parts = tok.split(":")
        bp = parts[-2] if len(parts) > 1 and parts[-2] in BPS else "base"
        u = parts[-1]
        slot = rec.setdefault(bp, {})
        m = re.match(r"^text-(?:(xs|sm|base|lg|\dxl|xl))(?:/([\w.\[\]]+))?$", u)
        if m:
            key = m.group(1)
            size, lh = TEXT.get(key, (None, None))
            tv = theme.get(f"--text-{key}")
            if tv:
                size = to_px(tv, theme)
            tl = theme.get(f"--text-{key}--line-height")
            if tl:
                lhv = to_px(tl, theme)
                lh = lhv if lhv and lhv > 3 else (lhv * size if lhv and size else lh)
            slot["size"] = size
            slot.setdefault("lh", lh)
            continue
        m = re.match(r"^text-\[([\d.]+)px\]$", u)
        if m:
            slot["size"] = float(m.group(1))
            continue
        m = re.match(r"^font-(thin|extralight|light|normal|medium|semibold|bold|extrabold|black)$", u)
        if m:
            slot["weight"] = WEIGHT[m.group(1)]
            continue
        m = re.match(r"^font-\[(\d{3})\]$", u)
        if m:
            slot["weight"] = int(m.group(1))
            continue
        m = re.match(r"^leading-(.+)$", u)
        if m:
            v = m.group(1)
            if v in LEADING:
                slot["lh_ratio"] = LEADING[v]
            elif re.match(r"^\d+$", v):
                slot["lh"] = int(v) * 4.0
            else:
                mm = re.match(r"^\[([\d.]+)(px|rem)?\]$", v)
                if mm:
                    n = float(mm.group(1))
                    slot["lh"] = n * 16 if mm.group(2) == "rem" else (n if mm.group(2) else None)
                    if not mm.group(2):
                        slot["lh_ratio"] = n
            continue


def load_tokens(tw_dir: Path):
    files = _lib.css_files_of(tw_dir)
    theme = theme_vars(files)
    tokens, unparsed = {}, set()
    for f in files:
        for headers, decls in walk(_lib.read(f)):
            names = []
            for i, h in enumerate(headers):
                if re.match(r"^@utility\s+[\w-]+$", h):
                    names.append((i, h.split()[1]))
                elif re.match(r"^\.[\w-]+(\s*,\s*\.[\w-]+)*$", h):
                    names += [(i, n.strip()[1:]) for n in h.split(",")]
            if not names:
                continue
            i, _ = names[0]
            if not all(h.startswith("@") for h in headers[i + 1:]):
                continue
            bp = bp_of(headers[:i] + headers[i + 1:])
            for _, name in names:
                rec = tokens.setdefault(name, {})
                slot = rec.setdefault(bp, {})
                for d in decls:
                    if d.startswith("@apply"):
                        apply_tokens(d[6:], theme, rec)
                        slot = rec.setdefault(bp, {})
                        continue
                    if ":" not in d:
                        continue
                    prop, val = [x.strip() for x in d.split(":", 1)]
                    if prop == "font-size":
                        px = to_px(val, theme)
                        slot["size"] = px
                        if px is None:
                            unparsed.add(name)
                    elif prop == "line-height":
                        px = to_px(val, theme)
                        if px is not None and px > 3:
                            slot["lh"] = px
                        elif px is not None:
                            slot["lh_ratio"] = px
                        else:
                            unparsed.add(name)
                    elif prop == "font-weight":
                        slot["weight"] = WEIGHT.get(val, int(val) if val.isdigit() else None)
    # only keep tokens that set a font size somewhere (typography tokens)
    typo = {n: r for n, r in tokens.items() if any("size" in s and s["size"] for s in r.values())}
    return typo, unparsed


def effective(rec, bp):
    eff = {}
    for b in BPS[: BPS.index(bp) + 1]:
        for k, v in rec.get(b, {}).items():
            if v is not None:
                eff[k] = v
    if "lh" not in eff and "lh_ratio" in eff and eff.get("size"):
        eff["lh"] = eff["lh_ratio"] * eff["size"]
    return eff


def match_text(tokens, size, lh, weight, bp, top=3):
    rows = []
    for name, rec in tokens.items():
        e = effective(rec, bp)
        if not e.get("size"):
            continue
        diffs, score = [], 0.0
        for label, want, have in (("size", size, e.get("size")), ("lh", lh, e.get("lh")), ("weight", weight, e.get("weight"))):
            if want is None:
                continue
            if have is None and label == "weight":
                have = 400  # CSS default when a token sets no weight
            if have is None:
                diffs.append(f"{label} ?")
                score += 0.5
            elif abs(have - want) <= 0.6:
                diffs.append(f"{label} {want:g}✓")
            else:
                diffs.append(f"{label} {have:g}≠{want:g}")
                score += abs(have - want) / max(want, 1) + 1
        rows.append((score, name, diffs))
    rows.sort(key=lambda r: (r[0], r[1]))
    return rows[:top]


# ------------------------------------------------------------------ colors

def parse_color(v):
    v = v.strip()
    m = re.match(r"^#([0-9a-fA-F]{3,8})$", v)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.match(r"^rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)", v)
    if m:
        return tuple(int(x) for x in m.groups())
    m = re.match(r"^(\d{1,3})\s+(\d{1,3})\s+(\d{1,3})$", v)
    if m:
        return tuple(int(x) for x in m.groups())
    return None


def lab(rgb):
    def f(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = map(f, rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    t = lambda v: v ** (1 / 3) if v > 0.008856 else 7.787 * v + 16 / 116
    return 116 * t(y) - 16, 500 * (t(x) - t(y)), 200 * (t(y) - t(z))


def load_colors(tw_dir: Path):
    colors = {}
    for f in _lib.css_files_of(tw_dir):
        for k, v in re.findall(r"--color-([\w-]+)\s*:\s*([^;]+);", _lib.read(f)):
            rgb = parse_color(v)
            if rgb and k not in colors:
                colors[k] = rgb
    cfg = re.sub(r"//[^\n]*|/\*.*?\*/", "", _lib.read(tw_dir / "tailwind.config.js"), flags=re.S)
    for k, v in re.findall(r"""['"]?([\w-]+)['"]?\s*:\s*['"](#[0-9a-fA-F]{3,8})['"]""", cfg):
        rgb = parse_color(v)
        if rgb:
            colors.setdefault(k, rgb)
    colors.setdefault("white", (255, 255, 255))
    colors.setdefault("black", (0, 0, 0))
    return colors


def match_color(colors, hexv, top=3):
    rgb = parse_color(hexv)
    if not rgb:
        return None
    la = lab(rgb)
    rows = sorted(((sum((a - b) ** 2 for a, b in zip(la, lab(c))) ** 0.5, n) for n, c in colors.items()))
    return rows[:top]


# ------------------------------------------------------------------ spacing

def space_class(px, tw, prop=None):
    p = f"{prop}-" if prop else ""
    n = px / 4
    if tw >= 4:
        return f"{p}{n:g}" if (px * 4) % 1 == 0 and (n * 4) % 1 == 0 else f"{p}[{px:g}px]"
    if px == 1:
        return f"{p}px"
    if px in TW3_SCALE or px in (2, 6, 10, 14):
        return f"{p}{n:g}"
    return f"{p}[{px:g}px]"


# ------------------------------------------------------------------ cli

def context(a):
    if a.tailwind_dir:
        return None, Path(a.tailwind_dir), a.tw or 3
    root = _lib.find_root()
    info = _lib.project(root, theme=a.theme)
    tw_dir = Path(a.tailwind_dir) if a.tailwind_dir else root / info["themes"][info["target_theme"]]["tailwind"]["dir"]
    return info, tw_dir, a.tw or info["tw"] or 3


def run_text(tokens, size, lh, weight, bp, top, label=""):
    rows = match_text(tokens, size, lh, weight, bp, top)
    want = f"{size:g}/{lh:g}/w{weight}" if lh and weight else f"{size:g}"
    if not rows:
        return f"{label}text {want} @{bp}: NO TYPOGRAPHY TOKENS FOUND"
    best = rows[0]
    if best[0] == 0:
        return f"{label}text {want} @{bp}: EXACT .{best[1]}"
    alts = "; ".join(f".{n} ({' '.join(d)})" for _, n, d in rows)
    return f"{label}text {want} @{bp}: NO EXACT TOKEN — closest {alts}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["text", "color", "space", "batch"])
    ap.add_argument("spec", nargs="?")
    ap.add_argument("--size", type=float)
    ap.add_argument("--lh", type=float)
    ap.add_argument("--weight", type=int)
    ap.add_argument("--bp", default="xl", choices=BPS, help="effective breakpoint: base=375 frame, md=768, xl=1440 frame (check detect screens)")
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--hex")
    ap.add_argument("--px", type=float)
    ap.add_argument("--prop")
    ap.add_argument("--theme")
    ap.add_argument("--tailwind-dir")
    ap.add_argument("--tw", type=int)
    a = ap.parse_args()
    info, tw_dir, tw = context(a)

    if a.cmd == "text":
        tokens, unparsed = load_tokens(tw_dir)
        print(run_text(tokens, a.size, a.lh, a.weight, a.bp, a.top))
        if unparsed:
            print(f"(unparsed calc()/clamp() tokens: {', '.join(sorted(unparsed))})")
    elif a.cmd == "color":
        rows = match_color(load_colors(tw_dir), a.hex, a.top)
        if rows is None:
            print(f"color {a.hex}: cannot parse")
        elif rows[0][0] < 1:
            print(f"color {a.hex}: EXACT {rows[0][1]}  (bg-{rows[0][1]} / text-{rows[0][1]} / border-{rows[0][1]})")
        else:
            print(f"color {a.hex}: NO EXACT — nearest " + "; ".join(f"{n} (dE {d:.1f})" for d, n in rows))
    elif a.cmd == "space":
        print(f"space {a.px:g}px (TW{tw}): {space_class(a.px, tw, a.prop)}")
    else:
        spec = json.loads(_lib.read(a.spec))
        tokens, unparsed = load_tokens(tw_dir)
        colors = load_colors(tw_dir)
        seen = set()
        for t in spec.get("typography", []):
            for bp in ([t["bp"]] if t.get("bp") else [a.bp]):
                key = (t.get("size"), t.get("lh"), t.get("weight"), bp)
                if key in seen or not t.get("size"):
                    continue
                seen.add(key)
                print(run_text(tokens, t["size"], t.get("lh"), t.get("weight"), bp, 2, label=f"[{t.get('text', '')[:24]!r}] "))
        for c in spec.get("colors", []):
            rows = match_color(colors, c, 2)
            if rows:
                print(f"color {c}: " + (f"EXACT {rows[0][1]}" if rows[0][0] < 1 else "NO EXACT — nearest " + "; ".join(f"{n} (dE {d:.1f})" for d, n in rows)))
        sp = sorted({round(float(x["px"] if isinstance(x, dict) else x), 2) for x in spec.get("spacing", [])})
        if sp:
            print(f"spacing TW{tw}: " + ", ".join(f"{p:g}px->{space_class(p, tw)}" for p in sp))


if __name__ == "__main__":
    main()
