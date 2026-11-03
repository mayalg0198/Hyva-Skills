#!/usr/bin/env python3
"""Compare spec.json (from condense.py / figma_api.py) with computed styles from the browser.

Usage: style_compare.py SPEC.json COMPUTED.json [--tol 0.6]
COMPUTED.json = output of scripts/computed_styles.js. Elements are matched by their text. Prints only
mismatches (font-size, line-height, weight, colour) and spec texts not found on the page. Exit 1 on any.
"""
import argparse
import json
import re
import sys


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("computed")
    ap.add_argument("--tol", type=float, default=0.6)
    a = ap.parse_args()
    spec = json.load(open(a.spec))
    comp = json.load(open(a.computed))
    if comp.get("error"):
        print(comp["error"])
        sys.exit(1)
    page = {norm(i["text"]): i for i in comp["items"]}
    bad = 0
    for t in spec.get("typography", []):
        for sample in t.get("samples") or [t.get("text", "")]:
            key = norm(sample)
            hit = page.get(key) or next((v for k, v in page.items() if key and (k.startswith(key[:20]) or key.startswith(k[:20]))), None)
            if not hit:
                print(f"NOT FOUND on page: {sample!r}")
                bad += 1
                continue
            diffs = []
            if t.get("size") and abs(hit["size"] - t["size"]) > a.tol:
                diffs.append(f"font-size {hit['size']:g} (figma {t['size']:g})")
            if t.get("lh") and hit["lh"] is not None and abs(hit["lh"] - t["lh"]) > a.tol:
                diffs.append(f"line-height {hit['lh']:g} (figma {t['lh']:g})")
            if t.get("weight") and hit["weight"] != t["weight"]:
                diffs.append(f"weight {hit['weight']} (figma {t['weight']})")
            if t.get("color") and hit["color"].lower() != t["color"].lower():
                diffs.append(f"color {hit['color']} (figma {t['color']})")
            if diffs:
                bad += 1
                print(f"MISMATCH {sample!r} <{hit['tag']}>: " + "; ".join(diffs))
    print(f"style compare @{comp.get('viewport')}px: {bad} problem(s) over {len(page)} text element(s)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
