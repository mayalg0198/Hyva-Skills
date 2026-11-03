#!/usr/bin/env python3
"""
suggest-refactor.py — Before/After recipes for Alpine strict-CSP refactoring
============================================================================
Uses the same classifier as audit-csp.py, so every audit finding in a template
gets a recipe. Generated getters/methods reference component state via `this.`
and components are registered with Alpine.data (the CSP build does not look up
window globals). Treat the output as a starting point: check names and logic.

Usage:
  python3 scripts/suggest-refactor.py <path/to/template.phtml>
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import csp_common as cc
from csp_common import BOLD, CYAN, DIM, GREEN, RED, RESET

_spec = importlib.util.spec_from_file_location("audit_csp", Path(__file__).resolve().parent / "audit-csp.py")
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)

JS_WORDS = {
    "true", "false", "null", "undefined", "typeof", "instanceof", "new", "in", "of",
    "Math", "Object", "Array", "Number", "String", "JSON", "Date", "parseInt", "parseFloat",
    "window", "document", "event", "this",
}
_TOKEN = re.compile(r"""('(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*"|`(?:\\.|[^`\\])*`)|(\.\s*)?(\$?[A-Za-z_][\w$]*)""")


def with_this(expr: str) -> str:
    """Prefix free identifiers with `this.` (skips strings, members, JS globals, arrow params)."""
    params = set(re.findall(r"([A-Za-z_$][\w$]*)\s*=>", expr))
    for group in re.findall(r"\(([^()]*)\)\s*=>", expr):
        params |= {p.strip() for p in group.split(",") if p.strip()}

    def repl(m: re.Match) -> str:
        if m.group(1):
            return m.group(1)
        dot, name = m.group(2), m.group(3)
        if dot or name in JS_WORDS or name in params or name == "__PHP__":
            return m.group(0)
        return f"this.{name}"
    return _TOKEN.sub(repl, expr).replace("__PHP__", "/* PHP value → read from this.$el.dataset */")


def camel(words: list) -> str:
    words = [w for w in words if w]
    if not words:
        return "computed"
    return words[0][0].lower() + words[0][1:] + "".join(w[:1].upper() + w[1:] for w in words[1:])


def name_for(attr: str, val: str, used: set) -> str:
    """Readable, unique getter/method name derived from the attribute and expression."""
    idents = []
    for i in re.findall(r"\$?[A-Za-z_]\w*", re.sub(r"'[^']*'|\"[^\"]*\"", "", val)):
        i = i.lstrip("$")
        if i not in JS_WORDS and i != "__PHP__" and i not in idents:
            idents.append(i)
    idents = idents[:2]
    role = attr.lstrip("@:").replace("x-bind:", "").replace("x-on:", "").split(".")[0].split(":")[-1]
    prefix = {"x-show": "is", "x-if": "is", "disabled": "is"}.get(role, "")
    suffix = {"class": "Classes", "style": "Style", "x-for": "List", "id": "Id", "href": "Url"}.get(role, "")
    if val.lstrip().startswith("!"):
        prefix = "isNot"
    elif role == "method":
        toggle = re.match(r"^\s*([\w$]+)\s*=\s*!\s*\1\s*$", val)
        falsy = re.match(r"^\s*[\w$]+\s*=\s*(false|null|''|0)\s*$", val)
        prefix = "toggle" if toggle else ("clear" if falsy else "set")
        idents = idents[:1]
    base = camel(([prefix] if prefix else []) + [i[:1].upper() + i[1:] if prefix else i for i in idents]) + suffix
    name, n = base, 2
    while name in used:
        name, n = f"{base}{n}", n + 1
    used.add(name)
    return name


def recipe(fid: str, attr: str, val: str, used: set) -> tuple:
    """Return (after_html, js) for one finding."""
    if fid == "csp_call_parens":
        return f'{attr}="{val[:val.index("(")].strip()}"', "// No JS change: the method is called with the event automatically."
    if fid == "csp_call_with_args":
        m = re.match(r"\s*([\w$.]+)\s*\((.*)\)\s*$", val, re.S)
        fn = m.group(1).split(".")[-1] if m else name_for("method", val, used)
        args = [a.strip() for a in (m.group(2).split(",") if m else []) if a.strip()]
        data_attrs = " ".join(
            f'data-arg-{i}="<?= $escaper->escapeHtmlAttr(...) ?>"' if a == "__PHP__" else f':data-arg-{i}="{a}"'
            for i, a in enumerate(args)) or 'data-arg-0="..."'
        if attr == "x-data":
            reads = "\n".join(f"      this.arg{i} = this.$el.dataset.arg{i}; // was: {a}" for i, a in enumerate(args))
            return (f'x-data="{fn}" {data_attrs}',
                    f"function {fn}() {{\n  return {{\n    init() {{\n{reads}\n    }}\n  }};\n}}\n"
                    f"window.addEventListener('alpine:init', () => Alpine.data('{fn}', {fn}), {{once: true}});")
        reads = "\n".join(f"    const arg{i} = event.currentTarget.dataset.arg{i}; // was: {a}" for i, a in enumerate(args))
        note = ("\n// :data-arg-N=\"prop\" only works when prop is itself a plain path; otherwise expose it via a getter."
                if any(a != "__PHP__" for a in args) else "")
        return f'{attr}="{fn}" {data_attrs}', f"{fn}(event) {{\n{reads}\n    // ... original logic\n}}{note}"
    if fid == "csp_xdata_object_literal":
        fn = name_for("x-data", "init component", used)
        return (f'x-data="{fn}"',
                f"function {fn}() {{\n  return {val};\n}}\n"
                f"window.addEventListener('alpine:init', () => Alpine.data('{fn}', {fn}), {{once: true}});")
    if fid in ("csp_assignment", "csp_multi_statement"):
        fn = name_for("method", val, used)
        stmts = "\n".join(f"    {with_this(s.strip())};" for s in val.split(";") if s.strip())
        return f'{attr}="{fn}"', f"{fn}() {{\n{stmts}\n}}"
    if fid == "csp_function_definition":
        fn = name_for("method", val, used)
        return f'{attr}="{fn}"', f"{fn}(event) {{\n    // body of: {val}\n}}"
    if fid == "csp_xfor_expr":
        m = audit._XFOR.match(val)
        src = m.group("src") if m else val
        getter = name_for("x-for", src, used)
        head = val[:m.start("src")] if m else "item in "
        return f'x-for="{head}{getter}"', f"get {getter}() {{\n    return {with_this(src)};\n}}"
    if fid == "csp_object_literal":
        getter = name_for(attr, val, used)
        pairs = re.findall(r"""['"]?([^'":,{}]+?)['"]?\s*:\s*([^,}]+)""", val)
        lines = "\n".join(
            f"    if ({with_this(cond.strip())}) classes.push("
            + (f"this.$el.dataset.class{i} /* PHP class → data-class-{i} */" if "__PHP__" in cls else f"'{cls.strip()}'")
            + ");" for i, (cls, cond) in enumerate(pairs))
        return f'{attr}="{getter}"', f"get {getter}() {{\n    const classes = [];\n{lines}\n    return classes.join(' ');\n}}"
    # ternary / comparison / logical / negation / binary / not-dot-path → getter returning the expression
    getter = name_for(attr, val, used)
    return f'{attr}="{getter}"', f"get {getter}() {{\n    return {with_this(val)};\n}}"


def analyze_template_recipes(file_path: Path) -> int:
    try:
        raw = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        sys.stderr.write(f"{RED}❌ Cannot read {file_path}: {exc}{RESET}\n")
        return 2

    masked = cc.strip_html_comments(cc.mask_php(raw))
    used: set = set()
    recipes = []
    for m in audit.ATTR_SCAN_RE.finditer(masked):
        attr = m.group("attr")
        if attr.startswith(audit.SKIP_ATTRS):
            continue
        val = re.sub(r"\s+", " ", m.group("val")).strip()
        result = audit.classify_expression(attr, val) if val else None
        if not result:
            continue
        fid, msg = result
        after, js = recipe(fid, attr, val, used)
        recipes.append({"line": masked[:m.start()].count("\n") + 1, "type": fid, "doc": msg,
                        "before": f'{attr}="{val}"', "after": after, "js": js})

    for f in audit.inspect_template_csp(file_path):
        if f["id"] == "inline_event_handler":
            attr, _, val = f["snippet"].partition("=")
            fn = name_for("method", val.strip('"'), used)
            recipes.append({
                "line": f["line"], "type": f["id"], "doc": f["msg"], "before": f["snippet"],
                "after": f'@{attr[2:].lower()}="{fn}"  (inside the component\'s x-data element)',
                "js": f"{fn}(event) {{\n    // body of: {val.strip(chr(34))}\n}}",
            })
        elif f["id"] == "javascript_url":
            recipes.append({
                "line": f["line"], "type": f["id"], "doc": f["msg"], "before": f["snippet"],
                "after": '<button type="button" @click="doAction">…</button>',
                "js": "doAction() {\n    // logic that was in the javascript: URL\n}",
            })
        elif f["id"] == "nonstandard_hyva_csp_call":
            recipes.append({
                "line": f["line"], "type": f["id"], "doc": f["msg"], "before": f["snippet"],
                "after": "<?php $hyvaCsp->registerInlineScript() ?>   (or isset($hyvaCsp) && … for Luma-compatible modules)",
                "js": f"// automatic: {cc.run_cmd('fix-scripts ' + cc.display_path(file_path) + ' --normalize --dry-run')}",
            })
        if f["id"] == "nondeterministic_script_hash":
            recipes.append({
                "line": f["line"], "type": f["id"], "doc": f["msg"], "before": f["snippet"],
                "after": '<div x-data="myComponent" data-token="<?= $escaper->escapeHtmlAttr($token) ?>"></div>',
                "js": "<script>\n  window.addEventListener('alpine:init', () => Alpine.data('myComponent', () => ({\n"
                      "    token: null,\n    init() { this.token = this.$el.dataset.token; }\n  })), {once: true});\n"
                      "</script>\n<?php $hyvaCsp->registerInlineScript() ?>",
            })

    print("=" * 80)
    print(f"{BOLD}💡 Hyvä Strict CSP Refactoring Recipes{RESET}")
    print(f"File: {cc.display_path(file_path)}")
    print("=" * 80 + "\n")
    if not recipes:
        print(f"{GREEN}✅ No Alpine expressions need refactoring in this template.{RESET}\n")
        return 0

    for idx, r in enumerate(sorted(recipes, key=lambda r: r["line"]), 1):
        print(f"{BOLD}{CYAN}#{idx} line {r['line']} [{r['type']}]{RESET}")
        print(f"{DIM}{r['doc']}{RESET}")
        print(f"  {RED}❌ {r['before']}{RESET}")
        print(f"  {GREEN}✅ {r['after']}{RESET}")
        for line in r["js"].splitlines():
            print(f"     {line}")
        print()
    print(f"{DIM}Generated names/logic are a starting point — review before applying.{RESET}")
    return 0


def main():
    cc.ensure_python()
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: python3 scripts/suggest-refactor.py <path/to/template.phtml>\n")
        sys.exit(2)
    target = Path(sys.argv[1]).resolve()
    if not target.is_file():
        sys.stderr.write(f"{RED}❌ File not found: {target}{RESET}\n")
        sys.exit(2)
    sys.exit(analyze_template_recipes(target))


if __name__ == "__main__":
    main()
