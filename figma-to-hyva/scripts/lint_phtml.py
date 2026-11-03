#!/usr/bin/env python3
"""Static Hyvä rule linter for .phtml / .php files — prints violations only.

Usage:
  python3 -I lint_phtml.py FILE... | --changed [--base REF]
         [--csp strict|ready] [--tw 3|4] [--hyvacsp yes|no] [--json]

Context (CSP mode, Tailwind major, HyvaCsp availability) comes from detect.py's cache unless
forced with flags. Exit 1 when at least one error. Rule IDs match references/hyva-rules.md.
Heuristic rules are `warn`; rules that break the page / the CSP build are `error`.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

DIRECTIVE = re.compile(r"""(?P<name>@[\w.:-]+|x-on:[\w.:-]+|x-show|x-text|x-html|x-if|x-for|x-model[\w.]*|x-effect|x-init|:[\w-]+|x-bind:[\w-]+)\s*=\s*(?P<q>["'])(?P<val>.*?)(?P=q)""", re.S)
SAFE_EXPR = re.compile(r"^[\w$]+(\.[\w$]+)*$")
FOR_EXPR = re.compile(r"^\(?\s*[\w$]+(\s*,\s*[\w$]+)?\s*\)?\s+in\s+[\w$]+(\.[\w$]+)*$")
SPACING = re.compile(r"(?<![\w\[./-])(?:[a-z0-9-]+:)*-?(?:m|p|mx|my|mt|mb|ml|mr|px|py|pt|pb|pl|pr|w|h|gap|gap-x|gap-y|top|left|right|bottom|inset|space-x|space-y|size|min-w|max-w|min-h|max-h)-(\d+\.\d+)(?![\w./\]-])")
DYN_CLASS = re.compile(r"""['"](?:[a-z0-9]+:)*(?:grid-cols|col-span|row-span|text|bg|border|gap|w|h|p[xytblr]?|m[xytblr]?|flex|order|z|opacity|rounded|font)-['"]\s*\.""")
DYN_CLASS_INTERP = re.compile(r"""class\s*=\s*"[^"]*\b(?:grid-cols|col-span|text|bg|border|gap|w|h|p[xytblr]?|m[xytblr]?|order|z|rounded)-(?:<\?=|\{\$)""")
SAFE_OUT = re.compile(r"escape|\(int\)|\(float\)|json_encode|Html\s*\(|getChild|getBlockHtml|renderHtml|\$hyvaCsp|\$secureRenderer|\$block->getHtmlId|count\(|\(bool\)")
OUT_TAG = re.compile(r"<\?=\s*(.+?)\s*\?>", re.S)
ALLOWED_DECIMAL = {"0.5", "1.5", "2.5", "3.5"}


def classes_in(text: str):
    for m in re.finditer(r"""class\s*=\s*"([^"]*)"|class\s*=\s*'([^']*)'""", text):
        raw = m.group(1) if m.group(1) is not None else m.group(2)
        yield m.start(), re.sub(r"<\?.*?\?>", " ", raw, flags=re.S)


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def lint_template(path, text, ctx):
    out = []

    def add(pos, rule, sev, msg):
        out.append({"file": str(path), "line": line_of(text, pos), "rule": rule, "sev": sev, "msg": msg})

    strict = ctx["csp"] == "strict"
    ssev = "error" if strict else "warn"
    # same-length copy with PHP blocks blanked: tag regexes must not stop at the '>' of '->'
    masked = re.sub(r"<\?.*?\?>", lambda m: re.sub(r"[^\n]", "P", m.group(0)), text, flags=re.S)

    # ALP-1: directive values must be property/method paths
    for m in DIRECTIVE.finditer(text):
        val = m.group("val").strip()
        name = m.group("name")
        if not val or "<?" in val or name in ("x-init",) and SAFE_EXPR.match(val):
            continue
        if name.startswith(":class") and val.startswith("{"):
            pass
        ok = bool(SAFE_EXPR.match(val)) or (name == "x-for" and FOR_EXPR.match(val))
        if name == "x-for" and not ok:
            # x-for="item in items" with 'in' + path only; anything else is an expression
            ok = False
        if not ok:
            add(m.start(), "ALP-1", ssev, f'{name}="{val[:60]}" is an expression; use a method/getter path')
    for m in re.finditer(r"""x-data\s*=\s*["']\s*\{""", text):
        add(m.start(), "ALP-1", ssev, "x-data object literal; register Alpine.data('name', ...) and use x-data=\"name\"")
    for m in re.finditer(r"""x-data\s*=\s*["'][\w$.]+\(""", text):
        add(m.start(), "ALP-1", ssev, "x-data with call arguments; read options from data-* in init()")

    # ALP-2 / ALP-3: scripts
    scripts = [m for m in re.finditer(r"<script\b([^>]*)>(.*?)</script>", text, re.S)
               if "src=" not in m.group(1) and "ld+json" not in m.group(1) and "text/x-magento-init" not in m.group(1)]
    regs = len(re.findall(r"registerInlineScript", text))
    if scripts and regs < len(scripts) and (strict or ctx["hyvacsp"]):
        add(scripts[0].start(), "ALP-2", "error" if strict else "warn",
            f"{len(scripts)} inline <script> but {regs} registerInlineScript call(s)")
    for m in scripts:
        for p in re.finditer(r"<\?(?:=|php)", m.group(2)):
            add(m.start(2) + p.start(), "ALP-3", ssev, "PHP value inside <script>; move it to a data-* attribute")
            break
    if not ctx["hyvacsp"]:
        for m in re.finditer(r"require\(\s*\\?(?:[\w\\]*\\)?HyvaCsp::class", text):
            add(m.start(), "ALP-2", "error", "HyvaCsp viewmodel does not exist in this project (fatal)")
        for m in re.finditer(r"(?<!isset\()\$hyvaCsp->", text):
            if "isset($hyvaCsp)" not in text:
                add(m.start(), "ALP-2", "warn", "$hyvaCsp not guarded by isset() (not injected on this Hyvä version)")
                break
    if "x-show" in text and "x-cloak" not in text:
        add(text.index("x-show"), "ALP-6", "warn", "x-show used but no x-cloak in file (flash before Alpine boots)")

    # TW rules
    for pos, cls in classes_in(text):
        if ctx["tw"] == 3:
            for m in SPACING.finditer(cls):
                if m.group(1) not in ALLOWED_DECIMAL:
                    add(pos, "TW-3", "error", f"'{m.group(0)}' does not exist in Tailwind 3 (use [..px])")
            for m in re.finditer(r"(?<![\w\[])[a-z][\w:-]*!(?=\s|$)", cls):
                add(pos, "TW-4", "error", f"'{m.group(0)}' important suffix is Tailwind 4; v3 uses prefix !")
    for m in DYN_CLASS.finditer(text):
        add(m.start(), "TW-1", "error", "dynamic Tailwind class built by concatenation (purged); use a map of literals")
    for m in DYN_CLASS_INTERP.finditer(text):
        add(m.start(), "TW-1", "error", "Tailwind class interpolated from PHP (purged); use a map of literals")

    # TPL
    for m in OUT_TAG.finditer(text):
        expr = m.group(1)
        if SAFE_OUT.search(expr) or expr.startswith(("__(", "$escaper")) or "@noEscape" in expr:
            continue
        expr = re.sub(r"\s+", " ", expr)
        if re.match(r"^\$[\w>-]+\s*;?$", expr) or "->get" in expr or "getUrl" in expr or "getViewFileUrl" in expr:
            add(m.start(), "TPL-2", "warn", f"possibly unescaped output: <?= {expr[:50]} ?>")
    for m in re.finditer(r"(ObjectManager|->getCollection\(\)|->load\(\$)", text):
        add(m.start(), "TPL-1", "warn", f"business logic in template ({m.group(1)}); move to Block/ViewModel")
    for m in re.finditer(r"<img\b(?![^>]*\balt\s*=)[^>]*>", masked, re.S):
        add(m.start(), "A11Y-3", "warn", "<img> without alt (use alt=\"\" aria-hidden=\"true\" if decorative)")
    for m in re.finditer(r"<a\b[^>]*target\s*=\s*[\"']_blank[\"'][^>]*>", masked, re.S):
        if "noopener" not in text[m.start():m.end()]:
            add(m.start(), "A11Y-5", "warn", 'target="_blank" without rel="noopener noreferrer"')
    for m in re.finditer(r"<(div|span|li)\b[^>]*(?:@click|x-on:click)[^>]*>", masked, re.S):
        if "role=" not in masked[m.start():m.end()] and "tabindex" not in masked[m.start():m.end()]:
            add(m.start(), "A11Y-4", "warn", f"<{m.group(1)}> with click handler but no role/tabindex (use <button>)")
    body = re.sub(r"<script\b.*?</script>|<style\b.*?</style>|<\?.*?\?>|<!--.*?-->", " ", text, flags=re.S)
    for m in re.finditer(r">\s*([A-Z][A-Za-zÀ-ÿ'’,.!?-]+(?:\s+[A-Za-zÀ-ÿ'’,.!?-]+){1,})\s*<", body):
        txt = m.group(1)
        if re.search(r"\b(true|false|null)\b", txt):
            continue
        out.append({"file": str(path), "line": line_of(text, max(text.find(txt.split()[0]), 0)), "rule": "TPL-3", "sev": "warn",
                    "msg": f"hardcoded text '{txt[:40]}' — wrap in __() and add to i18n"})
        break
    return out


def lint_php(path, text, ctx):
    out = []

    def add(pos, rule, sev, msg):
        out.append({"file": str(path), "line": line_of(text, pos), "rule": rule, "sev": sev, "msg": msg})

    if "declare(strict_types=1)" not in text:
        add(0, "PHP-10", "warn", "missing declare(strict_types=1)")
    for m in re.finditer(r"ObjectManager::getInstance|->createBlock\(", text):
        add(m.start(), "PHP-10", "error" if "ObjectManager" in m.group(0) else "warn",
            f"{m.group(0)} in business code; inject via constructor")
    for m in re.finditer(r"->addChild\(", text):
        add(m.start(), "PHP-3", "warn", "addChild() registers '<parent>.<alias>'; fetch with getChildBlock($alias)")
    for m in re.finditer(r"hasData\(\s*['\"](?:show|enable|is_|display)[^'\"]*['\"]\s*\)", text):
        add(m.start(), "PHP-4", "warn", "hasData() on a boolean widget param is true for '0'; use (bool) getData()")
    return out


def changed_lines(root, base, f):
    """Set of added/modified line numbers vs base, or None when the whole file is new/untracked."""
    import subprocess
    rel = os.path.relpath(f, root)
    tracked = subprocess.run(["git", "-C", str(root), "ls-files", "--error-unmatch", rel], capture_output=True).returncode == 0
    if not tracked:
        return None
    r = subprocess.run(["git", "-C", str(root), "diff", "-U0", base, "--", rel], capture_output=True, text=True)
    lines = set()
    for m in re.finditer(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", r.stdout, re.M):
        start, n = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
        lines.update(range(start, start + max(n, 0)))
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--changed", action="store_true")
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--csp", choices=["strict", "ready"])
    ap.add_argument("--tw", type=int, choices=[3, 4])
    ap.add_argument("--hyvacsp", choices=["yes", "no"])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--all-lines", action="store_true", help="do not restrict to lines changed vs --base")
    a = ap.parse_args()

    root = _lib.find_root(os.path.dirname(os.path.abspath(a.files[0])) if a.files else None)
    ctx = {"csp": a.csp, "tw": a.tw, "hyvacsp": None if not a.hyvacsp else a.hyvacsp == "yes"}
    if None in (ctx["csp"], ctx["tw"], ctx["hyvacsp"]):
        try:
            info = _lib.project(root)
            ctx["csp"] = ctx["csp"] or info["csp_mode"]
            ctx["tw"] = ctx["tw"] or info["tw"]
            ctx["hyvacsp"] = info["hyvacsp"] if ctx["hyvacsp"] is None else ctx["hyvacsp"]
        except Exception:
            ctx.update({"csp": ctx["csp"] or "ready", "tw": ctx["tw"] or 3, "hyvacsp": bool(ctx["hyvacsp"])})
    files = [__import__("pathlib").Path(f).resolve() for f in a.files]
    if a.changed:
        files += [f for f in _lib.git_changed(root, a.base, (".phtml", ".php"))]
    results = []
    for f in dict.fromkeys(files):
        text = _lib.read(f)
        if f.suffix == ".phtml":
            found = lint_template(f, text, ctx)
        elif f.suffix == ".php" and re.search(r"/app/(code|design)/", str(f)):
            found = lint_php(f, text, ctx)
        else:
            continue
        keep = None if a.all_lines else changed_lines(root, a.base, f)
        results += [r for r in found if keep is None or r["line"] in keep]
    for r in results:
        try:
            r["file"] = os.path.relpath(r["file"], root)
        except ValueError:
            pass
    errors = sum(r["sev"] == "error" for r in results)
    if a.json:
        print(json.dumps({"context": ctx, "files": len(set(files)), "errors": errors, "results": results}, indent=1))
    else:
        for r in sorted(results, key=lambda r: (r["file"], r["line"])):
            loc = f"{r['file']}:{r['line']}" if r["line"] else r["file"]
            print(f"{loc} {r['rule']} {r['sev']}: {r['msg']}")
        print(f"lint: {len(set(files))} file(s), {errors} error(s), {len(results) - errors} warning(s) "
              f"[csp={ctx['csp']} tw={ctx['tw']} hyvacsp={'yes' if ctx['hyvacsp'] else 'no'}]")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
