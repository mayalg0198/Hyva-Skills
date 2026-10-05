#!/usr/bin/env python3
"""
suggest-refactor.py — Recipe Generator for Alpine.js Strict CSP Refactoring
=============================================================================
Analyzes a .phtml template and prints actionable Before/After refactoring
recipes for all detected non-CSP Alpine expressions:
  - Calls with arguments → data-* attributes + dataset event listener
  - Ternary operators → component getters / computed properties
  - Object literals in :class → component class methods or array classes
  - Binary concatenation → template methods or computed IDs

Usage:
  python3 scripts/suggest-refactor.py <path/to/template.phtml>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import csp_common as cc
from csp_common import BOLD, CYAN, DIM, GREEN, MAGENTA, RED, RESET, YELLOW


def analyze_template_recipes(file_path: Path):
    try:
        raw = file_path.read_text(encoding="utf-8")
    except Exception as exc:
        sys.stderr.write(f"{RED}❌ Cannot read {file_path}: {exc}{RESET}\n")
        return

    clean = cc.strip_html_comments(cc.strip_php(raw))

    ATTR_SCAN_RE = re.compile(
        r"""(?P<attr>@[\w\.-]+|:[\w\.-]+|x-[\w\.-]+)\s*=\s*(?P<quote>["'])(?P<val>.*?)(?P=quote)""",
        re.DOTALL
    )

    recipes = []

    for m in ATTR_SCAN_RE.finditer(clean):
        attr = m.group("attr")
        val = m.group("val").strip()
        line_no = clean[:m.start()].count("\n") + 1

        if not val or attr == "x-for":
            continue

        # 1. Call with arguments
        call_m = re.search(r"""\b([a-zA-Z0-9_$]+)\s*\(\s*(?!\s*\))([^)]+)\)""", val)
        if call_m:
            fn_name = call_m.group(1)
            args_str = call_m.group(2)
            if attr == "x-data":
                recipes.append({
                    "line": line_no,
                    "type": "x-data Component Configuration Argument",
                    "attr": attr,
                    "original": f'{attr}="{val}"',
                    "before": f'<{attr}="{fn_name}({args_str})">',
                    "after": f'// In HTML template:\n'
                             f'<div x-data="{fn_name}"\n'
                             f'     data-config-field="<?= $escaper->escapeHtmlAttr(...) ?>">\n\n'
                             f'// In Alpine component JS factory:\n'
                             f'function {fn_name}() {{\n'
                             f'    return {{\n'
                             f'        configField: null,\n'
                             f'        init() {{\n'
                             f'            this.configField = this.$el.dataset.configField;\n'
                             f'        }}\n'
                             f'    }};\n'
                             f'}}',
                    "doc": "alpine3-csp.js cannot evaluate arguments in x-data. Pass configuration via HTML5 data-* attributes and read them in init() via this.$el.dataset."
                })
            else:
                recipes.append({
                    "line": line_no,
                    "type": "Function Call with Arguments",
                    "attr": attr,
                    "original": f'{attr}="{val}"',
                    "before": f'<{attr}="{fn_name}({args_str})">',
                    "after": f'<{attr}="{fn_name}" data-item-id="<?= $escaper->escapeHtmlAttr(...) ?>">\n\n'
                             f'// In Alpine component JS:\n'
                             f'{fn_name}(event) {{\n'
                             f'    const itemId = event.currentTarget.dataset.itemId;\n'
                             f'    // ... your logic\n'
                             f'}}',
                    "doc": "alpine3-csp.js cannot evaluate arguments. Use zero-argument calls and retrieve parameters via event.currentTarget.dataset."
                })
            continue

        # 2. Ternary operator
        if "?" in val and ":" in val:
            recipes.append({
                "line": line_no,
                "type": "Ternary Operator",
                "attr": attr,
                "original": f'{attr}="{val}"',
                "before": f'<{attr}="{val}">',
                "after": f'// In HTML template:\n'
                         f'<{attr}="computedState">\n\n'
                         f'// In Alpine component JS factory:\n'
                         f'get computedState() {{\n'
                         f'    return {val};\n'
                         f'}}',
                "doc": "Ternary operators are blocked by strict CSP evaluator. Replace with an Alpine getter."
            })
            continue

        # 3. Object literal
        if val.startswith("{") and val.endswith("}") and ":" in val:
            if attr == "x-data":
                recipes.append({
                    "line": line_no,
                    "type": "Inline Object Literal in x-data",
                    "attr": attr,
                    "original": f'{attr}="{val}"',
                    "before": f'<{attr}="{val}">',
                    "after": f'// In HTML template:\n'
                             f'<div x-data="initMyComponent">\n\n'
                             f'// In companion JS or inline script:\n'
                             f'function initMyComponent() {{\n'
                             f'    return {{\n'
                             f'        // component properties\n'
                             f'    }};\n'
                             f'}}\n'
                             f'window.initMyComponent = initMyComponent;',
                    "doc": "Inline object literals in x-data cannot be evaluated by alpine3-csp.js. Extract state into an Alpine data factory function."
                })
            else:
                recipes.append({
                    "line": line_no,
                    "type": "Object Literal in Binding",
                    "attr": attr,
                    "original": f'{attr}="{val}"',
                    "before": f'<{attr}="{val}">',
                    "after": f'// In HTML template:\n'
                             f'<{attr}="activeClasses">\n\n'
                             f'// In Alpine component JS factory:\n'
                             f'get activeClasses() {{\n'
                             f'    // Return string or array of class names\n'
                             f'    return this.isActive ? "active font-bold" : "";\n'
                             f'}}',
                    "doc": "Object literals in :class or other bindings require JS eval(). Return strings or arrays from a getter."
                })
            continue

        # 4. Comparison expression
        if re.search(r"""(?:===|!==|==|!=|<=|>=|<|>)""", val):
            clean_expr = val.lstrip("\\")
            recipes.append({
                "line": line_no,
                "type": "Comparison Expression",
                "attr": attr,
                "original": f'{attr}="{val}"',
                "before": f'<{attr}="{val}">',
                "after": f'// In HTML template:\n'
                         f'<{attr}="isMatchingState">\n\n'
                         f'// In Alpine component JS factory:\n'
                         f'get isMatchingState() {{\n'
                         f'    return {clean_expr};\n'
                         f'}}',
                "doc": "Comparison operators require JS evaluation which is disabled under strict CSP. Move comparison into a getter."
            })
            continue

        # 5. Logical operators (&&, ||)
        if re.search(r"""(?:&&|\|\|)""", val):
            clean_expr = val.lstrip("\\")
            recipes.append({
                "line": line_no,
                "type": "Logical Expression (&& / ||)",
                "attr": attr,
                "original": f'{attr}="{val}"',
                "before": f'<{attr}="{val}">',
                "after": f'// In HTML template:\n'
                         f'<{attr}="shouldShow">\n\n'
                         f'// In Alpine component JS factory:\n'
                         f'get shouldShow() {{\n'
                         f'    return {clean_expr};\n'
                         f'}}',
                "doc": "Logical operators cannot be evaluated by the alpine3-csp dot-path evaluator. Refactor to a getter method."
            })
            continue

        # 6. Binary concatenation
        if "+" in val and ("'" in val or '"' in val):
            recipes.append({
                "line": line_no,
                "type": "String Concatenation",
                "attr": attr,
                "original": f'{attr}="{val}"',
                "before": f'<{attr}="{val}">',
                "after": f'// In HTML template:\n'
                         f'<{attr}="formattedId">\n\n'
                         f'// In Alpine component JS factory:\n'
                         f'get formattedId() {{\n'
                         f'    return `{val}`;\n'
                         f'}}',
                "doc": "Binary + operator in attribute bindings is blocked. Compute full string inside the Alpine component."
            })
            continue

    # 7. Check for nondeterministic script text (Sutunam BeBe9 Gotcha 8: Dynamic Script Hash Growth)
    NONDETERMINISTIC_RE = re.compile(
        r"\b(?:uniqid|random_int|rand|microtime|mt_rand|random_bytes)\s*\(",
        re.IGNORECASE
    )
    for m in cc._SCRIPT_BLOCK.finditer(raw):
        script_full = m.group(0)
        line_no = raw[:m.start()].count("\n") + 1
        for php_call in re.findall(r"<\?(?:php|=).*?\?>", script_full, re.DOTALL):
            if NONDETERMINISTIC_RE.search(php_call):
                recipes.append({
                    "line": line_no,
                    "type": "Nondeterministic Script Text (Dynamic Hash Growth)",
                    "attr": "script",
                    "original": php_call.strip(),
                    "before": script_full.strip()[:140] + "\n...",
                    "after": "// In HTML element:\n"
                             "<div data-token=\"<?= $escaper->escapeHtmlAttr($token) ?>\" x-data=\"myComponent\"></div>\n\n"
                             "// In static <script>:\n"
                             "Alpine.data('myComponent', () => ({\n"
                             "    token: null,\n"
                             "    init() { this.token = this.$el.dataset.token; }\n"
                             "}));\n\n"
                             "<?php isset($hyvaCsp) && $hyvaCsp->registerInlineScript(); ?>",
                    "doc": "Changing script text per render causes SHA-256 hashes to accumulate in FPC (from 1 to 30+ hashes). Keep script text deterministic and move dynamic values to HTML5 data-* attributes or inert JSON."
                })

    print("=" * 80)
    print(f"{BOLD}💡 Hyvä Strict CSP Refactoring Recipes{RESET}")
    print(f"File: {file_path}")
    print("=" * 80 + "\n")

    if not recipes:
        print(f"{GREEN}✅ No complex Alpine expressions needing refactoring in this template!{RESET}\n")
        return

    for idx, r in enumerate(recipes, 1):
        print(f"{BOLD}{CYAN}Recipe #{idx} (Line {r['line']}): {r['type']}{RESET}")
        print(f"{DIM}Issue: {r['doc']}{RESET}\n")
        print(f"  {RED}❌ Before (Non-CSP):{RESET}")
        for l in r['before'].splitlines():
            print(f"     {l}")
        print(f"\n  {GREEN}✅ After (CSP-Compliant Pattern):{RESET}")
        for l in r['after'].splitlines():
            print(f"     {l}")
        print("\n" + "-" * 80 + "\n")


def main():
    cc.ensure_python()
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/suggest-refactor.py <path/to/template.phtml>")
        sys.exit(2)

    target = Path(sys.argv[1]).resolve()
    if not target.is_file():
        print(f"Error: File not found: {target}")
        sys.exit(2)

    analyze_template_recipes(target)


if __name__ == "__main__":
    main()
