#!/usr/bin/env python3
"""
audit-csp.py — High-Precision CSP Auditor for Hyvä Compatibility Modules
=========================================================================
Scans Magento 2 Hyvä compatibility modules, child theme overrides, or
custom modules for Content Security Policy (strict CSP) compliance:
  1. Unsafe `$hyvaCsp` calls without `isset($hyvaCsp)` (PHP fatal crash).
  2. Un-nonced executable `<script>` blocks (blocked by CSP).
  3. Alpine directives with arguments `@event="fn(arg)"` (eval error).
  4. Alpine directives with ternaries `:prop="a ? b : c"` (eval error).
  5. Alpine directives with object literals `:class="{ 'active': flag }"` (eval error).
  6. Alpine directives with binary expressions / concatenation `:id="'prefix-' + id"`.
  7. Alpine inline function / arrow definitions.
  8. Legacy Alpine v2 directives (`x-spread`, `$el.__x`).

Usage:
  python3 scripts/audit-csp.py [path/to/module-or-template] [--fail-on-warning] [--output text|json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import csp_common as cc
from csp_common import BOLD, CYAN, DIM, GREEN, RED, RESET, YELLOW


def inspect_template_csp(phtml_path: Path) -> list[dict]:
    findings: list[dict] = []
    try:
        raw_content = phtml_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return [{"line": 1, "severity": "fatal", "id": "read_error", "msg": f"Cannot read file: {exc}"}]

    lines = raw_content.splitlines()

    # ── 1. Unsafe $hyvaCsp call ──
    for idx, line in enumerate(lines, 1):
        if cc.HYVA_CSP_UNSAFE_CALL_RE.search(line):
            if "isset(" not in line:
                findings.append({
                    "line": idx,
                    "severity": "fatal",
                    "id": "unsafe_hyva_csp",
                    "msg": "Unsafe $hyvaCsp call without isset($hyvaCsp) — causes PHP fatal crash when CSP module is disabled",
                    "snippet": line.strip()
                })

    # ── 2. Inline <script> blocks ──
    for m in cc._SCRIPT_BLOCK.finditer(raw_content):
        tag_match = cc.RAW_INLINE_SCRIPT_RE.search(m.group(0))
        if tag_match:
            script_full = m.group(0)
            end_pos = m.end()
            line_no = raw_content[:m.start()].count("\n") + 1

            # Check if registerInlineScript was mistakenly placed INSIDE <script>
            if cc.HYVA_CSP_REGISTER_CALL_RE.search(script_full):
                findings.append({
                    "line": line_no,
                    "severity": "fatal",
                    "id": "misplaced_hyva_csp",
                    "msg": "registerInlineScript() placed inside <script> block — MUST be placed immediately after </script> because Hyvä inspects ob_get_contents() for the last closed </script> element",
                    "snippet": tag_match.group(0).strip()
                })
                continue

            # Check if <script> has nonce attribute
            has_nonce_attr = "nonce=" in tag_match.group(0).lower()

            # Check if registerInlineScript is placed immediately AFTER </script>
            following_chunk = raw_content[end_pos:end_pos + 250]
            boundary_match = re.search(r"<(?:script|/?[a-z]+)", following_chunk, re.IGNORECASE)
            search_region = following_chunk[:boundary_match.start()] if boundary_match else following_chunk
            has_register_after = bool(cc.HYVA_CSP_REGISTER_CALL_RE.search(search_region))

            if not has_register_after and not has_nonce_attr:
                findings.append({
                    "line": line_no,
                    "severity": "fatal",
                    "id": "unnonced_inline_script",
                    "msg": "Executable inline <script> missing CSP nonce registration (must place <?php isset($hyvaCsp) && $hyvaCsp->registerInlineScript(); ?> immediately after </script>)",
                    "snippet": tag_match.group(0).strip()
                })

            # Check for non-deterministic PHP values inside executable <script> (Sutunam Gotcha 8: Hash growth)
            NONDETERMINISTIC_RE = re.compile(
                r"\b(?:uniqid|random_int|rand|microtime|mt_rand|random_bytes)\s*\(",
                re.IGNORECASE
            )
            php_calls_in_script = re.findall(r"<\?(?:php|=).*?\?>", script_full, re.DOTALL)
            for php_call in php_calls_in_script:
                if NONDETERMINISTIC_RE.search(php_call):
                    findings.append({
                        "line": line_no,
                        "severity": "fatal",
                        "id": "nondeterministic_script_hash",
                        "msg": "Nondeterministic PHP expression in inline <script> changes script text on every render, causing dynamic script hash accumulation and persistent FPC bloat. Move dynamic value to an HTML data-* attribute or inert JSON.",
                        "snippet": php_call.strip()
                    })

    # ── 3. Alpine.js CSP Violations in Directives ──
    # Strip PHP tags first so PHP expressions don't trigger false positives
    no_php = cc.strip_php(raw_content)
    no_comments = cc.strip_html_comments(no_php)

    # Directives to inspect: @..., :..., x-...
    ATTR_SCAN_RE = re.compile(
        r"""(?P<attr>@[\w\.-]+|:[\w\.-]+|x-[\w\.-]+)\s*=\s*(?P<quote>["'])(?P<val>.*?)(?P=quote)""",
        re.DOTALL
    )

    for m in ATTR_SCAN_RE.finditer(no_comments):
        attr_name = m.group("attr")
        raw_val = m.group("val").strip()
        val = re.sub(r"\s+", " ", raw_val).strip().lstrip("\\")
        line_no = no_comments[:m.start()].count("\n") + 1

        if not val:
            continue

        # Skip x-for="item in items" (natively supported by alpine3-csp.js)
        if attr_name == "x-for":
            continue

        # Skip transition directives that take modifiers, duration, or class strings
        if attr_name.startswith("x-transition"):
            continue

        # 3.1 Function calls with arguments: foo(bar) or select(item.id)
        # Note: 0-arg calls like `init()` or `toggle()` or simple identifiers are checked
        CALL_WITH_ARGS_RE = re.compile(r"""\b[a-zA-Z0-9_$]+\s*\(\s*(?!\s*\))\S+.*?\s*\)""")
        if CALL_WITH_ARGS_RE.search(val):
            findings.append({
                "line": line_no,
                "severity": "fatal",
                "id": "csp_call_with_args",
                "msg": f"Alpine directive '{attr_name}' calls function with arguments — blocked by alpine3-csp.js dot-path evaluator. Pass parameters via HTML5 data-* attributes.",
                "snippet": f'{attr_name}="{raw_val}"'
            })
            continue

        # 3.2 Ternary operator: a ? b : c
        if "?" in val and ":" in val:
            findings.append({
                "line": line_no,
                "severity": "fatal",
                "id": "csp_ternary",
                "msg": f"Ternary operator in '{attr_name}' violates CSP dot-path evaluator. Replace with an Alpine getter method.",
                "snippet": f'{attr_name}="{raw_val}"'
            })
            continue

        # 3.3 Object literals in class/bind or x-data: { 'active': isActive }
        if val.startswith("{") and val.endswith("}") and ":" in val:
            if attr_name == "x-data":
                findings.append({
                    "line": line_no,
                    "severity": "fatal",
                    "id": "csp_xdata_object_literal",
                    "msg": "Inline object literal in 'x-data' violates CSP evaluator. Define component in an Alpine.data factory and pass parameters via data-* attributes.",
                    "snippet": f'{attr_name}="{raw_val}"'
                })
            else:
                findings.append({
                    "line": line_no,
                    "severity": "fatal",
                    "id": "csp_object_literal",
                    "msg": f"Object literal in '{attr_name}' violates CSP evaluator. Return classes from an Alpine getter or array.",
                    "snippet": f'{attr_name}="{raw_val}"'
                })
            continue

        # 3.4 Comparison operators: ===, !==, ==, !=, <=, >=, <, >
        if re.search(r"""(?:===|!==|==|!=|<=|>=|<|>)""", val):
            findings.append({
                "line": line_no,
                "severity": "fatal",
                "id": "csp_comparison_expr",
                "msg": f"Comparison operator in '{attr_name}' violates CSP evaluator (alpine3-csp only evaluates dot-paths). Refactor to a component getter.",
                "snippet": f'{attr_name}="{raw_val}"'
            })
            continue

        # 3.5 Logical operators: &&, ||
        if re.search(r"""(?:&&|\|\|)""", val):
            findings.append({
                "line": line_no,
                "severity": "fatal",
                "id": "csp_logical_expr",
                "msg": f"Logical operator (&&, ||) in '{attr_name}' violates CSP evaluator. Move condition to a computed getter.",
                "snippet": f'{attr_name}="{raw_val}"'
            })
            continue

        # 3.6 Arrow functions / function expressions: () => ...
        if "=>" in val or "function(" in val:
            findings.append({
                "line": line_no,
                "severity": "fatal",
                "id": "csp_function_definition",
                "msg": f"Inline function / arrow function in '{attr_name}' violates CSP. Declare methods in Alpine data factory.",
                "snippet": f'{attr_name}="{raw_val}"'
            })
            continue

        # 3.7 Binary expressions / String concatenation: 'prefix-' + id or +item
        if re.search(r"""(['"].*?['"]\s*\+\s*|\+\s*['"].*?['"])""", val):
            findings.append({
                "line": line_no,
                "severity": "fatal",
                "id": "csp_binary_expr",
                "msg": f"String concatenation in '{attr_name}' violates CSP evaluator. Move expression into an Alpine getter.",
                "snippet": f'{attr_name}="{raw_val}"'
            })
            continue

    # ── 4. Alpine v2 Leftovers ──
    for idx, line in enumerate(lines, 1):
        if "x-spread" in line:
            findings.append({
                "line": idx,
                "severity": "fatal",
                "id": "legacy_x_spread",
                "msg": "x-spread is removed in Alpine v3 / Hyvä 1.4+ (causes fatal crash).",
                "snippet": line.strip()
            })
        if "$el.__x" in line:
            findings.append({
                "line": idx,
                "severity": "fatal",
                "id": "legacy_el_x",
                "msg": "$el.__x internal property is undefined in Alpine v3.",
                "snippet": line.strip()
            })

    return findings


def main():
    cc.ensure_python()
    parser = argparse.ArgumentParser(description="High-Precision CSP Auditor for Hyvä Compatibility Modules")
    parser.add_argument("target", nargs="?", default=".", help="Module directory, child theme folder, or single template to audit")
    parser.add_argument("--fail-on-warning", action="store_true", help="Exit code 1 on any warning")
    parser.add_argument("--output", choices=["text", "json"], default="text", help="Output format")
    args = parser.parse_args()

    target_path = Path(args.target).resolve()
    if not target_path.exists():
        sys.stderr.write(f"{RED}❌ Target path not found: {target_path}{RESET}\n")
        sys.exit(2)

    templates = cc.find_templates(target_path)
    if not templates:
        sys.stderr.write(f"{YELLOW}⚠️  No .phtml templates found in: {target_path}{RESET}\n")
        sys.exit(0)

    all_results: dict[str, list[dict]] = {}
    total_findings = 0
    total_fatal = 0

    for tpl in templates:
        findings = inspect_template_csp(tpl)
        if findings:
            rel = tpl.relative_to(cc.find_project_root()) if tpl.is_relative_to(cc.find_project_root()) else tpl
            all_results[str(rel)] = findings
            total_findings += len(findings)
            total_fatal += sum(1 for f in findings if f["severity"] == "fatal")

    if args.output == "json":
        print(json.dumps({
            "target": str(target_path),
            "templates_scanned": len(templates),
            "total_findings": total_findings,
            "fatal_findings": total_fatal,
            "files": all_results
        }, indent=2))
    else:
        print("=" * 80)
        print(f"{BOLD}🛡️  Hyvä Compatibility Module — Strict CSP Auditor{RESET}")
        print(f"Target path       : {BOLD}{target_path}{RESET}")
        print(f"Templates scanned : {BOLD}{len(templates)}{RESET}")
        print("=" * 80)

        if not all_results:
            print(f"\n{GREEN}{BOLD}🎉 100% CLEAN! Zero CSP violations detected.{RESET}")
            print("All inline scripts are safely registered with isset($hyvaCsp), and all Alpine expressions comply with alpine3-csp.js dot-path evaluator.\n")
            sys.exit(0)

        print(f"\n{RED if total_fatal else YELLOW}{BOLD}⚠️  Found {total_findings} CSP issue(s) across {len(all_results)} file(s):{RESET}\n")

        for fpath, issues in all_results.items():
            print(f"{BOLD}{fpath}{RESET} ({len(issues)} finding{'s' if len(issues) > 1 else ''}):")
            for iss in issues:
                color = RED if iss["severity"] == "fatal" else YELLOW
                print(f"   line {iss['line']:<4} {color}[{iss['id']}]{RESET} {iss['msg']}")
                if "snippet" in iss:
                    print(f"        {DIM}Snippet: {iss['snippet'][:90]}{RESET}")
            print()

        print("=" * 80)
        print(f"Total findings: {total_findings} ({total_fatal} fatal / blocking CSP)")
        
        has_unnonced_scripts = any(
            any(iss["id"] in ("unnonced_inline_script", "misplaced_hyva_csp", "unsafe_hyva_csp") for iss in issues)
            for issues in all_results.values()
        )
        has_alpine_issues = any(
            any(iss["id"] not in ("unnonced_inline_script", "misplaced_hyva_csp", "unsafe_hyva_csp") for iss in issues)
            for issues in all_results.values()
        )

        if has_unnonced_scripts:
            print(f"👉 Run {CYAN}./run.sh fix-scripts{RESET} to automatically register missing script nonces.")
        if has_alpine_issues:
            first_tpl = list(all_results.keys())[0]
            print(f"👉 Run {CYAN}./run.sh suggest {first_tpl}{RESET} to view Before/After refactoring recipes.")
        print("=" * 80)

    if total_fatal > 0 or (args.fail_on_warning and total_findings > 0):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
