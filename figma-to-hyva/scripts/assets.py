#!/usr/bin/env python3
"""Validate and place exported Figma assets into the Hyvä theme (dedupe by content hash).

Usage:
  python3 -I assets.py place FILE... [--subdir svg|images] [--theme VENDOR/THEME] [--rename name.ext] [--dry-run]
  python3 -I assets.py find FILE...        # only report exact duplicates already in the theme

For each file: refuses empty/non-image files, reports SVG root width/height (never edited), looks for
a byte-identical (or SVG-normalised identical) file already in the theme's web/images|svg and, if
found, tells you to reuse it. Otherwise optimises SVG with svgo when available (npx --no-install)
and copies it, printing the `$block->getViewFileUrl('...')` expression to use.
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

EXTS = {".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}


def norm_hash(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix == ".svg":
        data = re.sub(rb"\s+", b" ", re.sub(rb"<!--.*?-->", b"", data, flags=re.S)).strip()
    return hashlib.sha256(data).hexdigest()


def svg_dims(path: Path):
    head = _lib.read(path)[:2000]
    m = re.search(r"<svg\b[^>]*>", head, re.S)
    if not m:
        return None
    w = re.search(r'\bwidth="([^"]+)"', m.group(0))
    h = re.search(r'\bheight="([^"]+)"', m.group(0))
    vb = re.search(r'viewBox="([^"]+)"', m.group(0))
    return (w.group(1) if w else None, h.group(1) if h else None, vb.group(1) if vb else None)


def index_theme(tdir: Path) -> dict:
    idx = {}
    for sub in ("web/images", "web/svg", "web/icons"):
        for p in (tdir / sub).rglob("*"):
            if p.is_file() and p.suffix.lower() in EXTS:
                idx.setdefault(norm_hash(p), p)
    return idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["place", "find"])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--subdir")
    ap.add_argument("--theme")
    ap.add_argument("--rename")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    root = _lib.find_root()
    info = _lib.project(root, theme=a.theme)
    tdir = _lib.theme_path(info, root)
    idx = index_theme(tdir)
    bad = 0
    for f in map(Path, a.files):
        if not f.is_file() or f.stat().st_size == 0:
            print(f"FAIL {f}: missing or empty")
            bad += 1
            continue
        if f.suffix.lower() not in EXTS:
            print(f"FAIL {f}: not an image asset")
            bad += 1
            continue
        extra = ""
        if f.suffix == ".svg":
            d = svg_dims(f)
            if not d:
                print(f"FAIL {f}: no <svg> root")
                bad += 1
                continue
            extra = f" svg width={d[0]} height={d[1]} viewBox={d[2]}"
            if not d[0] or not d[1]:
                extra += " (WARNING: root has no width/height)"
        dup = idx.get(norm_hash(f))
        if dup:
            rel = dup.relative_to(tdir / "web")
            print(f"REUSE {f.name}: identical to {dup.relative_to(root)} -> $block->getViewFileUrl('{rel}'){extra}")
            continue
        if a.cmd == "find":
            print(f"NEW   {f.name}: no identical asset in theme{extra}")
            continue
        sub = a.subdir or ("svg" if f.suffix == ".svg" else "images")
        sub = "images" if sub not in ("svg", "images") else sub
        name = a.rename if a.rename and len(a.files) == 1 else f.name
        name = re.sub(r"[^\w.-]+", "-", name).lower()
        dest = tdir / "web" / sub / name
        if dest.exists():
            print(f"FAIL {f.name}: {dest.relative_to(root)} already exists (different content) — use --rename")
            bad += 1
            continue
        if a.dry_run:
            print(f"WOULD PLACE {f.name} -> {dest.relative_to(root)}{extra}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, dest)
        opt = ""
        if dest.suffix == ".svg" and shutil.which("npx"):
            r = subprocess.run(["npx", "--no-install", "svgo", "--multipass", str(dest)], capture_output=True, text=True, timeout=60)
            opt = " (svgo applied)" if r.returncode == 0 else " (svgo unavailable)"
            d2 = svg_dims(dest)
            if d2 and d2[:2] != svg_dims(f)[:2]:
                shutil.copyfile(f, dest)  # keep original root width/height
                opt = " (svgo changed root size -> original kept)"
        print(f"PLACED {dest.relative_to(root)}{opt}{extra} -> $block->getViewFileUrl('{sub}/{name}')")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
