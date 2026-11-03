#!/usr/bin/env python3
"""Offline regression suite for the figma-to-hyva scripts (no Figma, no Magento, no network).

Usage: python3 -I run_evals.py
Builds a throw-away Magento-like tree in a temp dir, runs every script against known fixtures and
checks the expected output. Prints PASS/FAIL per case and exits 1 on any failure. Run it after
editing any script (and before trusting a change to the lint rules).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
RESULTS = []


def sh(script, *args, cwd=None):
    r = subprocess.run([sys.executable, "-I", str(SCRIPTS / script), *map(str, args)], cwd=cwd, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr)


def check(name, cond, detail=""):
    RESULTS.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}" + ("" if cond else f"\n     {detail[:400]}"))


BAD_STRICT = """<?php
/** @var \\Magento\\Framework\\Escaper $escaper */
declare(strict_types=1);
$cols = 3;
?>
<div x-data="{ open: false }" class="<?= 'grid-cols-' . $cols ?> grid">
    <button @click="open = !open" x-show="!open">Open</button>
    <img src="<?= $block->getViewFileUrl('images/a.svg') ?>">
    <a href="https://x.test" target="_blank">out</a>
</div>
<script>
    window.x = '<?= $block->getUrl('a/b') ?>';
</script>
"""
BAD_TW3 = """<div class="mt-12.5 hidden! md:right-3.75 p-4"></div>"""
GOOD = """<?php
/** @var \\Magento\\Framework\\Escaper $escaper */
declare(strict_types=1);
?>
<div x-data="initGood" x-cloak data-url="<?= $escaper->escapeUrl($block->getUrl('a/b')) ?>" class="grid grid-cols-2 p-4">
    <button @click="toggle" x-show="isClosed" type="button"><?= $escaper->escapeHtml(__('Open')) ?></button>
    <img src="<?= $escaper->escapeUrl($block->getViewFileUrl('images/a.svg')) ?>" alt="" aria-hidden="true">
</div>
<script>
    function initGood() { return { open: false, toggle() { this.open = !this.open; }, get isClosed() { return !this.open; } }; }
    window.addEventListener('alpine:init', () => Alpine.data('initGood', initGood), {once: true});
</script>
<?php $hyvaCsp->registerInlineScript() ?>
"""
TYPO_CSS = """@layer components {
  .title-1 { font-size: 24px; line-height: 28px; font-weight: 700; }
  .title-2 { @apply text-xl font-semibold md:text-2xl; }
  @media (min-width: 1280px) { .title-1 { font-size: 40px; line-height: 44px; } }
}
@theme { --color-primary: #e84127; --color-brand: #443244; }
"""
SAMPLE_TSX = """const imgHero = "https://www.figma.com/api/mcp/asset/abc";
export default function C() { return (
<div className="flex gap-[16px] p-[24px]" data-name="Card" data-node-id="1:2">
<img alt="" src={imgHero} data-name="Hero" data-node-id="1:3" />
<p className="font-['Inter:Bold',sans-serif] text-[32px] leading-[40px] text-[#e84127]" data-name="Title" data-node-id="1:4">Bonjour Lyon</p>
</div>); }"""


def main():
    tmp = Path(tempfile.mkdtemp(prefix="f2h-evals-"))
    try:
        # ---- lint
        (tmp / "bad.phtml").write_text(BAD_STRICT)
        (tmp / "tw3.phtml").write_text(BAD_TW3)
        (tmp / "good.phtml").write_text(GOOD)
        rc, out = sh("lint_phtml.py", "--all-lines", "--csp", "strict", "--tw", "4", "--hyvacsp", "yes", tmp / "bad.phtml", cwd=tmp)
        for rule in ("ALP-1", "ALP-2", "ALP-3", "TPL-2", "A11Y-3", "A11Y-5", "TW-1"):
            check(f"lint strict flags {rule}", rule in out, out)
        check("lint strict exits 1", rc == 1)
        rc, out = sh("lint_phtml.py", "--all-lines", "--csp", "ready", "--tw", "3", "--hyvacsp", "no", tmp / "tw3.phtml", cwd=tmp)
        check("lint TW3 flags TW-3 and TW-4", "TW-3" in out and "TW-4" in out, out)
        rc, out = sh("lint_phtml.py", "--all-lines", "--csp", "strict", "--tw", "4", "--hyvacsp", "yes", tmp / "good.phtml", cwd=tmp)
        check("lint clean template passes", rc == 0 and "0 error(s), 0 warning(s)" in out, out)

        # ---- tokens
        tw = tmp / "tw"
        (tw / "components").mkdir(parents=True)
        (tw / "components/typography.css").write_text(TYPO_CSS)
        rc, out = sh("tokens.py", "text", "--tailwind-dir", tw, "--size", "40", "--lh", "44", "--weight", "700", "--bp", "xl", cwd=tmp)
        check("tokens text exact at xl via media query", "EXACT .title-1" in out, out)
        rc, out = sh("tokens.py", "text", "--tailwind-dir", tw, "--size", "24", "--lh", "28", "--weight", "700", "--bp", "base", cwd=tmp)
        check("tokens text exact at base", "EXACT .title-1" in out, out)
        rc, out = sh("tokens.py", "text", "--tailwind-dir", tw, "--size", "24", "--lh", "32", "--weight", "600", "--bp", "md", cwd=tmp)
        check("tokens @apply md:text-2xl resolves", "EXACT .title-2" in out, out)
        rc, out = sh("tokens.py", "text", "--tailwind-dir", tw, "--size", "33", "--bp", "xl", cwd=tmp)
        check("tokens reports NO EXACT with closest", "NO EXACT" in out, out)
        rc, out = sh("tokens.py", "color", "--tailwind-dir", tw, "--hex", "#E84127", cwd=tmp)
        check("tokens color exact", "EXACT primary" in out, out)
        rc, out = sh("tokens.py", "color", "--tailwind-dir", tw, "--hex", "#ee5a40", cwd=tmp)
        check("tokens color nearest", "nearest primary" in out, out)
        rc, o3 = sh("tokens.py", "space", "--tailwind-dir", tw, "--tw", "3", "--px", "50", "--prop", "mt", cwd=tmp)
        rc, o4 = sh("tokens.py", "space", "--tailwind-dir", tw, "--tw", "4", "--px", "50", "--prop", "mt", cwd=tmp)
        check("space TW3 uses arbitrary, TW4 uses scale", "mt-[50px]" in o3 and "mt-12.5" in o4, o3 + o4)

        # ---- condense + batch
        (tmp / "s.tsx").write_text(SAMPLE_TSX)
        rc, out = sh("condense.py", "tsx", tmp / "s.tsx", "--out", tmp / "spec", cwd=tmp)
        spec = json.loads((tmp / "spec.json").read_text())
        t = spec["typography"][0] if spec["typography"] else {}
        check("condense extracts typography/colors/assets",
              (t.get("size"), t.get("lh"), t.get("weight")) == (32, 40, 700) and "#e84127" in spec["colors"] and spec["assets"], out)
        rest = {"nodes": {"1:2": {"document": {"id": "1:2", "name": "Card", "type": "FRAME", "layoutMode": "VERTICAL", "itemSpacing": 16,
                "absoluteBoundingBox": {"width": 375, "height": 200}, "fills": [{"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1}}],
                "children": [{"id": "1:3", "name": "T", "type": "TEXT", "characters": "Salut", "fills": [{"type": "SOLID", "color": {"r": 0.91, "g": 0.255, "b": 0.153}}],
                              "style": {"fontSize": 24, "lineHeightPx": 28, "fontWeight": 700, "fontFamily": "Inter"}}]}}}}
        (tmp / "rest.json").write_text(json.dumps(rest))
        rc, out = sh("condense.py", "rest", tmp / "rest.json", "--out", tmp / "rspec", cwd=tmp)
        rs = json.loads((tmp / "rspec.json").read_text())
        check("condense rest extracts text style", rs["typography"] and rs["typography"][0]["size"] == 24 and "#ffffff" in rs["colors"], out)
        (tmp / "b.json").write_text(json.dumps({"typography": [{"size": 24, "lh": 28, "weight": 700, "text": "x"}], "colors": ["#e84127"], "spacing": [16]}))
        rc, out = sh("tokens.py", "batch", tmp / "b.json", "--tailwind-dir", tw, "--bp", "base", "--tw", "3", cwd=tmp)
        check("tokens batch runs", "EXACT .title-1" in out and "EXACT primary" in out and "16px->4" in out, out)

        # ---- fake Magento root for project-aware scripts
        root = tmp / "m2"
        (root / "app/etc").mkdir(parents=True)
        (root / "app/etc/di.xml").write_text("<config/>")
        th = root / "app/design/frontend/Acme/shop"
        (th / "i18n").mkdir(parents=True)
        (th / "theme.xml").write_text("<theme><title>x</title><parent>Hyva/default</parent></theme>")
        (th / "i18n/fr_FR.csv").write_text('"Existing","Existant"\n')
        (th / "Magento_Catalog/templates").mkdir(parents=True)
        (th / "Magento_Catalog/templates/x.phtml").write_text("<h2><?= $escaper->escapeHtml(__('Existing')) ?></h2><p><?= $escaper->escapeHtml(__('Hello %1', $n)) ?></p>")
        (root / "CLAUDE.md").write_text("```php\n<?php\n/**\n * @author Acme\n */\n\ndeclare(strict_types=1);\n```\n")
        rc, out = sh("detect.py", root, "--brief", cwd=root)
        check("detect brief on fake root", "theme: Acme/shop" in out and "MODE:" in out, out)
        rc, out = sh("i18n_sync.py", th / "Magento_Catalog/templates/x.phtml", cwd=root)
        check("i18n reports missing string", rc == 1 and "Hello %1" in out and "Existing" not in out.split("missing")[1], out)
        (tmp / "tr.json").write_text(json.dumps({"Hello %1": {"fr_FR": "Bonjour %1"}}))
        rc, out = sh("i18n_sync.py", th / "Magento_Catalog/templates/x.phtml", "--write", "--translations", tmp / "tr.json", cwd=root)
        check("i18n writes translated row", '"Hello %1","Bonjour %1"' in (th / "i18n/fr_FR.csv").read_text(), out)
        rc, out = sh("i18n_sync.py", th / "Magento_Catalog/templates/x.phtml", cwd=root)
        check("i18n clean after write", rc == 0, out)

        # ---- scaffold + lint of generated code
        spec = {"type": "widget", "vendor": "Acme", "module": "Promo", "name": "promo_banner", "title": "Promo banner", "alpine": True,
                "params": [{"name": "title", "type": "text", "label": "Title"}, {"name": "show_cta", "type": "boolean", "label": "CTA", "default": 1},
                           {"name": "limit", "type": "number", "label": "Items", "default": 4, "min": 1, "max": 12}]}
        (tmp / "w.json").write_text(json.dumps(spec))
        rc, out = sh("scaffold.py", tmp / "w.json", "--write", cwd=root)
        tpl = root / "app/code/Acme/Promo/view/frontend/templates/widget/promo_banner.phtml"
        blk = root / "app/code/Acme/Promo/Block/Widget/PromoBanner.php"
        check("scaffold writes widget module", rc == 0 and tpl.exists() and blk.exists(), out)
        check("scaffold uses CLAUDE.md header", "@author Acme" in blk.read_text())
        rc, out = sh("lint_phtml.py", "--all-lines", "--csp", "strict", "--tw", "4", "--hyvacsp", "yes", tpl, blk, cwd=root)
        check("scaffolded files pass strict lint", rc == 0, out)
        rc, out = sh("scaffold.py", tmp / "w.json", "--write", cwd=root)
        check("scaffold refuses to overwrite", rc == 1 and "REFUSED" in out, out)
        if shutil.which("php"):
            r = subprocess.run(["php", "-l", str(blk)], capture_output=True, text=True)
            check("scaffolded PHP lints", r.returncode == 0, r.stdout + r.stderr)

        # ---- class check against built css
        (root / ".govard.yml").write_text("domain: acme.test\n")
        tw_dir = th / "web/tailwind"
        (tw_dir).mkdir(parents=True)
        (tw_dir / "package.json").write_text(json.dumps({"scripts": {"build-prod": "x"}, "devDependencies": {"tailwindcss": "^3.2.7"}}))
        (th / "web/css").mkdir(parents=True)
        (th / "web/css/styles.css").write_text(".flex{display:flex}.md\\:mt-4{margin-top:1rem}.p-4{padding:1rem}")
        cls = th / "Magento_Catalog/templates/cls.phtml"
        cls.write_text('<div class="flex md:mt-4 p-4 product-info mt-12.5 grid-cols-<?= $n ?> text-[13px]" :class="arrowClass"></div>')
        rc, out = sh("build_verify.py", "--check-only", "--theme", "Acme/shop", cls, cwd=root)
        check("class check flags missing utilities only", rc == 1 and "mt-12.5" in out and "text-[13px]" in out
              and "product-info" not in out and "arrowClass" not in out and "md:mt-4" not in out.split("MISSING")[1], out)
        rc, out = sh("build_verify.py", "--dry-run", "--theme", "Acme/shop", cls, cwd=root)
        check("dry run shows govard build + flush", "govard tool npm --prefix" in out and "cache:flush" in out, out)

        # ---- cache
        rc, out = sh("cache.py", "get", "FK", "1:2", "--version", "v1", cwd=root)
        check("cache MISS", rc == 3, out)
        rc, out = sh("cache.py", "put", "FK", "1:2", "--version", "v1", "--prefix", tmp / "spec", cwd=root)
        rc, out = sh("cache.py", "get", "FK", "1:2", "--version", "v1", cwd=root)
        check("cache FRESH", rc == 0 and "FRESH" in out, out)
        rc, out = sh("cache.py", "get", "FK", "1:2", "--version", "v2", cwd=root)
        check("cache STALE on version change", rc == 2, out)

        # ---- rules + style compare + assets
        rc, out = sh("rules.py", "--csp", "strict", "--tw", "4", "--hyvacsp", "yes", cwd=root)
        rc2, out2 = sh("rules.py", "--csp", "ready", "--tw", "3", "--hyvacsp", "no", cwd=root)
        check("rules filter differs per project", "hidden!" in out and "!hidden" in out2 and "<!--if" not in out + out2, "")
        (tmp / "c.json").write_text(json.dumps({"viewport": 1440, "items": [{"text": "Bonjour Lyon", "tag": "p", "size": 30, "lh": 40, "weight": 700, "color": "#e84127"}]}))
        rc, out = sh("style_compare.py", tmp / "spec.json", tmp / "c.json", cwd=root)
        check("style_compare flags font-size", rc == 1 and "font-size 30" in out, out)
        (tmp / "icon.svg").write_text('<svg width="24" height="24" viewBox="0 0 24 24"><path d="M0 0h24v24H0z"/></svg>')
        rc, out = sh("assets.py", "place", tmp / "icon.svg", "--dry-run", cwd=root)
        check("assets validates svg + reports root size", "width=24 height=24" in out, out)
        (tmp / "empty.png").write_bytes(b"")
        rc, out = sh("assets.py", "place", tmp / "empty.png", cwd=root)
        check("assets rejects empty file", rc == 1 and "FAIL" in out, out)
        try:
            import PIL  # noqa: F401
            from PIL import Image
            Image.new("RGB", (100, 100), "white").save(tmp / "a.png")
            im = Image.new("RGB", (100, 100), "white")
            for x in range(40):
                for y in range(40):
                    im.putpixel((x, y), (255, 0, 0))
            im.save(tmp / "b.png")
            rc, out = sh("pixel_diff.py", tmp / "a.png", tmp / "b.png", "--out", tmp / "d.png", cwd=root)
            check("pixel_diff detects change", rc == 1 and "16.00%" in out, out)
        except ImportError:
            print("SKIP pixel_diff (Pillow missing)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{sum(RESULTS)}/{len(RESULTS)} passed")
    sys.exit(0 if all(RESULTS) else 1)


if __name__ == "__main__":
    main()
