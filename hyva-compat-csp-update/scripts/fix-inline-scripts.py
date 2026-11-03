#!/usr/bin/env python3
"""
fix-inline-scripts.py — Automated CSP registration fixer for Hyvä templates
===========================================================================
Hyvä's registerInlineScript() reads ob_get_contents() for the LAST CLOSED
<script> element, so the call must sit IMMEDIATELY AFTER `</script>`.

Per template, in HTML context only (scripts inside PHP strings, heredocs, PHP
comments or HTML comments are left alone):
  1. Removes registrations misplaced INSIDE a <script> block.
  2. Adds `<?php $hyvaCsp->registerInlineScript() ?>` (Hyvä's own form) right after
     every executable inline </script> that has none.
  3. --guarded: inserts `<?php isset($hyvaCsp) && $hyvaCsp->registerInlineScript(); ?>`
     instead and also wraps existing bare calls — for compat modules whose templates
     may render on Luma or on theme-module versions that predate $hyvaCsp.
  4. --normalize: rewrites `$viewModels->require(HyvaCsp::class)->registerInline…()` to the
     injected `$hyvaCsp->…` (guarded form when --guarded or when HyvaCsp does not exist).
Scripts whose text changes on every render (uniqid/rand/time, directly or via a variable)
are NOT registered: registering them mints a new hash per render and bloats the cached CSP
header. They are listed so the value can be moved to data-* first.
Each written file is checked with `php -l` (when php is on PATH) and reverted if
the lint fails. Files under vendor/, generated/, var/, pub/static/ are refused
unless --include-generated is given.

Usage:
  python3 scripts/fix-inline-scripts.py <path> [--dry-run] [--guarded] [--normalize] [--include-generated]
"""

from __future__ import annotations

import argparse
import difflib
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import csp_common as cc
from csp_common import BOLD, CYAN, DIM, GREEN, RED, RESET, YELLOW

SCRIPT_PAIR_RE = re.compile(
    r"(?P<indent>^[ \t]*)?<script\b(?P<attrs>[^>]*)>(?P<body>.*?)</script>",
    re.DOTALL | re.IGNORECASE | re.MULTILINE
)

MISPLACED_INSIDE_RE = re.compile(
    r"^[ \t]*<\?php\s+(?:if\s*\(\s*isset\(\s*\$hyvaCsp\s*\)\s*\)\s*|\s*isset\(\s*\$hyvaCsp\s*\)\s*&&\s*|\s*)"
    r"\$hyvaCsp->registerInlineScript\(\s*\)\s*;?\s*\?>\s*\n?",
    re.IGNORECASE | re.MULTILINE
)

REGISTRATION_BARE = "<?php $hyvaCsp->registerInlineScript() ?>"
REGISTRATION_GUARDED = "<?php isset($hyvaCsp) && $hyvaCsp->registerInlineScript(); ?>"


def fix_content(content: str, guarded: bool = False, normalize: bool = False,
                force_guard_normalized: bool = False) -> tuple[str, list]:
    """Return (new content, line numbers of scripts left unregistered because nondeterministic)."""
    # 1. Remove registrations misplaced INSIDE <script> blocks (HTML context only)
    spans = cc.non_html_spans(content)

    def clean_inside(m: re.Match) -> str:
        if cc.in_spans(m.start(), spans):
            return m.group(0)
        body = m.group("body")
        if cc.HYVA_CSP_REGISTER_CALL_RE.search(body):
            cleaned = MISPLACED_INSIDE_RE.sub("", body)
            if cleaned != body:
                return m.group(0).replace(body, cleaned, 1)
        return m.group(0)

    content = SCRIPT_PAIR_RE.sub(clean_inside, content)

    # 2. --guarded: wrap existing bare calls — only the matched span is rewritten
    if guarded:
        def guard(m: re.Match) -> str:
            call = m.group(1).rstrip().rstrip(";")
            return f"<?php isset($hyvaCsp) && {call}; ?>"
        content = cc.HYVA_CSP_UNSAFE_CALL_RE.sub(guard, content)

    # 2b. --normalize: $viewModels->require(HyvaCsp::class)->x() → $hyvaCsp->x()
    if normalize:
        def norm(m: re.Match) -> str:
            call = f"$hyvaCsp->{m.group('method')}()"
            return f"isset($hyvaCsp) && {call}" if (guarded or force_guard_normalized) else call
        content = cc.NONSTANDARD_CSP_CALL_RE.sub(norm, content)

    # 3. Register every executable inline script that has no registration yet
    spans = cc.non_html_spans(content)
    nondet_vars = cc.nondeterministic_vars(content)
    skipped = []
    out, last = [], 0
    for m in SCRIPT_PAIR_RE.finditer(content):
        if cc.in_spans(m.start(), spans):
            continue  # inside a PHP string/heredoc/comment or an HTML comment
        attrs = m.group("attrs")
        if not cc.is_executable_inline_script(attrs):
            continue
        if re.search(r"(?<![\w-])nonce\s*=", attrs, re.IGNORECASE):
            continue
        if cc.registration_follows(content, m.end()):
            continue
        if cc.nondeterministic_snippet(m.group(0), nondet_vars):
            skipped.append(content[:m.start()].count("\n") + 1)
            continue
        indent = m.group("indent") or ""
        out.append(content[last:m.end()])
        out.append(f"\n{indent}{REGISTRATION_GUARDED if guarded else REGISTRATION_BARE}")
        last = m.end()
    out.append(content[last:])
    return "".join(out), skipped


def php_lint(path: Path) -> tuple[bool, str]:
    php = shutil.which("php")
    if not php:
        return True, ""
    res = subprocess.run([php, "-l", str(path)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return res.returncode == 0, res.stdout.strip()


def fix_template_scripts(file_path: Path, dry_run: bool, guarded: bool, normalize: bool = False,
                         force_guard_normalized: bool = False) -> tuple[bool, str, list]:
    """Returns (modified, unified_diff, skipped_nondeterministic_lines). Line endings are preserved."""
    try:
        with open(file_path, encoding="utf-8", newline="") as fh:
            original = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        sys.stderr.write(f"{RED}❌ Cannot read {file_path}: {exc}{RESET}\n")
        return False, "", []

    content, skipped = fix_content(original, guarded=guarded, normalize=normalize,
                                   force_guard_normalized=force_guard_normalized)
    if content == original:
        return False, "", skipped

    diff = "".join(difflib.unified_diff(
        original.splitlines(keepends=True), content.splitlines(keepends=True),
        fromfile=str(file_path), tofile=str(file_path), n=2,
    ))
    if not dry_run:
        with open(file_path, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
        ok, msg = php_lint(file_path)
        if not ok:
            with open(file_path, "w", encoding="utf-8", newline="") as fh:
                fh.write(original)
            sys.stderr.write(f"{RED}❌ php -l failed after fixing {file_path} — reverted.\n   {msg}{RESET}\n")
            return False, "", skipped
    return True, diff, skipped


def is_generated(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root).parts
    except ValueError:
        rel = path.parts
    return bool(cc.GENERATED_PARTS.intersection(rel)) or rel[:1] == ("var",) or rel[:2] == ("pub", "static")


def main():
    cc.ensure_python()
    parser = argparse.ArgumentParser(description="CSP registration fixer for Hyvä templates")
    parser.add_argument("target", help="Template file or directory (module, theme, compat module)")
    parser.add_argument("--dry-run", action="store_true", help="Print diffs without writing to disk")
    parser.add_argument("--guarded", action="store_true",
                        help="Use the isset($hyvaCsp) form (inserted and existing calls) — for modules that also render on Luma")
    parser.add_argument("--normalize", action="store_true",
                        help="Rewrite $viewModels->require(HyvaCsp::class)->registerInline…() to the injected $hyvaCsp")
    parser.add_argument("--include-generated", action="store_true",
                        help="Allow files under vendor/, generated/, var/ or pub/static/ (refused by default)")
    args = parser.parse_args()

    target_path = Path(args.target).resolve()
    if not target_path.exists():
        sys.stderr.write(f"{RED}❌ Target path not found: {target_path}{RESET}\n")
        sys.exit(2)

    root = cc.find_project_root()
    templates = cc.find_templates(target_path)
    if not args.include_generated:
        skipped = [p for p in templates if is_generated(p, root)]
        templates = [p for p in templates if not is_generated(p, root)]
        if skipped:
            sys.stderr.write(f"{YELLOW}⚠️  Skipped {len(skipped)} file(s) under vendor/, generated/, var/ or "
                             f"pub/static/ (pass --include-generated to override){RESET}\n")
    if not templates:
        sys.stderr.write(f"{YELLOW}⚠️  No editable .phtml files found in: {target_path}{RESET}\n")
        sys.exit(0)

    print("=" * 80)
    print(f"{BOLD}⚡ Hyvä CSP Registration Fixer{' (DRY RUN)' if args.dry_run else ''}{RESET}")
    print(f"Target: {target_path} ({len(templates)} templates)")
    print("=" * 80 + "\n")

    modified_count = 0
    left_unregistered = []
    force_guard = cc.hyva_csp_class_available(root) is False
    for tpl in templates:
        changed, diff, skipped = fix_template_scripts(tpl, dry_run=args.dry_run, guarded=args.guarded,
                                                      normalize=args.normalize, force_guard_normalized=force_guard)
        left_unregistered += [(tpl, line) for line in skipped]
        if changed:
            modified_count += 1
            status = f"{YELLOW}[DRY RUN - WOULD FIX]{RESET}" if args.dry_run else f"{GREEN}✅ [FIXED]{RESET}"
            print(f"{status} {cc.display_path(tpl)}")
            for line in diff.splitlines()[:20]:
                color = GREEN if line.startswith("+") else (RED if line.startswith("-") else DIM)
                print(f"   {color}{line}{RESET}")
            print()

    if left_unregistered:
        print(f"{RED}{BOLD}Not registered — script text changes on every render (uniqid/rand/time):{RESET}")
        for tpl, line in left_unregistered:
            print(f"   {cc.display_path(tpl)}:{line}")
        print(f"   Move the dynamic value to a data-* attribute (see {CYAN}{cc.run_cmd('suggest <file>')}{RESET}), then re-run.\n")
    print("=" * 80)
    action = "would be modified" if args.dry_run else "updated"
    print(f"Completed: {modified_count} / {len(templates)} file(s) {action}.")
    if args.dry_run and modified_count > 0:
        print(f"Re-run without {CYAN}--dry-run{RESET} to apply. Nothing is committed — review with `git diff`.")
    print("=" * 80)


if __name__ == "__main__":
    main()
