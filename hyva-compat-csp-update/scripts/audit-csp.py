#!/usr/bin/env python3
"""
audit-csp.py — High-Precision CSP Auditor for Hyvä Compatibility Modules
=========================================================================
Scans Magento 2 Hyvä compatibility modules, child theme overrides, or
custom modules for Content Security Policy (strict CSP) compliance:
  1. `$hyvaCsp` calls without `isset($hyvaCsp)` (warning: fatal only where the template
     can also render on Luma / pre-$hyvaCsp Hyvä; Hyvä injects $hyvaCsp everywhere else).
  2. Executable inline `<script>` without registerInlineScript() right after </script>,
     registration misplaced inside <script>, nondeterministic script text (uniqid/rand/time,
     directly or via a variable).
  3. Alpine directive values that are not plain dot-paths — the only thing alpine3-csp.js
     resolves: calls (with or without arguments), operators, ternaries, object literals,
     assignments, negation, string literals, x-for sources that are expressions.
  4. Inline event-handler attributes (`onclick="…"`) and `javascript:` URLs — blocked by
     script-src without 'unsafe-inline' / 'unsafe-hashes', whatever the Alpine build.
  5. Non-standard `$viewModels->require(HyvaCsp::class)->registerInlineScript()` (works where
     the class exists, fatal where it does not).
  6. Legacy Alpine v2 directives (`x-spread`, `$el.__x`).

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


NONDETERMINISTIC_CALL = cc.NONDETERMINISTIC_CALL
# `true` matches the identifier pattern but the evaluator looks up a property named "true"
LITERALS = {"true", "false", "null", "undefined", "NaN", "Infinity"}
EVENT_HANDLER_RE = re.compile(
    r"""(?<=\s)(?P<attr>on(?:click|dblclick|change|input|submit|load|error|focus|focusin|focusout|blur|"""
    r"""key(?:down|up|press)|mouse\w+|touch\w+|pointer\w+|drag\w*|drop|scroll|resize|reset|select|"""
    r"""contextmenu|play|pause|ended|toggle|animation\w+|transition\w+|wheel|beforeunload|unload|copy|cut|paste))"""
    r"""\s*=\s*(?P<q>["'])(?P<val>.*?)(?P=q)""",
    re.IGNORECASE | re.DOTALL,
)
JS_URL_RE = re.compile(
    r"""(?<=\s)(?P<attr>href|src|action|formaction)\s*=\s*(?P<q>["'])\s*javascript:(?P<val>.*?)(?P=q)""",
    re.IGNORECASE | re.DOTALL,
)
_STRING_LIT = re.compile(r"""'(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"|`(?:\\.|[^`\\])*`""")
_PLAIN_PATH = re.compile(r"^\$?[A-Za-z_][\w$]*(?:\.\$?[A-Za-z_][\w$]*)*$")
_XFOR = re.compile(r"^\(?\s*[A-Za-z_$][\w$]*(?:\s*,\s*[A-Za-z_$][\w$]*)?\s*\)?\s+(?:in|of)\s+(?P<src>.+)$")
# Attribute names: require whitespace before so data-max-height / xlink:href don't match
ATTR_SCAN_RE = re.compile(
    r"""(?<=\s)(?P<attr>@[\w.:-]+|:[\w.:-]+|x-[\w.:-]+)\s*=\s*(?P<quote>["'])(?P<val>.*?)(?P=quote)""",
    re.DOTALL,
)
SKIP_ATTRS = ("x-transition", "x-cloak", "x-ref", "x-teleport", "x-ignore")


def classify_expression(attr: str, val: str) -> tuple[str, str] | None:
    """Return (finding id, message) when `val` is not a plain dot-path that
    alpine3-csp.js can resolve, else None. `val` has PHP masked as __PHP__."""
    if attr == "x-for":
        m = _XFOR.match(val)
        if not m:
            return "csp_xfor_expr", "x-for must be `item in prop.path` / `(item, index) in prop.path`."
        val = m.group("src").strip()
        if val.isdigit():
            return "csp_xfor_expr", "x-for over a number (`i in 10`) is resolved as a property named '10' — expose an array getter."
        if _PLAIN_PATH.match(val) and val not in LITERALS:
            return None
        return "csp_xfor_expr", "x-for source must be a property path — move filtering/mapping into a getter."
    if val in LITERALS:
        return "csp_not_dot_path", f"Literal `{val}` is looked up as a property named '{val}' — use a getter, or a static attribute."
    if _PLAIN_PATH.match(val):
        return None
    if "__PHP__" in val and re.fullmatch(r"[\w$.]*__PHP__[\w$.]*", val):
        return None  # e.g. x-data="initFoo<?= $id ?>" → dynamic but still a plain name
    bare = _STRING_LIT.sub("''", val)
    if re.search(r"=>|\bfunction\s*\(", bare):
        return "csp_function_definition", "Inline function/arrow — declare a method in the Alpine.data factory."
    if re.fullmatch(r"\$?[\w$.]+\(\s*\)", bare):
        return "csp_call_parens", "Remove the parentheses: the CSP evaluator only resolves names (`toggle`, not `toggle()`)."
    if re.search(r"[\w$]\s*\(", bare):
        return "csp_call_with_args", "Call with arguments — pass values via data-* attributes and read event.currentTarget.dataset."
    if bare.lstrip().startswith("{"):
        if attr == "x-data":
            return "csp_xdata_object_literal", "Object literal in x-data — register an Alpine.data factory and read config from data-*."
        return "csp_object_literal", "Object literal — return the class/style string from a getter."
    if ";" in bare:
        return "csp_multi_statement", "Several statements — move them into a named method."
    if re.search(r"\?(?![.?])", bare) and ":" in bare:
        return "csp_ternary", "Ternary — replace with a getter."
    if re.search(r"===|!==|==|!=|<=|>=|<|>", bare):
        return "csp_comparison_expr", "Comparison — move it into a getter."
    if re.search(r"&&|\|\||\?\?", bare):
        return "csp_logical_expr", "Logical operator — move the condition into a getter."
    if re.search(r"(?<![=!<>])=(?!=)|\+\+|--", bare):
        return "csp_assignment", "Assignment — use a named method (`@click=\"show\"`)."
    if bare.lstrip().startswith("!"):
        return "csp_negation", "Negation `!` is not supported — add a getter (e.g. `isClosed`)."
    if re.search(r"[+\-*/%]", bare):
        return "csp_binary_expr", "Arithmetic/concatenation — move it into a getter."
    return "csp_not_dot_path", "Not a plain property path (literal, index access, …) — expose it via a getter."


def inspect_template_csp(phtml_path: Path) -> list[dict]:
    findings: list[dict] = []
    try:
        raw_content = phtml_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return [{"line": 1, "severity": "fatal", "id": "read_error", "msg": f"Cannot read file: {exc}"}]

    lines = raw_content.splitlines()
    spans = cc.non_html_spans(raw_content)

    # ── 1. $hyvaCsp call without isset() (warning: only fatal on Luma / pre-$hyvaCsp Hyvä) ──
    for idx, line in enumerate(lines, 1):
        if cc.HYVA_CSP_UNSAFE_CALL_RE.search(line):
            window = "\n".join(lines[max(0, idx - 4):idx])
            if "isset(" not in window:
                findings.append({
                    "line": idx, "severity": "warning", "id": "unsafe_hyva_csp",
                    "msg": "$hyvaCsp call without isset() — fine in Hyvä-only code; guard it if this template can also render on Luma or old Hyvä",
                    "snippet": line.strip(),
                })

    nondet_vars = cc.nondeterministic_vars(raw_content)
    class_available = cc.hyva_csp_class_available(cc.find_project_root())

    # ── 1b. Non-standard registration through $viewModels ──
    for m in cc.NONSTANDARD_CSP_CALL_RE.finditer(raw_content):
        line_no = raw_content[:m.start()].count("\n") + 1
        if class_available is False:
            findings.append({
                "line": line_no, "severity": "fatal", "id": "nonstandard_hyva_csp_call",
                "msg": "HyvaCsp does not exist in this project's theme module → fatal error. Use `isset($hyvaCsp) && $hyvaCsp->registerInlineScript()` (fix-scripts --normalize).",
                "snippet": m.group(0),
            })
        else:
            findings.append({
                "line": line_no, "severity": "warning", "id": "nonstandard_hyva_csp_call",
                "msg": "Registers the script, but is not Hyvä's form and is fatal on theme modules without HyvaCsp. Use the injected `$hyvaCsp->…` (fix-scripts --normalize).",
                "snippet": m.group(0),
            })

    # ── 2. Inline <script> blocks (HTML context only) ──
    for m in cc._SCRIPT_BLOCK.finditer(raw_content):
        if cc.in_spans(m.start(), spans):
            continue
        tag = re.match(r"<script\b[^>]*>", m.group(0), re.IGNORECASE).group(0)
        if not cc.is_executable_inline_script(tag[len("<script"):-1]):
            continue
        script_full = m.group(0)
        line_no = raw_content[:m.start()].count("\n") + 1

        if cc.HYVA_CSP_REGISTER_CALL_RE.search(script_full):
            findings.append({
                "line": line_no, "severity": "fatal", "id": "misplaced_hyva_csp",
                "msg": "registerInlineScript() inside <script> — it must come immediately after </script> (Hyvä reads the last closed <script> from the output buffer)",
                "snippet": tag.strip(),
            })
            continue

        has_nonce_attr = bool(re.search(r"(?<![\w-])nonce\s*=", tag, re.IGNORECASE))
        if not has_nonce_attr and not cc.registration_follows(raw_content, m.end()):
            findings.append({
                "line": line_no, "severity": "fatal", "id": "unnonced_inline_script",
                "msg": "Inline <script> without registerInlineScript() right after </script>",
                "snippet": tag.strip(),
            })

        php_call = cc.nondeterministic_snippet(script_full, nondet_vars)
        if php_call:
            findings.append({
                "line": line_no, "severity": "fatal", "id": "nondeterministic_script_hash",
                "msg": "Script text changes on every render (uniqid/rand/time…) → a new CSP hash per render, growing the cached header. Move the value to data-* or JSON.",
                "snippet": php_call,
            })

    # ── 3. Alpine directives the CSP evaluator cannot resolve ──
    masked = cc.strip_html_comments(cc.mask_php(raw_content))
    for m in ATTR_SCAN_RE.finditer(masked):
        attr_name = m.group("attr")
        if attr_name.startswith(SKIP_ATTRS):
            continue
        raw_val = m.group("val").strip()
        val = re.sub(r"\s+", " ", raw_val).strip()
        if not val:
            continue
        result = classify_expression(attr_name, val)
        if result:
            fid, msg = result
            findings.append({
                "line": masked[:m.start()].count("\n") + 1, "severity": "fatal", "id": fid,
                "msg": f"'{attr_name}': {msg}",
                "snippet": f'{attr_name}="{raw_val}"',
            })

    # ── 4. Inline event handlers and javascript: URLs (HTML outside <script>) ──
    markup = cc._SCRIPT_BLOCK.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), masked)
    for m in EVENT_HANDLER_RE.finditer(markup):
        findings.append({
            "line": markup[:m.start()].count("\n") + 1, "severity": "fatal", "id": "inline_event_handler",
            "msg": f"'{m.group('attr')}' inline handler is blocked by script-src without 'unsafe-inline' — use @{m.group('attr')[2:].lower()} with a method, or addEventListener in a registered script.",
            "snippet": f'{m.group("attr")}="{m.group("val")[:60]}"',
        })
    for m in JS_URL_RE.finditer(markup):
        findings.append({
            "line": markup[:m.start()].count("\n") + 1, "severity": "fatal", "id": "javascript_url",
            "msg": "javascript: URL is blocked under strict CSP — use a <button type=\"button\"> with @click (or href=\"#\" + @click.prevent).",
            "snippet": f'{m.group("attr")}="javascript:{m.group("val")[:50]}"',
        })

    # ── 5. Alpine v2 leftovers ──
    for idx, line in enumerate(lines, 1):
        if "x-spread" in line:
            findings.append({"line": idx, "severity": "fatal", "id": "legacy_x_spread",
                             "msg": "x-spread was removed in Alpine v3.", "snippet": line.strip()})
        if "$el.__x" in line:
            findings.append({"line": idx, "severity": "fatal", "id": "legacy_el_x",
                             "msg": "$el.__x is undefined in Alpine v3.", "snippet": line.strip()})

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
        if args.output == "json":
            print(json.dumps({"target": str(target_path), "templates_scanned": 0, "total_findings": 0,
                              "fatal_findings": 0, "files": {}}, indent=2))
        sys.exit(0)

    all_results: dict[str, list[dict]] = {}
    total_findings = 0
    total_fatal = 0
    target_disp = cc.display_path(target_path)

    for tpl in templates:
        findings = inspect_template_csp(tpl)
        if findings:
            all_results[cc.display_path(tpl)] = findings
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
            print("All inline scripts are registered and all Alpine expressions are plain dot-paths.\n")
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
        print(f"Total findings: {total_findings} ({total_fatal} break under CSP, {total_findings - total_fatal} warnings)")
        
        has_unnonced_scripts = any(
            any(iss["id"] in ("unnonced_inline_script", "misplaced_hyva_csp", "unsafe_hyva_csp") for iss in issues)
            for issues in all_results.values()
        )
        has_alpine_issues = any(
            any(iss["id"] not in ("unnonced_inline_script", "misplaced_hyva_csp", "unsafe_hyva_csp") for iss in issues)
            for issues in all_results.values()
        )

        if has_unnonced_scripts:
            print(f"👉 Preview fixes: {CYAN}{cc.run_cmd('fix-scripts ' + target_disp + ' --dry-run')}{RESET}")
        if has_alpine_issues:
            first_tpl = list(all_results.keys())[0]
            print(f"👉 Recipes: {CYAN}{cc.run_cmd('suggest ' + first_tpl)}{RESET}")
        print("=" * 80)

    if total_fatal > 0 or (args.fail_on_warning and total_findings > 0):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
