#!/usr/bin/env python3
"""
fix-inline-scripts.py — Automated CSP Nonce Fixer for Hyvä Compatibility Modules
================================================================================
Correctly injects Hyvä CSP inline script registrations:
  - Hyvä inspects ob_get_contents() for the last closed </script> element.
    Therefore, `<?php isset($hyvaCsp) && $hyvaCsp->registerInlineScript(); ?>`
    MUST be placed IMMEDIATELY AFTER `</script>`, NEVER inside <script>.
  - Automatically cleans up any previously misplaced registrations inside <script>.
  - Guards existing bare `$hyvaCsp->...` calls with `isset($hyvaCsp) && ...`.

Usage:
  python3 scripts/fix-inline-scripts.py [path] [--dry-run]
"""

from __future__ import annotations

import argparse
import difflib
import re
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
    r"^[ \t]*<\?php\s+(?:if\s*\(\s*isset\(\s*\$hyvaCsp\s*\)\s*\)\s*|\s*isset\(\s*\$hyvaCsp\s*\)\s*&&\s*|\s*)\$hyvaCsp->registerInlineScript\(\s*\)\s*;?\s*\?>\s*\n?",
    re.IGNORECASE | re.MULTILINE
)


def is_executable_inline_script(attrs: str) -> bool:
    """Return True if script block is inline and executable JavaScript."""
    if re.search(r"\bsrc\s*=", attrs, re.IGNORECASE):
        return False
    type_match = re.search(r'\btype\s*=\s*["\']([^"\']+)["\']', attrs, re.IGNORECASE)
    if type_match:
        script_type = type_match.group(1).lower().strip()
        if script_type in ("application/ld+json", "text/x-magento-init", "text/html", "text/template"):
            return False
    return True


def fix_template_scripts(file_path: Path, dry_run: bool = False) -> tuple[bool, str]:
    """
    Fix inline scripts in file_path.
    Returns (modified: bool, unified_diff: str).
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as exc:
        sys.stderr.write(f"{RED}❌ Cannot read {file_path}: {exc}{RESET}\n")
        return False, ""

    original = content
    modified = False

    # 1. Clean up any misplaced registrations INSIDE <script> blocks
    def clean_inside_scripts(m: re.Match) -> str:
        nonlocal modified
        full_match = m.group(0)
        body = m.group("body")
        if cc.HYVA_CSP_REGISTER_CALL_RE.search(body):
            cleaned_body = MISPLACED_INSIDE_RE.sub("", body)
            if cleaned_body != body:
                modified = True
                return full_match.replace(body, cleaned_body)
        return full_match

    content = SCRIPT_PAIR_RE.sub(clean_inside_scripts, content)

    # 2. Fix bare $hyvaCsp-> calls that lack isset($hyvaCsp)
    new_lines = []
    for line in content.splitlines(keepends=True):
        if cc.HYVA_CSP_UNSAFE_CALL_RE.search(line):
            line = cc.HYVA_CSP_UNSAFE_CALL_RE.sub(
                r"<?php isset($hyvaCsp) && \1 ?>",
                line
            )
            # Ensure it ends with semicolon before ?>
            line = re.sub(r";?\s*\?>", r"; ?>", line)
            modified = True
        new_lines.append(line)
    content = "".join(new_lines)

    # 3. Locate each <script>...</script> and ensure registration immediately follows </script>
    offset = 0
    matches = list(SCRIPT_PAIR_RE.finditer(content))

    for m in matches:
        start_idx = m.start() + offset
        end_idx = m.end() + offset
        attrs = m.group("attrs")
        indent = m.group("indent") or ""

        # Only process executable inline scripts
        if not is_executable_inline_script(attrs):
            continue

        # If script already has nonce attribute on the tag, it is compliant
        if re.search(r"\bnonce\s*=", attrs, re.IGNORECASE):
            continue

        # Look ahead right after </script> up to next 250 characters
        following_chunk = content[end_idx:end_idx + 250]

        # Stop looking ahead if another tag or script starts
        boundary_match = re.search(r"<(?:script|/?[a-z]+)", following_chunk, re.IGNORECASE)
        search_region = following_chunk[:boundary_match.start()] if boundary_match else following_chunk

        # Check if registerInlineScript is already called right after </script>
        if cc.HYVA_CSP_REGISTER_CALL_RE.search(search_region):
            continue

        # Also check if it's called within the following block before endif/next tag
        following_lines = following_chunk.splitlines(keepends=True)[:3]
        if any("registerInlineScript" in line for line in following_lines):
            continue

        # Prepare injection immediately AFTER </script>
        # Match indentation of </script>
        injection = f"\n{indent}<?php isset($hyvaCsp) && $hyvaCsp->registerInlineScript(); ?>"

        # Insert after end_idx
        content = content[:end_idx] + injection + content[end_idx:]
        offset += len(injection)
        modified = True

    if content != original:
        diff = "".join(difflib.unified_diff(
            original.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=str(file_path),
            tofile=str(file_path),
            n=2
        ))
        if not dry_run:
            file_path.write_text(content, encoding="utf-8")
        return True, diff

    return False, ""


def main():
    cc.ensure_python()
    parser = argparse.ArgumentParser(description="Automated CSP Nonce Fixer for Hyvä Compatibility Modules")
    parser.add_argument("target", nargs="?", default=".", help="File or folder to fix")
    parser.add_argument("--dry-run", action="store_true", help="Print diffs without writing to disk")
    args = parser.parse_args()

    target_path = Path(args.target).resolve()
    if not target_path.exists():
        sys.stderr.write(f"{RED}❌ Target path not found: {target_path}{RESET}\n")
        sys.exit(2)

    templates = cc.find_templates(target_path)
    if not templates:
        sys.stderr.write(f"{YELLOW}⚠️  No .phtml files found in: {target_path}{RESET}\n")
        sys.exit(0)

    print("=" * 80)
    print(f"{BOLD}⚡ Hyvä CSP Nonce Fixer{' (DRY RUN)' if args.dry_run else ''}{RESET}")
    print(f"Target: {target_path} ({len(templates)} templates)")
    print("=" * 80 + "\n")

    modified_count = 0
    for tpl in templates:
        changed, diff = fix_template_scripts(tpl, dry_run=args.dry_run)
        if changed:
            modified_count += 1
            status = f"{YELLOW}[DRY RUN - WOULD FIX]{RESET}" if args.dry_run else f"{GREEN}✅ [FIXED]{RESET}"
            rel = tpl.relative_to(cc.find_project_root()) if tpl.is_relative_to(cc.find_project_root()) else tpl
            print(f"{status} {rel}")
            if diff:
                for line in diff.splitlines()[:20]:
                    color = GREEN if line.startswith("+") else (RED if line.startswith("-") else DIM)
                    print(f"   {color}{line}{RESET}")
            print()

    print("=" * 80)
    action = "would be modified" if args.dry_run else "successfully updated"
    print(f"Completed! {modified_count} / {len(templates)} file(s) {action}.")
    if args.dry_run and modified_count > 0:
        print(f"Re-run without {CYAN}--dry-run{RESET} to apply changes.")
    print("=" * 80)


if __name__ == "__main__":
    main()
