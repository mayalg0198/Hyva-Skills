#!/usr/bin/env python3
"""
==============================================================================
Hyvä Vendor Template Diff & CSP Scanner: scan-vendor-diffs.py
Purpose: batch-compare child-theme templates with their upstream counterpart
         (Hyvä default theme or 3rd-party Hyvä compatibility modules) and flag
         outdated overrides + CSP risks.

Usage (from anywhere inside the project):
    scan-vendor-diffs.py --module "Amasty_*"          # one vendor family
    scan-vendor-diffs.py --module Magento_Catalog --diff
    scan-vendor-diffs.py --csp-only                   # only templates with CSP findings
    scan-vendor-diffs.py --output json

CSP findings are informational unless strict CSP is on (--strict-csp, or
`strictCsp: true` in .hyva-upgrade.json); then they make the script exit 1.
Use --fail-on-issues to force exit 1 regardless of the CSP mode.
Exit codes: 0 = ok · 1 = gate failed · 2 = usage/setup error
==============================================================================
"""
from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hyva_common as hc  # noqa: E402
from hyva_common import BLUE, BOLD, CYAN, GREEN, RED, RESET, YELLOW  # noqa: E402


def analyze_template_csp(t_text: str, v_text: str) -> list:
    """CSP differences / violations between a theme override and upstream."""
    issues = []

    raw, registered = hc.inline_script_stats(t_text)
    if raw > registered:
        issues.append(f"UNREGISTERED_SCRIPT: {raw} inline <script> tag(s) vs {registered} registerInlineScript() call(s)")
    if hc.has_unguarded_hyva_csp(t_text):
        issues.append("UNSAFE_HYVA_CSP: registerInlineScript() call missing the isset($hyvaCsp) guard")
    if hc.has_dynamic_script_hash(t_text):
        issues.append("DYNAMIC_SCRIPT_HASH: uniqid()/$uniqueId inside <script> causes CSP hash bloat in FPC")
    if hc.has_dynamic_script_php(t_text):
        issues.append("DYNAMIC_SCRIPT_PHP: dynamic PHP data inside <script> bloats the CSP hash and the cache")
    if hc.has_inline_event_handlers(t_text):
        issues.append("INLINE_EVENT_HANDLER: onclick/onchange/... attribute blocked by strict CSP")
    if hc.has_php_in_alpine_directives(t_text):
        issues.append("PHP_IN_ALPINE_DIRECTIVE: PHP tag inside an Alpine directive (:class, @click, x-show, ...)")
    if raw and registered == 0 and ("registerInlineScript" in v_text or "hyvaCsp" in v_text):
        issues.append("VENDOR_CSP_MISSING: upstream registers its inline script but the override does not")
    violations = hc.alpine_csp_violations(t_text)
    if violations:
        issues.append(f"ALPINE_CSP_EXPRESSION: {len(violations)} violation(s): " + "; ".join(violations[:3]))
    return issues


def main() -> None:
    hc.ensure_python()
    parser = argparse.ArgumentParser(description="Hyvä vendor template diff & CSP scanner")
    parser.add_argument("--config", help="Path to .hyva-upgrade.json (default: project root)")
    parser.add_argument("--theme", help="Child theme directory (default: config / auto-discovery)")
    parser.add_argument("--vendor", help="Hyvä default theme directory")
    parser.add_argument("--module", help="Module filter, e.g. 'Amasty_*' or Magento_Catalog")
    parser.add_argument("--csp-only", action="store_true", help="Only list templates with CSP findings")
    parser.add_argument("--modified-only", action="store_true", help="Only list templates that differ from upstream")
    parser.add_argument("--identical-only", action="store_true", help="Only list templates identical to upstream (redundant overrides)")
    parser.add_argument("--custom-only", action="store_true", help="Only list custom templates without upstream counterparts")
    parser.add_argument("--diff", action="store_true", help="Print a unified diff for modified templates")
    parser.add_argument("--strict-csp", dest="strict_csp", action="store_true", default=None,
                        help="CSP findings fail the run (default: config strictCsp)")
    parser.add_argument("--no-strict-csp", dest="strict_csp", action="store_false")
    parser.add_argument("--audit-csp", action="store_true", help="Display CSP issues even if strictCsp is false")
    parser.add_argument("--fail-on-issues", action="store_true", help="Exit 1 on any CSP finding")
    parser.add_argument("--output", choices=["text", "json"], default="text")
    args = parser.parse_args()

    hc.enter_project_root()
    config = hc.load_config(args.config, quiet=args.output == "json")
    strict_csp = hc.resolve_strict_csp(args.strict_csp, config)
    theme_dir = hc.resolve_theme_path(args.theme, config)
    vendor_theme = hc.resolve_vendor_theme(args.vendor, config)
    module_index = hc.build_vendor_module_index()
    csp_active = strict_csp or args.audit_csp or args.csp_only

    pattern = f"{args.module}/**/*.phtml" if args.module else "**/*.phtml"
    templates = sorted(theme_dir.glob(pattern))
    if args.module and not templates:
        sys.stderr.write(f"{RED}❌ No templates match --module {args.module!r} in {theme_dir}{RESET}\n")
        sys.exit(2)
    if not module_index and args.output == "text":
        print(f"{YELLOW}⚠️  vendor/composer/installed.json not found — 3rd-party counterparts cannot be resolved "
              f"(run `composer install` first).{RESET}")

    if args.output == "text":
        print("=" * 80)
        print(f"{BOLD}🔍 Hyvä Vendor Template Diff & CSP Auditor{RESET}")
        print(f"Target theme   : {BOLD}{theme_dir}{RESET}")
        print(f"Module filter  : {BOLD}{args.module or 'All modules'}{RESET}")
        print(f"Templates found: {BOLD}{len(templates)}{RESET}")
        if strict_csp:
            mode = "STRICT (findings fail the run)"
        elif args.audit_csp:
            mode = "AUDIT (findings are informational)"
        else:
            mode = "standard (CSP details omitted; pass --audit-csp to inspect)"
        print(f"CSP mode       : {mode}")
        print("=" * 80 + "\n")

    results, counts = [], {"identical": 0, "modified": 0, "custom_only": 0, "csp_issues": 0}
    for tpl in templates:
        rel = tpl.relative_to(theme_dir)
        t_text = tpl.read_text(encoding="utf-8", errors="ignore")
        v_path, v_source = hc.resolve_vendor_template(rel, vendor_theme, module_index)
        has_vendor = bool(v_path and v_path.exists())
        v_text = v_path.read_text(encoding="utf-8", errors="ignore") if has_vendor else ""

        issues = analyze_template_csp(t_text, v_text) if csp_active else []
        if issues:
            counts["csp_issues"] += 1
        if not has_vendor:
            status, diff_text = "custom_only", ""
        elif t_text == v_text:
            status, diff_text = "identical", ""
        else:
            status = "modified"
            diff_text = "".join(difflib.unified_diff(
                v_text.splitlines(keepends=True), t_text.splitlines(keepends=True),
                fromfile=f"vendor/{v_path.name}", tofile=f"theme/{rel.name}"))
        counts[status] += 1
        if args.csp_only and not issues:
            continue
        if args.modified_only and status != "modified":
            continue
        if args.identical_only and status != "identical":
            continue
        if args.custom_only and status != "custom_only":
            continue
        results.append({"file": str(rel), "status": status, "vendor_file": str(v_path) if has_vendor else None,
                        "vendor_source": v_source, "issues": issues, "diff": diff_text})

    failed = bool(counts["csp_issues"]) and (strict_csp or args.fail_on_issues)

    if args.output == "json":
        print(json.dumps({"total": len(templates), "strict_csp": strict_csp, "identical": counts["identical"],
                          "modified": counts["modified"], "unresolved": counts["custom_only"],
                          "csp_issues": counts["csp_issues"], "items": results}, indent=2, ensure_ascii=False))
        sys.exit(1 if failed else 0)

    icons = {"identical": f"{GREEN}✅ [IDENTICAL]{RESET}", "modified": f"{YELLOW}✏️  [MODIFIED]{RESET}",
             "custom_only": f"{BLUE}ℹ️  [CUSTOM]{RESET}"}
    for item in results:
        icon = f"{RED}🚨 [CSP ISSUE]{RESET}" if (item["issues"] and csp_active) else icons[item["status"]]
        print(f"{icon} {BOLD}{item['file']}{RESET} ({item['vendor_source']})")
        if item["vendor_file"]:
            print(f"   Vendor: {item['vendor_file']}")
        if csp_active:
            for issue in item["issues"]:
                print(f"   {RED}• {issue}{RESET}")
        if args.diff and item["diff"]:
            print(f"\n{CYAN}--- DIFF ({item['file']}) ---{RESET}")
            lines = item["diff"].splitlines()
            for line in lines[:50]:
                color = GREEN if line.startswith("+") else RED if line.startswith("-") else ""
                print(f"{color}{line}{RESET if color else ''}")
            if len(lines) > 50:
                print(f"{YELLOW}... [diff truncated: {len(lines) - 50} more lines]{RESET}")
            print()

    print("\n" + "=" * 80)
    print(f"{BOLD}📊 SCAN SUMMARY:{RESET}")
    print(f"Total templates scanned : {len(templates)}")
    print(f"Identical vs vendor     : {GREEN}{counts['identical']}{RESET}")
    print(f"Modified vs vendor      : {YELLOW}{counts['modified']}{RESET}")
    print(f"Custom-only (no vendor) : {BLUE}{counts['custom_only']}{RESET}")
    if csp_active:
        print(f"Templates with CSP alert: {RED}{counts['csp_issues']}{RESET}")
    else:
        print(f"CSP checks              : {CYAN}Omitted (strictCsp: false). Pass --audit-csp to inspect.{RESET}")
    if counts["csp_issues"] and not failed:
        print(f"{YELLOW}(informational — strictCsp is off; use --strict-csp or --fail-on-issues to gate){RESET}")
    print("=" * 80)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
