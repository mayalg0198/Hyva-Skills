#!/usr/bin/env python3
"""Offline regression suite for hyva-theme-upgrade (no Magento, no network, no browser).

Usage: python3 -I evals/run_evals.py
Builds a throw-away Magento-like tree (vendor default theme, a module registered at its package
root, a module registered under src/ via composer autoload.files, a child theme with overrides,
layouts and i18n), runs the run.sh commands against it and exits 1 on any failure. The project
tree must be left untouched by every read-only command.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
RESULTS = []
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def w(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def build(root: Path):
    reg = "<?php\n\\Magento\\Framework\\Component\\ComponentRegistrar::register(\\Magento\\Framework\\Component\\ComponentRegistrar::MODULE, '{}', __DIR__);\n"
    w(root / "composer.json", "{}")
    w(root / "bin/magento", "#!/bin/sh\n")
    # vendor default theme
    vt = root / "vendor/hyva-themes/magento2-default-theme"
    w(vt / "theme.xml", "<theme><title>Hyva Default</title><parent>Hyva/reset</parent></theme>")
    w(vt / "Magento_Catalog/templates/product/view/title.phtml", "<h1><?= $escaper->escapeHtml($block->getTitle()) ?></h1>\n")
    w(vt / "Magento_Catalog/templates/product/list.phtml", "<ul class=\"products\"></ul>\n")
    w(vt / "Magento_Theme/layout/default.xml",
      '<page><body><referenceContainer name="content"><block name="hyva.header" template="x.phtml"/></referenceContainer></body></page>')
    # module registered at package root
    w(root / "vendor/acme/module-root/registration.php", reg.format("Acme_Root"))
    w(root / "vendor/acme/module-root/view/frontend/layout/default.xml",
      '<page><body><referenceContainer name="content"><block name="acme.root.block"/></referenceContainer></body></page>')
    # module registered under src/ (autoload.files) — the case that used to be invisible
    w(root / "vendor/acme/module-src/src/registration.php", reg.format("Acme_Src"))
    w(root / "vendor/acme/module-src/src/view/frontend/layout/checkout_cart_index.xml",
      '<page><body><referenceContainer name="content"><block name="acme.src.freeshipping"/></referenceContainer></body></page>')
    w(root / "vendor/acme/module-src/src/view/frontend/templates/banner.phtml", "<div class=\"banner\"></div>\n")
    installed = {"packages": [
        {"name": "acme/module-root", "install-path": "../acme/module-root"},
        {"name": "acme/module-src", "install-path": "../acme/module-src",
         "autoload": {"files": ["src/registration.php"], "psr-4": {"Acme\\Src\\": "src"}}},
        {"name": "hyva-themes/magento2-default-theme", "version": "1.4.6",
         "install-path": "../hyva-themes/magento2-default-theme"},
    ]}
    w(root / "vendor/composer/installed.json", json.dumps(installed))
    # child theme
    ct = root / "app/design/frontend/Acme/shop"
    w(ct / "theme.xml", "<theme><title>Shop</title><parent>Hyva/default</parent></theme>")
    w(ct / "registration.php", "<?php\n")
    w(ct / "Magento_Catalog/templates/product/view/title.phtml",  # identical override
      "<h1><?= $escaper->escapeHtml($block->getTitle()) ?></h1>\n")
    w(ct / "Magento_Catalog/templates/product/list.phtml",  # modified + legacy patterns
      "<ul class=\"products text-fg bg-opacity-50\" x-spread=\"trigger\"></ul>\n"
      "<span><?= $escaper->escapeHtml(__('Add to cart')) ?></span>"
      "<input placeholder=\"<?= $escaper->escapeHtml(__('0123')) ?>\">\n")
    w(ct / "Acme_Src/templates/banner.phtml", "<div class=\"banner custom\"></div>\n")  # override of src/ module
    w(ct / "Magento_Theme/templates/custom-only.phtml", "<div><?= $escaper->escapeHtml(__('Already translated')) ?></div>\n")
    w(ct / "Magento_Checkout/layout/checkout_cart_index.xml",
      '<page><body><referenceBlock name="acme.src.freeshipping" remove="true"/>'
      '<referenceBlock name="acme.root.block" remove="true"/>'
      '<referenceBlock name="totally.missing.block" remove="true"/></body></page>')
    w(ct / "i18n/fr_FR.csv", '"Already translated","Déjà traduit"\n')
    w(ct / "web/tailwind/package.json", json.dumps({"devDependencies": {"tailwindcss": "^4.3.0"}}))


def run(*args, cwd, env=None):
    r = subprocess.run(["bash", str(SKILL / "run.sh"), *map(str, args)], cwd=cwd, capture_output=True, text=True,
                       env={**os.environ, **(env or {})}, timeout=300)
    return r.returncode, ANSI.sub("", r.stdout + r.stderr)


def snapshot(root: Path) -> dict:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}" + ("" if cond else f"\n     {str(detail)[-700:]}"))


def main():
    tmp = Path(tempfile.mkdtemp(prefix="hyva-upgrade-evals-"))
    try:
        root = tmp / "m2"
        build(root)
        cfg = tmp / "outside" / "upgrade.json"
        w(cfg, json.dumps({"from_version": "1.4.6", "to_version": "1.5.2", "themePath": "app/design/frontend/Acme/shop",
                           "vendorThemePath": "vendor/hyva-themes/magento2-default-theme", "locales": ["fr_FR"],
                           "cssFreeze": False, "strictCsp": False}))
        before = snapshot(root)

        rc, out = run("doctor", "--config", cfg, cwd=root)
        check("doctor honours --config (file outside the project)", "Configured (1.4.6 → 1.5.2)" in out, out)
        check("doctor finds the child theme", "app/design/frontend/Acme/shop" in out, out)

        rc, out = run("layout", "--config", cfg, cwd=root)
        check("layout: block declared by a src/ module is not an orphan", "acme.src.freeshipping" not in out, out)
        check("layout: block declared by a root module is not an orphan", "acme.root.block" not in out, out)
        check("layout: a truly missing block is reported", "totally.missing.block" in out, out)

        rc, out = run("vendor", "--config", cfg, cwd=root)
        check("vendor: identical override detected", re.search(r"IDENTICAL\]\s+Magento_Catalog/templates/product/view/title\.phtml", out), out)
        check("vendor: modified override detected", re.search(r"MODIFIED\]\s+Magento_Catalog/templates/product/list\.phtml", out), out)
        check("vendor: override of a src/ module template is matched, labelled with its package",
              re.search(r"Acme_Src/templates/banner\.phtml \(module-src\)", out), out)
        check("vendor: custom-only template counted", re.search(r"Custom-only \(no vendor\)\s*:\s*1\b", out), out)

        rc, out = run("diff", "Magento_Catalog/templates/product/view/title.phtml", "--config", cfg, cwd=root)
        check("diff: identical override exits 0", rc == 0, out)
        rc, out = run("diff", "Magento_Catalog/templates/product/list.phtml", "--config", cfg, cwd=root)
        check("diff: modified override exits 1 and shows the change", rc == 1 and "x-spread" in out, out)

        rc, out = run("i18n", "--locale", "fr_FR", "--config", cfg, cwd=root)
        check("i18n: untranslated phrase reported", "Add to cart" in out, out)
        check("i18n: translated phrase not reported", "Already translated\"" not in out.split("Missing from")[-1], out)
        check("i18n: letter-less placeholder skipped and counted", "'0123'" in out and "1 without letters skipped" in out, out)

        rc, out = run("audit", "--config", cfg, cwd=root)
        check("audit: x-spread flagged", "x-spread" in out, out)
        check("audit: *-opacity-* flagged", "opacity" in out.lower(), out)
        check("audit: -fg token flagged when crossing 1.5.2", "text-fg" in out or "-fg" in out, out)
        check("audit exits non-zero on fatal findings", rc != 0, out)

        rc, out = run("changelog", "--config", cfg, cwd=root)
        check("changelog prints the 1.4.6 → 1.5.2 range", rc == 0 and "1.5" in out, out[-500:])

        check("read-only commands left the project untouched", snapshot(root) == before)

        rc, out = run("nonsense", cwd=root)
        check("unknown command exits 2 with help", rc == 2 and "Commands" in out, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{sum(RESULTS)}/{len(RESULTS)} passed")
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
