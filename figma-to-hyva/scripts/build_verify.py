#!/usr/bin/env python3
"""Quiet build + cache flush + Tailwind class presence check, in one call.

Usage:
  build_verify.py [--di] [--generate] [--skip-build] [--skip-flush] [--check-only] [--dry-run]
                  [--base REF] [--theme VENDOR/THEME] [FILE.phtml ...]

Steps (commands come from detect.py: Govard/Warden/DDEV prefixes, build-prod vs build, generate):
  1. [--generate] npm run generate   (TW4 hyva tokens, after editing hyva.config.json)
  2. CSS build                        3. cache:flush layout block_html full_page
  4. [--di] setup:di:compile          5. class check
Prints PASS/FAIL per step and only the last lines of a failing log. The class check extracts the
Tailwind-looking classes from changed (or given) .phtml files and verifies each exists in the built
styles.css — a class that "does nothing" (dynamic name, TW3 invalid spacing, stale build) shows up as MISSING.
Exit 1 on any failure or missing class.
"""
import argparse
import os
import re
import shlex
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

TAIL = 12


def css_escape(cls: str) -> str:
    out = ""
    for i, ch in enumerate(cls):
        if re.match(r"[A-Za-z0-9_-]", ch) and not (i == 0 and ch.isdigit()):
            out += ch
        else:
            out += "\\" + ch
    return out


def run(label, cmd, root, dry):
    if dry:
        print(f"WOULD RUN {label}: {cmd}")
        return True
    t0 = time.time()
    r = subprocess.run(shlex.split(cmd), cwd=root, capture_output=True, text=True)
    ok = r.returncode == 0
    print(f"{'PASS' if ok else 'FAIL'} {label} ({time.time() - t0:.0f}s)")
    if not ok:
        tail = (r.stdout + r.stderr).strip().splitlines()[-TAIL:]
        print("\n".join("  | " + l for l in tail))
    return ok


UTILITY = re.compile(
    r"^(?:[a-z0-9-]+:)*!?-?(?:p[xytblres]?|m[xytblres]?|w|h|min-[wh]|max-[wh]|size|gap(?:-[xy])?|space-[xy]|"
    r"grid(?:-cols|-rows|-flow)?|col-(?:span|start|end)|row-(?:span|start|end)|flex(?:-[a-z]+)?|items|justify|content|"
    r"self|place|order|text|font|leading|tracking|bg|border|rounded|shadow|ring|opacity|z|top|left|right|bottom|inset|"
    r"overflow|object|aspect|block|inline(?:-block|-flex|-grid)?|hidden|absolute|relative|fixed|sticky|static|float|"
    r"clear|cursor|select|pointer-events|transition|duration|ease|delay|animate|transform|translate|scale|rotate|"
    r"origin|fill|stroke|sr-only|underline|no-underline|uppercase|lowercase|capitalize|truncate|whitespace|break|"
    r"list|appearance|outline|divide|backdrop|blur|brightness|visible|invisible|container|decoration|line-clamp|"
    r"columns|basis|grow|shrink|table|contents|group|peer)(?:-|!|$)")


def template_classes(text: str):
    """Static class="..." values only (":class" holds Alpine expressions), Tailwind-looking tokens only."""
    found = set()
    for m in re.finditer(r"""(?<![:\w@-])class\s*=\s*(?:"([^"]*)"|'([^']*)')""", text):
        raw = m.group(1) if m.group(1) is not None else m.group(2)
        raw = re.sub(r"<\?.*?\?>", " ", raw, flags=re.S)
        for c in raw.split():
            if re.search(r"[<>$?{}\"']|__", c) or c in ("group", "peer"):
                continue
            if UTILITY.match(c) or "[" in c:
                found.add(c)
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--di", action="store_true")
    ap.add_argument("--generate", action="store_true")
    ap.add_argument("--skip-build", action="store_true")
    ap.add_argument("--skip-flush", action="store_true")
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--theme")
    a = ap.parse_args()
    root = _lib.find_root()
    info = _lib.project(root, theme=a.theme)
    cmds = info["cmds"]
    if not cmds:
        print("FAIL no environment/build commands detected (run detect.py, check CLAUDE.md)")
        sys.exit(1)
    ok = True
    if not a.check_only:
        if a.generate and "generate" in cmds:
            ok &= run("generate tokens", cmds["generate"], root, a.dry_run)
        if not a.skip_build and "build" in cmds and ok:
            ok &= run("css build", cmds["build"], root, a.dry_run)
        if not a.skip_flush and ok:
            ok &= run("cache flush", cmds["flush"], root, a.dry_run)
        if a.di and ok:
            ok &= run("di compile", cmds["di"], root, a.dry_run)
    missing_total = 0
    files = [os.path.abspath(f) for f in a.files] or [str(f) for f in _lib.git_changed(root, a.base, (".phtml",))]
    css = root / cmds.get("css_out", "")
    if not files:
        print("SKIP class check: no changed .phtml")
    elif not css.is_file():
        print(f"FAIL class check: {cmds.get('css_out')} not found (build first)")
        ok = False
    else:
        css_text = _lib.read(css)
        age = (time.time() - css.stat().st_mtime) / 60
        newest = max(os.path.getmtime(f) for f in files)
        stale = css.stat().st_mtime < newest and not a.dry_run
        for f in files:
            miss = []
            for c in sorted(template_classes(_lib.read(f))):
                base = c.lstrip("!").rstrip("!")
                if not re.search(r"\.(?:" + re.escape(css_escape(base)) + r"|" + re.escape(css_escape(c)) + r")(?![\w\\-])", css_text):
                    miss.append(c)
            if miss:
                missing_total += len(miss)
                print(f"MISSING in {os.path.relpath(f, root)}: {' '.join(miss[:40])}{' …' if len(miss) > 40 else ''}")
        print(f"{'PASS' if not missing_total else 'FAIL'} class check: {len(files)} file(s), {missing_total} class(es) not in "
              f"{cmds['css_out']} (built {age:.0f} min ago{', OLDER than templates -> rebuild' if stale else ''})")
        print("  note: custom/JS-only classes and Alpine-toggled strings may be listed; judge each (TW-1/TW-3 are the usual cause)")
    sys.exit(0 if ok and not missing_total else 1)


if __name__ == "__main__":
    main()
