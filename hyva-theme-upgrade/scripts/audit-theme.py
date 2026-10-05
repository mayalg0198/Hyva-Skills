#!/usr/bin/env python3
"""
==============================================================================
Hyvä Theme Upgrade Auditor: audit-theme.py
Purpose: scan a Hyvä child theme for upgrade-compatibility issues. Version-aware
         (from_version / to_version come from .hyva-upgrade.json) and
         CSP-mode-aware (strictCsp decides whether CSP findings are fatal).

Usage (from anywhere inside the project):
    python3 .agents/skills/hyva-theme-upgrade/scripts/audit-theme.py [options]

Options:
    --theme PATH             Hyvä child theme (default: config / auto-discovery)
    --vendor PATH            Hyvä default theme in vendor/
    --module PATTERN         Only audit templates of matching modules, e.g.
                             'Magento_Checkout' or 'Amasty_*' (one page flow)
    --strict-csp             CSP findings are FATAL   (default: config strictCsp)
    --no-strict-csp          CSP findings are warnings only
    --lint-php               Run `php -l` on every template
    --php-cmd "CMD"          PHP launcher, e.g. "govard env exec php"
    --skip-vendor-align      Skip vendor feature-parity checks
    --fail-on-warning        Exit 1 on warnings too (strict CI gate)
    --output text|json       Output format (default: text)

Exit codes: 0 = no fatal findings · 1 = fatal findings · 2 = usage/setup error
==============================================================================
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hyva_common as hc  # noqa: E402
from hyva_common import BLUE, BOLD, CYAN, GREEN, RED, RESET, YELLOW  # noqa: E402

SEVERITY_ORDER = ("fatal", "warning", "info")


# ─── Check catalogue (version- and CSP-mode-gated) ───────────────────────────

def build_checks(from_ver: str, to_ver: str, strict_csp: bool = False, audit_csp: bool = False, tw_version: int = 4) -> list:
    """
    Return the checks that apply to the upgrade range and detected Tailwind version.

    Each check is a dict: id, name, severity and ONE of
      patterns       [(compiled regex, description)]        content only
      custom_check   fn(content, vendor) -> (bool, message)  content (+vendor)
      vendor_check   fn(vendor, content) -> (bool, message)  needs upstream file
    `strict_csp` promotes the CSP-level rules from warning to fatal.
    When both strict_csp and audit_csp are False, strict CSP checks are omitted.
    """
    to_v = hc.parse_ver(to_ver)
    csp = "fatal" if strict_csp else "warning"
    checks: list = []

    # ── Always applicable (Alpine v3 / Hyvä 1.4+) ──
    checks.append({
        "id": "fatal_alpine_v2",
        "name": "Fatal Alpine v2 Directives",
        "severity": "fatal",
        "patterns": [
            (re.compile(r"\bx-spread\b"), "x-spread is removed in Alpine v3 (fatal crash)"),
            (re.compile(r"\$el\.__x\b"), "$el.__x is an internal Alpine v2 API (undefined in v3)"),
            (re.compile(r"alpine:initiali[zs]ed"), "alpine:initialized event renamed to alpine:init in v3"),
        ],
    })
    checks.append({
        "id": "storage_boolean",
        "name": "Unsafe localStorage JSON.parse",
        "severity": "warning",
        "patterns": [
            (re.compile(r"JSON\.parse\(.*?getItem\("),
             "JSON.parse on storage returns null when the key is missing → runtime TypeError"),
        ],
    })

    # ── Tailwind v4 migration (Tailwind v4 / Hyvä 1.4.0+) ──
    if tw_version >= 4 or to_v >= (1, 4, 0):
        checks.append({
            "id": "tw_v3_opacity",
            "name": "Deprecated Tailwind v3 *-opacity-* classes",
            "severity": "warning",
            "patterns": [
                (re.compile(r"\b(bg|text|border|placeholder|divide|ring)-opacity-(\d+)\b"),
                 "Use Tailwind v4 slash syntax instead (e.g. bg-black/50)"),
            ],
            "critical_combo": (
                re.compile(r"bg-black"),
                "CRITICAL: bg-black + bg-opacity-* → solid black modal backdrop (page invisible)",
            ),
        })
    if to_v >= (1, 5, 2):
        checks.append({
            "id": "legacy_fg_tokens",
            "name": "Legacy Design Tokens (*-fg → ink)",
            "severity": "warning",
            "patterns": [
                (re.compile(r"\b(text|bg|border|fill|stroke)-fg\b"),
                 "Replace with -ink / -ink-muted (--color-fg is kept only as a deprecated alias)"),
            ],
        })

    # ── Hyvä 1.4.7+ ──
    if hc.version_in_range("1.4.7", from_ver, to_ver):
        checks.append({
            "id": "missing_pageshow",
            "name": "Missing bfcache @pageshow.window handler",
            "severity": "warning",
            "vendor_check": lambda vc, c: (
                "@pageshow.window" in vc and "@pageshow.window" not in c and "pageshow" not in c,
                "Add @pageshow.window handler to refresh the form key on bfcache restore",
            ),
        })
        checks.append({
            "id": "missing_submitting",
            "name": "Missing anti-spam isSubmitting guard",
            "severity": "warning",
            "vendor_check": lambda vc, c: (
                "isSubmitting" in vc and "isSubmitting" not in c,
                "Add an isSubmitting guard to prevent double-submit",
            ),
        })

    # ── Hyvä 1.5.1+ ──
    if hc.version_in_range("1.5.1", from_ver, to_ver):
        checks.append({
            "id": "vendor_alignment_gallery",
            "name": "Vendor Feature Parity: gallery.additional container",
            "severity": "info",
            "vendor_check": lambda vc, c: (
                "gallery.additional" in vc and "gallery.additional" not in c,
                "New gallery.additional layout container (1.5.1) — add it to enable badge/promo injection",
            ),
        })

    # ── CSP Guard (always checked: prevent PHP fatal error when CSP is disabled) ──
    checks.append({
        "id": "unsafe_hyva_csp",
        "name": "CSP: $hyvaCsp call without isset()",
        "severity": "fatal",
        "custom_check": lambda c, vc: (
            hc.has_unguarded_hyva_csp(c),
            "registerInlineScript() without an isset($hyvaCsp) guard crashes when $hyvaCsp is undefined. "
            "Use: <?php isset($hyvaCsp) && $hyvaCsp->registerInlineScript(); ?>",
        ),
    })
    checks.append({
        "id": "misplaced_hyva_csp",
        "name": "CSP: registerInlineScript() inside <script>",
        "severity": "fatal",
        "custom_check": lambda c, vc: (
            hc.has_misplaced_hyva_csp(c),
            "registerInlineScript() placed inside <script> tag breaks Hyvä output buffer extraction. "
            "Must be placed immediately AFTER </script>.",
        ),
    })

    # ── Strict CSP hygiene (only scoped when project enforces strict CSP) ──
    if strict_csp or audit_csp:
        checks.append({
            "id": "inline_xdata_methods",
            "name": "Non-CSP Inline x-data Objects",
            "severity": "warning",
            "custom_check": lambda c, vc: (
                hc.has_complex_inline_xdata(c),
                "Inline x-data object defines methods / dynamic calls — extract to an Alpine.data() factory.",
            ),
        })
        checks.append({
            "id": "inline_event_handlers",
            "name": "CSP: Inline HTML Event Handlers (onclick/onchange)",
            "severity": csp,
            "custom_check": lambda c, vc: (
                hc.has_inline_event_handlers(c),
                "Inline HTML event handler detected — blocked by strict CSP. Use @click / @change.",
            ),
        })
        checks.append({
            "id": "php_in_alpine_directives",
            "name": "CSP: PHP injected inside Alpine directives",
            "severity": csp,
            "custom_check": lambda c, vc: (
                hc.has_php_in_alpine_directives(c),
                "PHP tag inside an Alpine directive (:class, @click, x-show …) — pass data via data-* "
                "attributes and read it from an Alpine.data() method.",
            ),
        })

        def _csp_expr(c, vc):
            found = hc.alpine_csp_violations(c)
            return (bool(found), f"{found[0]} (+{len(found) - 1} more)" if len(found) > 1 else (found[0] if found else ""))

        checks.append({
            "id": "alpine_csp_expression_violations",
            "name": "CSP: Non-dot-path Alpine expressions",
            "severity": csp,
            "custom_check": _csp_expr,
        })
        checks.append({
            "id": "dynamic_script_php_data",
            "name": "CSP: Dynamic PHP data / JSON in <script>",
            "severity": "warning",
            "custom_check": lambda c, vc: (
                hc.has_dynamic_script_php(c),
                "Dynamic PHP data inside an inline <script> creates a new CSP hash per render (FPC bloat). "
                "Pass data via DOM data-* attributes instead.",
            ),
        })

        def _unregistered(c, vc):
            raw, reg = hc.inline_script_stats(c)
            return (raw > reg, f"{raw} inline <script> tag(s) vs {reg} registerInlineScript() call(s) — blocked by strict CSP.")

        checks.append({
            "id": "unregistered_inline_scripts",
            "name": "CSP: Unregistered inline <script> blocks",
            "severity": csp,
            "custom_check": _unregistered,
        })
        checks.append({
            "id": "dynamic_script_hash_growth",
            "name": "CSP: Dynamic script hash growth in FPC",
            "severity": "warning",
            "custom_check": lambda c, vc: (
                hc.has_dynamic_script_hash(c),
                "uniqid()/$uniqueId inside <script> yields a new SHA-256 per render and bloats the cache. "
                "Pass dynamic values via DOM data-* attributes.",
            ),
        })

        # ── Vendor feature parity (CSP-specific) ──
        def _missing_csp(vc, c):
            raw, reg = hc.inline_script_stats(c)
            return (
                raw > 0 and reg == 0 and ("registerInlineScript" in vc or "hyvaCsp" in vc),
                "Upstream added Hyvä CSP script registration but the child-theme override lacks it.",
            )

        checks.append({
            "id": "vendor_alignment_missing_csp",
            "name": "Vendor Parity: missing Hyvä CSP registration",
            "severity": csp,
            "vendor_check": _missing_csp,
        })
        checks.append({
            "id": "vendor_alignment_csp",
            "name": "Vendor Parity: Alpine.data CSP component",
            "severity": "warning",
            "vendor_check": lambda vc, c: (
                ("Alpine.data" in vc or 'x-data="' in vc) and 'x-data="{' in c,
                "Upstream migrated to a named Alpine.data component; the override still uses an inline x-data object.",
            ),
        })

    # ── Vendor feature parity (General) ──
    checks.append({
        "id": "vendor_alignment_purifier",
        "name": "Vendor Parity: Purifier ViewModel sanitisation",
        "severity": "warning",
        "vendor_check": lambda vc, c: (
            "Purifier::class" in vc and "Purifier::class" not in c,
            "Upstream added the Purifier ViewModel to sanitise HTML output; the override lacks it.",
        ),
    })
    return checks


# ─── Runner ───────────────────────────────────────────────────────────────────

def run_checks(checks, templates, theme_dir, vendor_theme, module_index, skip_vendor):
    results = {c["id"]: [] for c in checks}
    for tpl in templates:
        rel = tpl.relative_to(theme_dir)
        content = tpl.read_text(encoding="utf-8", errors="ignore")
        vendor_file, _ = hc.resolve_vendor_template(rel, vendor_theme, module_index)
        vendor_content = (
            vendor_file.read_text(encoding="utf-8", errors="ignore") if vendor_file and vendor_file.exists() else ""
        )
        for check in checks:
            cid = check["id"]
            for pattern, desc in check.get("patterns", []):
                if pattern.search(content):
                    combo = check.get("critical_combo")
                    if combo and combo[0].search(content):
                        results[cid].append((str(rel), combo[1], True))
                    else:
                        results[cid].append((str(rel), desc, False))
            if "custom_check" in check:
                matched, desc = check["custom_check"](content, vendor_content)
                if matched:
                    results[cid].append((str(rel), desc, False))
            if "vendor_check" in check and not skip_vendor and vendor_content:
                matched, desc = check["vendor_check"](vendor_content, content)
                if matched:
                    results[cid].append((str(rel), desc, False))
    return results


def lint_php(templates, theme_dir, php_cmd):
    """Run `php -l` on every template. Returns (errors, skipped_reason | None)."""
    cmd = shlex.split(php_cmd)
    if not shutil.which(cmd[0]):
        return [], f"'{cmd[0]}' not found — pass --php-cmd (e.g. \"govard env exec php\") or install PHP"
    errors = []
    for tpl in templates:
        res = subprocess.run(cmd + ["-l", str(tpl)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            errors.append((str(tpl.relative_to(theme_dir)), (res.stderr or res.stdout).strip()))
    return errors, None


def main() -> None:
    hc.ensure_python()
    parser = argparse.ArgumentParser(description="Hyvä Theme Upgrade Auditor")
    parser.add_argument("--config", help="Path to .hyva-upgrade.json (default: project root)")
    parser.add_argument("--theme", help="Hyvä child theme directory")
    parser.add_argument("--vendor", help="Hyvä default theme directory")
    parser.add_argument("--module", help="Module filter, e.g. Magento_Checkout or 'Amasty_*'")
    parser.add_argument("--lint-php", action="store_true", help="Run `php -l` on all templates")
    parser.add_argument("--php-cmd", help='PHP launcher (default: config commands.php or "php")')
    parser.add_argument("--skip-vendor-align", action="store_true", help="Skip vendor feature-parity checks")
    parser.add_argument("--strict-csp", dest="strict_csp", action="store_true", default=None,
                        help="Treat CSP findings as FATAL (default: config strictCsp)")
    parser.add_argument("--no-strict-csp", dest="strict_csp", action="store_false",
                        help="Treat CSP findings as warnings")
    parser.add_argument("--audit-csp", action="store_true",
                        help="Include CSP checks as warnings even if strictCsp is false in config")
    parser.add_argument("--fail-on-warning", action="store_true", help="Exit 1 on warnings as well")
    parser.add_argument("--output", choices=["text", "json"], default="text")
    args = parser.parse_args()

    hc.enter_project_root()
    config = hc.load_config(args.config, quiet=args.output == "json")
    from_ver = config.get("from_version", "1.4.0")
    to_ver = config.get("to_version", "1.5.2")
    strict_csp = hc.resolve_strict_csp(args.strict_csp, config)
    theme_dir = hc.resolve_theme_path(args.theme, config)
    vendor_theme = hc.resolve_vendor_theme(args.vendor, config, strict_csp=strict_csp)
    tw_version = hc.detect_tailwind_version(theme_dir)
    php_cmd = args.php_cmd or (config.get("commands") or {}).get("php") or "php"

    pattern = f"{args.module}/**/*.phtml" if args.module else "**/*.phtml"
    templates = sorted(theme_dir.glob(pattern))
    if args.module and not templates:
        sys.stderr.write(f"{RED}❌ No templates match --module {args.module!r} in {theme_dir}{RESET}\n")
        sys.exit(2)

    checks = build_checks(from_ver, to_ver, strict_csp, args.audit_csp, tw_version=tw_version)
    module_index = hc.build_vendor_module_index()

    if args.output == "text":
        print("=" * 75)
        print(f"{BOLD}🔍 Hyvä Theme Upgrade Auditor{RESET}")
        print(f"Upgrade range  : {BOLD}{from_ver} → {to_ver}{RESET}")
        print(f"Target theme   : {BOLD}{theme_dir}{RESET}" + (f"  (module: {args.module})" if args.module else ""))
        print(f"Vendor theme   : {vendor_theme} ({'✅ Found' if vendor_theme.exists() else '❌ Not found'})")
        if strict_csp:
            mode = f"{RED}STRICT — CSP findings are fatal{RESET}"
        elif args.audit_csp:
            mode = f"{YELLOW}AUDIT — CSP findings are warnings{RESET}"
        else:
            mode = f"{CYAN}DISABLED (strictCsp: false) — strict CSP checks skipped. Pass --audit-csp to audit.{RESET}"
        print(f"CSP mode       : {mode}")
        if args.skip_vendor_align:
            print(f"{YELLOW}⚠️  Vendor alignment checks skipped (--skip-vendor-align){RESET}")
        elif not vendor_theme.exists():
            print(f"{YELLOW}⚠️  Vendor theme missing → vendor-parity checks have nothing to compare against{RESET}")
        print("=" * 75)
        print(f"Scanning {BOLD}{len(templates)}{RESET} templates...\n")

    results = run_checks(checks, templates, theme_dir, vendor_theme, module_index, args.skip_vendor_align)

    php_errors, php_skip = ([], None)
    if args.lint_php:
        php_errors, php_skip = lint_php(templates, theme_dir, php_cmd)

    sev = {c["id"]: c["severity"] for c in checks}
    totals = {s: sum(len(f) for cid, f in results.items() if sev[cid] == s) for s in SEVERITY_ORDER}
    totals["fatal"] += len(php_errors)

    if args.output == "json":
        print(json.dumps({
            "upgrade_range": f"{from_ver} → {to_ver}",
            "theme": str(theme_dir),
            "strict_csp": strict_csp,
            "total_templates": len(templates),
            "summary": totals,
            "results": {
                c["id"]: {
                    "name": c["name"],
                    "severity": c["severity"],
                    "findings": [{"file": f, "description": d, "critical": crit} for f, d, crit in results[c["id"]]],
                }
                for c in checks
            },
            "php_errors": [{"file": f, "error": e} for f, e in php_errors],
            "php_lint_skipped": php_skip,
        }, indent=2, ensure_ascii=False))
    else:
        print(f"{BOLD}--- 📋 AUDIT REPORT ({from_ver} → {to_ver}) ---{RESET}\n")
        palette = {"fatal": RED, "warning": YELLOW, "info": BLUE}
        for i, check in enumerate(checks, 1):
            findings = results[check["id"]]
            color = palette[check["severity"]]
            if not findings:
                status = f"{GREEN}✅ Clean{RESET}"
            elif check["severity"] == "fatal":
                status = f"{RED}❌ {len(findings)} FATAL{RESET}"
            else:
                status = f"{color}{'⚠️ ' if check['severity'] == 'warning' else 'ℹ️ '} {len(findings)} files{RESET}"
            print(f"{i}. {check['name']:<52}: {status}")
            for path, desc, critical in findings[:10]:
                print(f"   {color}• {path}{RESET}{f' {RED}← CRITICAL{RESET}' if critical else ''}")
                print(f"     {desc}")
            if len(findings) > 10:
                print(f"   {color}... and {len(findings) - 10} more (use --output json for the full list){RESET}")
        if args.lint_php:
            print(f"{len(checks) + 1}. PHP syntax (php -l)")
            if php_skip:
                print(f"   {YELLOW}⚠️  skipped: {php_skip}{RESET}")
            elif php_errors:
                for path, err in php_errors[:5]:
                    print(f"   {RED}• {path}: {err[:120]}{RESET}")
            else:
                print(f"   {GREEN}✅ all templates valid{RESET}")
        print("\n" + "=" * 75)
        if totals["fatal"]:
            print(f"{RED}{BOLD}🚨 {totals['fatal']} FATAL issue(s) — must fix before deploying!{RESET}")
        elif totals["warning"]:
            print(f"{YELLOW}{BOLD}⚠️  {totals['warning']} warning(s) — review and resolve per the 5-Step SOP.{RESET}")
            if not strict_csp:
                print(f"{YELLOW}   (strictCsp is off: CSP rules are reported as warnings. Re-run with --strict-csp to gate on them.){RESET}")
        else:
            print(f"{GREEN}{BOLD}🎉 Theme is clean and aligned with Hyvä {to_ver}!{RESET}")
        print("=" * 75)

    failed = totals["fatal"] > 0 or (args.fail_on_warning and totals["warning"] > 0)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
