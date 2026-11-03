#!/usr/bin/env python3
"""Generate the final completion checklist with automated evidence (ticks only what a script verified).

Usage:
  report.py [--base REF] [--browser] [--visual-diff PCT] [--gate-ok] [--figma-calls N] [--note TEXT]

Runs lint (changed lines), i18n check and the Tailwind class check (read-only, no build), then prints
the markdown checklist. Manual items stay [ ] unless you pass the flag proving them
(--browser = checked in a real browser at the 3 widths, --visual-diff PCT = measured diff,
--gate-ok = project quality gate passed). Also appends a line to var/figma-to-hyva/runs.jsonl.
"""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def run(script, *args):
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, script), *args], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--browser", action="store_true")
    ap.add_argument("--visual-diff", type=float)
    ap.add_argument("--gate-ok", action="store_true")
    ap.add_argument("--figma-calls", type=int, default=0)
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    root = _lib.find_root()
    info = _lib.project(root)
    files = _lib.git_changed(root, a.base, (".phtml", ".php", ".xml", ".css", ".csv", ".js"))

    rc_lint, out_lint = run("lint_phtml.py", "--changed", "--base", a.base)
    rc_i18n, out_i18n = run("i18n_sync.py", "--changed", "--base", a.base)
    rc_cls, out_cls = run("build_verify.py", "--check-only", "--base", a.base)
    errors = [l for l in out_lint.splitlines() if " error:" in l]
    tick = lambda ok: "x" if ok else " "
    lint_summary = out_lint.splitlines()[-1] if out_lint else "lint: n/a"
    vis = f"{a.visual_diff:.1f}% pixels differ" if a.visual_diff is not None else "not measured"
    lines = [
        f"## Completion checklist ({len(files)} changed file(s); csp={info['csp_mode']} TW{info['tw']})", "",
        f"- [{tick(rc_lint == 0)}] **Lint** (ALP/TW/TPL/A11Y on changed lines): {lint_summary}",
        f"- [{tick(rc_i18n == 0)}] **i18n**: {out_i18n.splitlines()[-1] if out_i18n else 'n/a'}",
        f"- [{tick(rc_cls == 0)}] **Tailwind classes present in built CSS**: {out_cls.splitlines()[-2] if len(out_cls.splitlines()) > 1 else out_cls}",
        f"- [{tick(a.gate_ok)}] **Quality gate** ({info['gate']}): {'passed' if a.gate_ok else 'not recorded'}",
        f"- [{tick(a.browser)}] **Browser** mobile/md/desktop, console clean, interactions + empty states: {'checked' if a.browser else 'NOT checked'}",
        f"- [{tick(a.visual_diff is not None and a.visual_diff < 2)}] **Visual diff vs Figma**: {vis}",
        "- [ ] **Traced** layout XML -> block/ViewModel -> template (manual, state it)",
        "- [ ] **Assets** all in place, local, right size (assets.py output)", "",
    ]
    if errors:
        lines += ["### Lint errors to fix", *errors[:15], ""]
    if rc_i18n and out_i18n:
        lines += ["### i18n", *out_i18n.splitlines()[:12], ""]
    if rc_cls and out_cls:
        lines += ["### Class check", *[l for l in out_cls.splitlines() if l.startswith(("MISSING", "FAIL"))][:8], ""]
    print("\n".join(lines))
    try:
        entry = {"ts": int(time.time()), "files": len(files), "lint_errors": len(errors), "figma_calls": a.figma_calls,
                 "i18n_ok": rc_i18n == 0, "classes_ok": rc_cls == 0, "browser": a.browser, "visual_diff": a.visual_diff,
                 "note": a.note}
        with open(_lib.cache_dir(root) / "runs.jsonl", "a") as fh:
            fh.write(json.dumps(entry) + "\n")
    except OSError:
        pass
    sys.exit(0 if rc_lint == 0 and rc_i18n == 0 and rc_cls == 0 else 1)


if __name__ == "__main__":
    main()
