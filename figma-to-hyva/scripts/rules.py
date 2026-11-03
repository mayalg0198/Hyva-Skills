#!/usr/bin/env python3
"""Print only the Hyvä rules that apply to this project (cuts the rule text the model must read).

Usage: rules.py [--csp strict|ready] [--tw 3|4] [--hyvacsp yes|no] [--sections 1,2,3,4,5] [--compact] [--theme V/T]

references/hyva-rules.md carries conditional blocks:
    <!--if csp=strict-->...<!--/if-->   <!--if tw=3-->...   <!--if hyvacsp=no-->...
A block is kept only when the project's value (detect.py cache, or the flags) matches. Markers are
stripped from the output. --sections keeps only the numbered `## N.` sections (default: all).
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

RULES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references", "hyva-rules.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csp", choices=["strict", "ready"])
    ap.add_argument("--tw", choices=["3", "4"])
    ap.add_argument("--hyvacsp", choices=["yes", "no"])
    ap.add_argument("--sections")
    ap.add_argument("--compact", action="store_true", help="drop fenced code examples and tables")
    ap.add_argument("--theme")
    a = ap.parse_args()
    ctx = {"csp": a.csp, "tw": a.tw, "hyvacsp": a.hyvacsp}
    if None in ctx.values():
        info = _lib.project(_lib.find_root(), theme=a.theme)
        ctx["csp"] = ctx["csp"] or info["csp_mode"]
        ctx["tw"] = ctx["tw"] or str(info["tw"] or 3)
        ctx["hyvacsp"] = ctx["hyvacsp"] or ("yes" if info["hyvacsp"] else "no")
    text = _lib.read(RULES)
    pat = re.compile(r"<!--if (\w+)=(\w+)-->\n?(.*?)<!--/if-->\n?", re.S)
    text = pat.sub(lambda m: m.group(3) if ctx.get(m.group(1)) == m.group(2) else "", text)
    if a.sections:
        keep = set(a.sections.split(","))
        parts = re.split(r"(?m)^(?=## \d+\. )", text)
        text = parts[0] + "".join(p for p in parts[1:] if re.match(r"## (\d+)\.", p).group(1) in keep)
    if a.compact:
        text = re.sub(r"```.*?```\n?", "", text, flags=re.S)
        text = re.sub(r"(?m)^\|.*\|\n", "", text)
    print(f"<!-- rules for csp={ctx['csp']} TW{ctx['tw']} hyvacsp={ctx['hyvacsp']} -->")
    print(re.sub(r"\n{3,}", "\n\n", text).strip())


if __name__ == "__main__":
    main()
