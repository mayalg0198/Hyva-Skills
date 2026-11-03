#!/usr/bin/env python3
"""Read-only stack detection for a Magento 2 + Hyvä project (cached).

Usage: python3 -I detect.py [project_root] [--brief|--json] [--refresh] [--theme VENDOR/THEME]

Default prints the full report; --brief prints ~15 lines (what a task needs); --json prints the
machine form other scripts read. Result is cached in <root>/var/figma-to-hyva/project.json and
invalidated when composer.lock, theme.xml, Tailwind config/package.json, Makefile or CLAUDE.md change.
Never reads secrets (env.php, auth.json, .env contents beyond TRAEFIK_DOMAIN).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

MAX_TOKENS = 40


def figma_token_state() -> str:
    return "set" if (os.environ.get("FR_FIGMA_TOKEN") or os.environ.get("FIGMA_TOKEN")) else "unset"


def brief(i: dict) -> None:
    t = i["themes"].get(i["target_theme"] or "", {})
    tw = t.get("tailwind", {})
    c = i["cmds"]
    reg = f"{i['scripts_registered']}/{i['scripts_total']}"
    print(f"root: {i['root']}")
    print(f"magento {i['magento']} | hyva {', '.join(f'{k} {v}' for k, v in i['hyva'].items() if k in ('magento2-theme-module', 'magento2-default-theme', 'magento2-default-theme-csp', 'magento2-hyva-checkout'))}")
    print(f"theme: {i['target_theme']} chain {' -> '.join(t.get('chain', []))} | other hyva themes: "
          f"{', '.join(k for k, v in i['themes'].items() if v['hyva'] and k != i['target_theme']) or '-'}")
    print(f"MODE: csp={i['csp_mode']} (hyvacsp viewmodel={'yes' if i['hyvacsp'] else 'NO'}, registered scripts {reg}) | tailwind=TW{i['tw']} ({tw.get('tailwindcss', '?')})")
    print(f"screens: {tw.get('screens', '?')}")
    print(f"tokens ({len(tw.get('token_classes', []))}): {' '.join(tw.get('token_classes', [])[:MAX_TOKENS])}")
    print(f"i18n: {', '.join(t.get('i18n', [])) or '-'} | assets: {', '.join(t.get('asset_dirs', [])) or '-'}")
    print(f"env: {i['env']['tool']} {i['env']['url']} | gate: {i['gate']} | figma token: {figma_token_state()}")
    for k in ("build", "generate", "flush", "di", "css_out"):
        if k in c:
            print(f"{k}: {c[k]}")
    print(f"guidance (read, they override generic rules): {', '.join(i['guidance']) or '-'}")


def full(i: dict) -> None:
    print("# figma-to-hyva project detection")
    print(f"root: {i['root']}\nmagento: {i['magento']}")
    print("hyva: " + (", ".join(f"{k} {v}" for k, v in i['hyva'].items()) or "none"))
    print(f"HyvaCsp viewmodel: {'yes ($hyvaCsp available)' if i['hyvacsp'] else 'NO — never require HyvaCsp::class'}")
    print(f"alpine builds shipped: {', '.join(i['alpine']) or '?'}")
    print(f"csp mode: {i['csp_mode']} (registered scripts {i['scripts_registered']}/{i['scripts_total']}) | tailwind major: {i['tw']}")
    print("\n## Themes")
    for code, t in i["themes"].items():
        flag = ("HYVA" + (" CSP" if t["csp"] else "")) if t["hyva"] else "luma/other"
        mark = " <- target" if code == i["target_theme"] else ""
        print(f"- {code} [{flag}] {' -> '.join(t['chain'])}  {t['dir']}{mark}")
        if t["hyva"]:
            tw = t.get("tailwind", {})
            print(f"  i18n: {', '.join(t['i18n']) or '-'} | assets: {', '.join(t['asset_dirs']) or '-'}")
            if tw:
                print(f"  tailwind {tw['tailwindcss']} config: {', '.join(tw['config'])} scripts: {', '.join(tw['scripts'])}")
                print(f"  screens: {tw['screens']}")
                print(f"  tokens ({len(tw['token_classes'])}): {' '.join(tw['token_classes'][:MAX_TOKENS])}")
                print(f"  theme vars: {len(tw['theme_vars'])}, css files: {tw['css_files']}")
    print("\n## Environment")
    for k, v in i["env"].items():
        print(f"{k}: {v}")
    for k, v in i["cmds"].items():
        print(f"cmd {k}: {v}")
    print(f"gate: {i['gate']}\nproject skills: {', '.join(i['project_skills']) or '-'}")
    print(f"guidance: {', '.join(i['guidance']) or '-'}")


def main() -> None:
    args = [a for a in sys.argv[1:]]
    refresh = "--refresh" in args
    theme = args[args.index("--theme") + 1] if "--theme" in args else None
    pos = [a for a in args if not a.startswith("--") and a != theme]
    root = _lib.find_root(pos[0] if pos else None)
    if not (root / "app").is_dir():
        print("NOT A MAGENTO ROOT — run from the project root or pass it as argument.")
        sys.exit(1)
    info = _lib.project(root, refresh=refresh, theme=theme)
    if "--json" in args:
        info.pop("sig", None)
        print(json.dumps(info, indent=1))
    elif "--brief" in args:
        brief(info)
    else:
        full(info)


if __name__ == "__main__":
    main()
