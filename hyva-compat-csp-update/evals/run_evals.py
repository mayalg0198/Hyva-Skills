#!/usr/bin/env python3
"""Offline regression suite for hyva-compat-csp-update (no Magento, no network).

Usage: python3 -I evals/run_evals.py
Builds throw-away project roots (with and without Hyvä's HyvaCsp class), runs audit / fix-scripts /
suggest on fixtures that mirror what alpine3-csp.js can and cannot evaluate, and exits 1 on any
failure. Run it after editing any script or rule.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
RESULTS = []

# One line per case: id, directive, expected finding (None = must stay silent)
CASES = [
    ("c01", 'x-show="!open"', "csp_negation"),
    ("c02", '@click="toggle()"', "csp_call_parens"),
    ("c03", '@click="open = true"', "csp_assignment"),
    ("c04", '@click="open = !open"', "csp_assignment"),
    ("c05", ':disabled="true"', "csp_not_dot_path"),
    ("c06", ':tabindex="0"', "csp_not_dot_path"),
    ("c07", ":value=\"'abc'\"", "csp_not_dot_path"),
    ("c08", 'x-text="count + 1"', "csp_binary_expr"),
    ("c09", '@click="count++"', "csp_assignment"),
    ("c12", 'onclick="doIt()"', "inline_event_handler"),
    ("c13", 'href="javascript:void(0)"', "javascript_url"),
    ("c14", '@click="select(item.id)"', "csp_call_with_args"),
    ("c15", ":class=\"open ? 'a' : 'b'\"", "csp_ternary"),
    ("c16", ":class=\"{ 'a': open }\"", "csp_object_literal"),
    ("c17", 'x-show="a && b"', "csp_logical_expr"),
    ("c20", 'x-show="a === b"', "csp_comparison_expr"),
    ("c21", "x-init=\"() => go()\"", "csp_function_definition"),
    ("ok1", '@click="toggle"', None),
    ("ok2", 'x-text="item.name"', None),
    ("ok3", '@click.prevent="$dispatch"', None),
    ("ok4", 'data-max-height="100"', None),
    ("ok5", 'x-bind:aria-expanded="isOpen"', None),
]
FOR_CASES = [
    ("c10", 'x-for="i in 10"', "csp_xfor_expr"),
    ("c11", 'x-for="item in items.filter(isOn)"', "csp_xfor_expr"),
    ("ok6", 'x-for="(item, index) in items"', None),
]

SCRIPTS_TPL = """<?php $slider = uniqid(); ?>
<div x-data="initA" data-id="<?= $slider ?>"></div>
<script>
    function initA() { return { open: false }; }
    window.addEventListener('alpine:init', () => Alpine.data('initA', initA), {once: true});
</script>
<script type="application/json" id="cfg">{"a": 1}</script>
<script>
    var tainted = '<?= $slider ?>';
</script>
<script>
    var direct = '<?= uniqid() ?>';
</script>
<script>
    function initB() { return {}; }
</script>
<?php $viewModels->require(\\Hyva\\Theme\\ViewModel\\HyvaCsp::class)->registerInlineScript(); ?>
<script src="/static/x.js"></script>
"""


def make_root(tmp: Path, name: str, with_class: bool) -> Path:
    root = tmp / name
    (root / "app/code/Acme/Mod/view/frontend/templates").mkdir(parents=True)
    (root / "composer.json").write_text("{}")
    vm = root / "vendor/hyva-themes/magento2-theme-module/src/ViewModel"
    vm.mkdir(parents=True)
    if with_class:
        (vm / "HyvaCsp.php").write_text("<?php class HyvaCsp {}")
    return root


def run(script, *args, cwd):
    r = subprocess.run([sys.executable, "-I", str(SCRIPTS / script), *map(str, args)],
                       cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def audit_json(target, cwd):
    _, out = run("audit-csp.py", target, "--output", "json", cwd=cwd)
    data = json.loads(out[out.find("{"):])
    return [f for fs in data["files"].values() for f in fs]


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}" + ("" if cond else f"\n     {str(detail)[:500]}"))


def main():
    tmp = Path(tempfile.mkdtemp(prefix="csp-evals-"))
    try:
        root = make_root(tmp, "m2", with_class=True)
        tdir = root / "app/code/Acme/Mod/view/frontend/templates"

        # ---- directive classification
        lines = ['<div x-data="initX">'] + [f'<a id="{cid}" {d}>x</a>' for cid, d, _ in CASES]
        lines += [f'<template {d}><span id="{cid}">x</span></template>' for cid, d, _ in FOR_CASES] + ["</div>"]
        (tdir / "cases.phtml").write_text("\n".join(lines) + "\n")
        by_line = {}
        for f in audit_json(tdir / "cases.phtml", root):
            by_line.setdefault(f["line"], set()).add(f["id"])
        for n, (cid, d, want) in enumerate(CASES + FOR_CASES, start=2):
            got = by_line.get(n, set())
            if want:
                check(f"{cid} {d} -> {want}", want in got, got)
            else:
                check(f"{cid} {d} stays silent", not got, got)

        # ---- scripts: registration, nondeterminism, json, nonstandard call
        (tdir / "scripts.phtml").write_text(SCRIPTS_TPL)
        ids = [(f["id"], f["line"], f["severity"]) for f in audit_json(tdir / "scripts.phtml", root)]
        unnonced = sorted(l for i, l, _ in ids if i == "unnonced_inline_script")
        check("unregistered scripts found (initA, tainted, direct), json/src/viewModels-registered ignored",
              unnonced == [3, 8, 11], ids)
        check("tainted variable flagged as nondeterministic", ("nondeterministic_script_hash", 8, "fatal") in ids, ids)
        check("direct uniqid() flagged as nondeterministic", ("nondeterministic_script_hash", 11, "fatal") in ids, ids)
        check("viewModels form = warning when HyvaCsp exists",
              any(i == "nonstandard_hyva_csp_call" and s == "warning" for i, _, s in ids), ids)

        root2 = make_root(tmp, "m2old", with_class=False)
        t2 = root2 / "app/code/Acme/Mod/view/frontend/templates"
        (t2 / "scripts.phtml").write_text(SCRIPTS_TPL)
        ids2 = [(f["id"], f["severity"]) for f in audit_json(t2 / "scripts.phtml", root2)]
        check("viewModels form = fatal when HyvaCsp is missing", ("nonstandard_hyva_csp_call", "fatal") in ids2, ids2)

        # ---- fixer
        rc, out = run("fix-inline-scripts.py", tdir / "scripts.phtml", "--dry-run", cwd=root)
        check("dry run leaves the file untouched", (tdir / "scripts.phtml").read_text() == SCRIPTS_TPL, out)
        rc, out = run("fix-inline-scripts.py", tdir / "scripts.phtml", cwd=root)
        fixed = (tdir / "scripts.phtml").read_text()
        blocks = re.split(r"</script>", fixed)
        after = lambda i: blocks[i + 1].lstrip()[:60]
        check("deterministic script registered", after(0).startswith("<?php $hyvaCsp->registerInlineScript()"), fixed)
        check("json script not registered", not after(1).startswith("<?php"), fixed)
        check("tainted script NOT registered", not after(2).startswith("<?php $hyvaCsp"), fixed)
        check("direct uniqid script NOT registered", not after(3).startswith("<?php $hyvaCsp"), fixed)
        check("fixer lists the scripts it refused", "Not registered" in out and ":8" in out and ":11" in out, out)
        rc, out = run("fix-inline-scripts.py", tdir / "scripts.phtml", cwd=root)
        check("fixer is idempotent", (tdir / "scripts.phtml").read_text() == fixed, out)

        rc, out = run("fix-inline-scripts.py", tdir / "scripts.phtml", "--normalize", cwd=root)
        norm = (tdir / "scripts.phtml").read_text()
        check("--normalize rewrites viewModels form to $hyvaCsp",
              "HyvaCsp::class" not in norm and norm.count("$hyvaCsp->registerInlineScript()") == 2, norm)
        rc, out = run("fix-inline-scripts.py", t2 / "scripts.phtml", "--normalize", cwd=root2)
        check("--normalize uses the isset() form when HyvaCsp is missing",
              "isset($hyvaCsp) && $hyvaCsp->registerInlineScript()" in (t2 / "scripts.phtml").read_text(), out)

        (tdir / "guard.phtml").write_text("<script>\n    var a = 1;\n</script>\n")
        run("fix-inline-scripts.py", tdir / "guard.phtml", "--guarded", cwd=root)
        check("--guarded inserts the isset() form",
              "isset($hyvaCsp) && $hyvaCsp->registerInlineScript()" in (tdir / "guard.phtml").read_text())

        (tdir / "inside.phtml").write_text("<script>\n    var a = 1;\n    <?php $hyvaCsp->registerInlineScript() ?>\n</script>\n")
        f_in = [f["id"] for f in audit_json(tdir / "inside.phtml", root)]
        check("registration inside <script> flagged", "misplaced_hyva_csp" in f_in, f_in)
        run("fix-inline-scripts.py", tdir / "inside.phtml", cwd=root)
        moved = (tdir / "inside.phtml").read_text()
        check("fixer moves it after </script>", moved.index("registerInlineScript") > moved.index("</script>"), moved)

        vend = root / "vendor/acme/x/view/frontend/templates"
        vend.mkdir(parents=True)
        (vend / "v.phtml").write_text("<script>var a=1;</script>\n")
        run("fix-inline-scripts.py", root / "vendor/acme", cwd=root)
        check("vendor/ is refused by default", "registerInlineScript" not in (vend / "v.phtml").read_text())

        # ---- suggest
        rc, out = run("suggest-refactor.py", tdir / "cases.phtml", cwd=root)
        check("suggest runs and covers new finding types",
              rc == 0 and "inline_event_handler" in out and "javascript_url" in out and "csp_negation" in out, out[-400:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{sum(RESULTS)}/{len(RESULTS)} passed")
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
