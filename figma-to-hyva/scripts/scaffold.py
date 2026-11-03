#!/usr/bin/env python3
"""Scaffold a Hyvä CMS widget module or a theme template from a small JSON spec.

Usage:
  scaffold.py SPEC.json [--write]          # default: dry run, prints the file list

widget spec:
  {"type": "widget", "vendor": "Sutunam", "module": "PromoBanner", "name": "promo_banner",
   "title": "Promo banner", "alpine": false,
   "params": [{"name": "title", "type": "text", "label": "Title"},
              {"name": "show_cta", "type": "boolean", "label": "Show button", "default": 1},
              {"name": "limit", "type": "number", "label": "Items", "default": 4, "min": 1, "max": 12}]}
template spec:
  {"type": "template", "path": "app/design/frontend/V/T/Magento_Catalog/templates/x.phtml", "alpine": false}

Generates registration.php, etc/module.xml, etc/widget.xml, Block/Widget/<Class>.php (typed, strict,
boolean/number params handled per PHP-4/PHP-5), view/frontend/templates/widget/<name>.phtml
(escaped, translated, optional Alpine component registered for CSP when the project needs it),
i18n/fr_FR.csv. The copyright header is taken from CLAUDE.md when it shows one. Never overwrites a file.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402


def header(root: Path) -> str:
    m = re.search(r"```php\s*\n<\?php\s*\n(/\*\*.*?\*/)\s*\n", _lib.read(root / "CLAUDE.md"), re.S)
    return f"<?php\n{m.group(1)}\n\ndeclare(strict_types=1);\n" if m else "<?php\n\ndeclare(strict_types=1);\n"


def camel(name: str) -> str:
    return "".join(p.capitalize() for p in re.split(r"[_\-\s]+", name))


def alpine_script(comp: str, strict: bool, hyvacsp: bool) -> str:
    reg = "<?php $hyvaCsp->registerInlineScript() ?>" if hyvacsp else \
        "<?php isset($hyvaCsp) && $hyvaCsp->registerInlineScript() ?>"
    return f"""<script>
    function {comp}() {{
        return {{
            open: false,
            init() {{
                this.items = Number(this.$el.dataset.items || 0);
            }},
            toggle() {{
                this.open = !this.open;
            }},
            get isClosed() {{
                return !this.open;
            }},
        }};
    }}
    window.addEventListener('alpine:init', () => Alpine.data('{comp}', {comp}), {{once: true}});
</script>
{reg}
"""


def widget_files(spec, root, info):
    v, mod, name = spec["vendor"], spec["module"], spec["name"]
    cls = camel(name)
    base = root / "app/code" / v / mod
    hdr = header(root)
    params = spec.get("params", [])
    ns = f"{v}\\{mod}"
    getters, wparams, tvars = [], [], []
    for p in params:
        pn, t = p["name"], p.get("type", "text")
        fn = "get" + camel(pn)
        label = p.get("label", pn)
        if t == "boolean":
            default = bool(p.get("default", 1))
            body = ("return !$this->hasData('%s') || (bool) $this->getData('%s');" % (pn, pn)) if default \
                else "return (bool) $this->getData('%s');" % pn
            getters.append(f"    public function {fn}(): bool\n    {{\n        {body}\n    }}\n")
            wparams.append(f'        <parameter name="{pn}" xsi:type="select" source_model="Magento\\Config\\Model\\Config\\Source\\Yesno" visible="true">\n'
                           f'            <label translate="true">{label}</label>\n            <description translate="true">{label}</description>\n'
                           f'            <value>{1 if default else 0}</value>\n        </parameter>')
            tvars.append(f"$show{camel(pn)} = $block->{fn}();")
        elif t == "number":
            lo, hi, d = p.get("min", 1), p.get("max", 50), p.get("default", 4)
            getters.append(f"    public function {fn}(): int\n    {{\n        $value = (int) $this->getData('{pn}');\n\n"
                           f"        return max({lo}, min({hi}, $value ?: {d}));\n    }}\n")
            wparams.append(f'        <parameter name="{pn}" xsi:type="text" visible="true">\n'
                           f'            <label translate="true">{label}</label>\n            <description translate="true">{lo}-{hi}</description>\n'
                           f'            <value>{d}</value>\n        </parameter>')
            tvars.append(f"$limit{camel(pn)} = $block->{fn}();")
        else:
            getters.append(f"    public function {fn}(): string\n    {{\n        return trim((string) $this->getData('{pn}'));\n    }}\n")
            wparams.append(f'        <parameter name="{pn}" xsi:type="text" visible="true">\n'
                           f'            <label translate="true">{label}</label>\n        </parameter>')
            tvars.append(f"${camel(pn)[0].lower() + camel(pn)[1:]} = $block->{fn}();")
    files = {}
    files[base / "registration.php"] = f"{hdr}\nuse Magento\\Framework\\Component\\ComponentRegistrar;\n\nComponentRegistrar::register(ComponentRegistrar::MODULE, '{v}_{mod}', __DIR__);\n"
    files[base / "etc/module.xml"] = f'<?xml version="1.0"?>\n<config xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="urn:magento:framework:Module/etc/module.xsd">\n    <module name="{v}_{mod}"/>\n</config>\n'
    files[base / "etc/widget.xml"] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<widgets xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="urn:magento:module:Magento_Widget:etc/widget.xsd">\n'
        f'    <widget id="{v.lower()}_{name}" class="{ns}\\Block\\Widget\\{cls}">\n        <label translate="true">{spec.get("title", cls)}</label>\n'
        '        <parameters>\n' + "\n".join(wparams) + '\n        </parameters>\n    </widget>\n</widgets>\n')
    files[base / f"Block/Widget/{cls}.php"] = (
        f"{hdr}\nnamespace {ns}\\Block\\Widget;\n\nuse Magento\\Framework\\View\\Element\\Template;\nuse Magento\\Widget\\Block\\BlockInterface;\n\n"
        f"class {cls} extends Template implements BlockInterface\n{{\n    protected $_template = '{v}_{mod}::widget/{name}.phtml';\n\n" + "\n".join(getters) + "}\n")
    comp = "init" + cls
    tpl = ["<?php", "/**", f" * @var \\{ns}\\Block\\Widget\\{cls} $block", " * @var \\Magento\\Framework\\Escaper $escaper", " */", "",
           "declare(strict_types=1);", "", *tvars, "?>"]
    body = f'<section class="{name.replace("_", "-")} container py-8"{" x-data=\"" + comp + "\" x-cloak" if spec.get("alpine") else ""}>\n'
    body += f"    <h2 class=\"title-2\"><?= $escaper->escapeHtml(__('{spec.get('title', cls)}')) ?></h2>\n    <!-- TODO: markup from Figma -->\n</section>\n"
    if spec.get("alpine"):
        body += alpine_script(comp, info["csp_mode"] == "strict", info["hyvacsp"])
    files[base / f"view/frontend/templates/widget/{name}.phtml"] = "\n".join(tpl) + "\n\n" + body
    files[base / "i18n/fr_FR.csv"] = f'"{spec.get("title", cls)}","{spec.get("title", cls)}"\n'
    return files


def template_files(spec, root, info):
    path = root / spec["path"]
    comp = "init" + camel(path.stem)
    tpl = ["<?php", "/**", " * @var \\Magento\\Framework\\View\\Element\\Template $block", " * @var \\Magento\\Framework\\Escaper $escaper", " */", "",
           "declare(strict_types=1);", "?>", "",
           f'<section class="container py-8"{" x-data=\"" + comp + "\" x-cloak" if spec.get("alpine") else ""}>', "    <!-- TODO: markup from Figma -->", "</section>"]
    out = "\n".join(tpl) + "\n"
    if spec.get("alpine"):
        out += alpine_script(comp, info["csp_mode"] == "strict", info["hyvacsp"])
    return {path: out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    spec = json.loads(_lib.read(a.spec))
    root = _lib.find_root()
    info = _lib.project(root)
    files = widget_files(spec, root, info) if spec.get("type", "widget") == "widget" else template_files(spec, root, info)
    clash = [p for p in files if p.exists()]
    if clash:
        print("REFUSED, would overwrite: " + ", ".join(str(p.relative_to(root)) for p in clash))
        sys.exit(1)
    for p, content in files.items():
        print(f"{'WRITE' if a.write else 'would write'} {p.relative_to(root)} ({len(content.splitlines())} lines)")
        if a.write:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
    if not a.write:
        print("dry run — re-run with --write. After writing: setup:upgrade + di:compile for a new module.")


if __name__ == "__main__":
    main()
