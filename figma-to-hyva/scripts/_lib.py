"""Shared helpers for the figma-to-hyva scripts.

Scripts run with `python3 -I`, which drops the script dir from sys.path, so each one does
`sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))` before `import _lib`.
Everything here is read-only except the project cache in <root>/var/figma-to-hyva/.
"""
import json
import os
import re
import subprocess
import time
from pathlib import Path

CACHE_DIR = "var/figma-to-hyva"
CACHE_TTL = 24 * 3600
MAX_CSS_BYTES = 300_000  # skip compiled outputs when mining tokens


def find_root(start=None) -> Path:
    p = Path(start or os.getcwd()).resolve()
    for q in [p, *p.parents]:
        if (q / "bin" / "magento").exists() or (q / "app" / "etc" / "di.xml").exists():
            return q
    return p


def read(path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def cache_dir(root: Path) -> Path:
    d = root / CACHE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def git_changed(root: Path, base: str = "HEAD", exts=(".phtml", ".php", ".xml", ".js", ".css", ".json", ".csv")):
    """Changed + untracked files, restricted to app/ (never pub/, vendor/, var/)."""
    out = set()
    for args in (["diff", "--name-only", "--diff-filter=ACMR", base, "--"],
                 ["ls-files", "--others", "--exclude-standard", "--", "app"]):
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
        if r.returncode == 0:
            out.update(line for line in r.stdout.splitlines() if line)
    return sorted(root / f for f in out if f.startswith("app/") and f.endswith(exts) and (root / f).is_file())


# --------------------------------------------------------------------------- detection

def lock_packages(root: Path) -> dict:
    try:
        data = json.loads(read(root / "composer.lock") or "{}")
    except ValueError:
        return {}
    return {p.get("name", ""): p.get("version", "")
            for p in data.get("packages", []) + data.get("packages-dev", [])}


def _themes(root: Path) -> dict:
    out = {}
    for xml in sorted((root / "app/design/frontend").glob("*/*/theme.xml")):
        code = f"{xml.parent.parent.name}/{xml.parent.name}"
        m = re.search(r"<parent>\s*([^<\s]+)\s*</parent>", read(xml))
        out[code] = {"dir": xml.parent, "parent": m.group(1) if m else None}
    return out


def _chain(code, themes) -> list:
    chain, seen = [], set()
    while code and code not in seen:
        seen.add(code)
        chain.append(code)
        code = themes.get(code, {}).get("parent")
        if code and code not in themes:
            chain.append(code)
            break
    return chain


def css_files_of(tw: Path) -> list:
    return sorted(p for p in tw.rglob("*.css")
                  if "node_modules" not in p.parts and "output" not in p.name
                  and p.stat().st_size < MAX_CSS_BYTES)


def _tailwind(theme_dir: Path, root: Path) -> dict:
    tw = theme_dir / "web" / "tailwind"
    if not tw.is_dir():
        return {}
    try:
        pkg = json.loads(read(tw / "package.json") or "{}")
    except ValueError:
        pkg = {}
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    ver = deps.get("tailwindcss", "?")
    m = re.search(r"(\d+)", ver)
    info = {"dir": str(tw.relative_to(root)), "tailwindcss": ver, "major": int(m.group(1)) if m else 0,
            "scripts": sorted(pkg.get("scripts", {}).keys()),
            "config": [f for f in ("tailwind.config.js", "hyva.config.json", "tailwind-source.css",
                                   "postcss.config.js") if (tw / f).exists()]}
    files = css_files_of(tw)
    classes, utilities, theme_vars = set(), set(), set()
    noise = re.compile(r"^text-(xs|sm|base|lg|\d?xl|left|right|center|justify|white|black|[a-z]+-\d{2,3})$")
    for p in files:
        text = read(p)
        utilities.update(re.findall(r"@utility\s+([a-z][\w-]*)", text))
        classes.update(c for c in re.findall(
            r"(?m)^\s*\.((?:title|heading|h[1-6]|txt|text|body|label|overline|caption|button|btn)[\w-]*)\s*[,{]", text)
            if not noise.match(c))
        theme_vars.update(re.findall(r"(--(?:color|text|font|spacing|radius|breakpoint)-[\w-]+)\s*:", text))
    info["css_files"] = len(files)
    info["token_classes"] = sorted(classes | utilities)
    info["theme_vars"] = sorted(theme_vars)
    cfg = re.sub(r"//[^\n]*|/\*.*?\*/", "", read(tw / "tailwind.config.js"), flags=re.S)
    screens = ""
    m = re.search(r"screens\s*:\s*\{([^}]*)\}", cfg)
    if m:
        screens = " ".join(f"{k}={v}" for k, v in re.findall(r"['\"]?([\w-]+)['\"]?\s*:\s*['\"]([^'\"]+)['\"]", m.group(1)))
    for p in files:
        for k, v in re.findall(r"--breakpoint-([\w-]+)\s*:\s*([^;]+);", read(p)):
            screens += f" {k}={v.strip()}"
    info["screens"] = screens.strip() or "sm=640 md=768 lg=1024 xl=1280 2xl=1536 (Tailwind defaults)"
    return info


def _env(root: Path) -> dict:
    gy = read(root / ".govard.yml")
    if gy:
        m = re.search(r"(?m)^\s*domain:\s*(\S+)", gy)
        return {"tool": "govard", "url": f"https://{m.group(1)}" if m else "?", "magento": "govard tool magento",
                "npm": "govard tool npm", "php": "govard tool php", "composer": "govard tool composer"}
    if (root / ".warden").is_dir() or "WARDEN_ENV_NAME" in read(root / ".env"):
        m = re.search(r"(?m)^TRAEFIK_DOMAIN=(\S+)", read(root / ".env"))
        return {"tool": "warden", "url": f"https://{m.group(1)}" if m else "?",
                "magento": "warden env exec php-fpm bin/magento", "npm": "warden env exec php-fpm npm",
                "php": "warden env exec php-fpm php", "composer": "warden env exec php-fpm composer"}
    if (root / ".ddev" / "config.yaml").exists():
        m = re.search(r"(?m)^name:\s*(\S+)", read(root / ".ddev" / "config.yaml"))
        return {"tool": "ddev", "url": f"https://{m.group(1)}.ddev.site" if m else "?", "magento": "ddev magento",
                "npm": "ddev npm", "php": "ddev exec php", "composer": "ddev composer"}
    return {"tool": "unknown", "url": "?"}


def _signature(root: Path) -> str:
    parts = [root / "composer.lock", root / "Makefile", root / ".govard.yml", root / "CLAUDE.md"]
    for t in (root / "app/design/frontend").glob("*/*"):
        parts += [t / "theme.xml", t / "web/tailwind/package.json", t / "web/tailwind/tailwind.config.js",
                  t / "web/tailwind/tailwind-source.css", t / "web/tailwind/hyva.config.json"]
    sig = []
    for p in parts:
        try:
            s = p.stat()
            sig.append(f"{p.relative_to(root)}:{s.st_size}:{s.st_mtime_ns}")
        except OSError:
            pass
    return "|".join(sig)


def collect(root: Path) -> dict:
    pkgs = lock_packages(root)
    info = {"root": str(root), "ts": time.time()}
    info["magento"] = (pkgs.get("magento/product-community-edition") or pkgs.get("magento/product-enterprise-edition")
                       or pkgs.get("magento/magento2-base", "?"))
    info["hyva"] = {k.split("/", 1)[1]: v for k, v in pkgs.items() if k.startswith("hyva-themes/")}
    src = root / "vendor/hyva-themes/magento2-theme-module/src"
    info["hyvacsp"] = (src / "ViewModel/HyvaCsp.php").exists()
    info["alpine"] = sorted({p.name for p in src.glob("view/*/web/js/alpine3*.js") if ".min." not in p.name}) if src.is_dir() else []
    themes = _themes(root)
    out = {}
    for code, t in themes.items():
        chain = _chain(code, themes)
        is_hyva = any(c.startswith("Hyva/") for c in chain)
        entry = {"dir": str(t["dir"].relative_to(root)), "parent": t["parent"], "chain": chain,
                 "hyva": is_hyva, "csp": any(c.endswith("-csp") for c in chain)}
        if is_hyva:
            entry["i18n"] = sorted(p.name for p in (t["dir"] / "i18n").glob("*.csv"))
            entry["asset_dirs"] = [d for d in ("web/images", "web/svg", "web/icons", "web/fonts") if (t["dir"] / d).is_dir()]
            entry["tailwind"] = _tailwind(t["dir"], root)
        out[code] = entry
    info["themes"] = out
    hyva_themes = [c for c, t in out.items() if t["hyva"]]
    with_tw = [c for c in hyva_themes if out[c].get("tailwind")]
    info["target_theme"] = (with_tw or hyva_themes or [None])[0]
    tw = out.get(info["target_theme"], {}).get("tailwind", {})
    info["tw"] = tw.get("major", 0)

    total = reg = 0
    for base in (root / "app/design/frontend", root / "app/code"):
        for p in base.rglob("*.phtml"):
            text = read(p)
            if "<script" in text:
                total += 1
                reg += "registerInlineScript" in text
    info["scripts_total"], info["scripts_registered"] = total, reg
    mk = read(root / "Makefile")
    gate = "csp-gate" in mk or bool(re.search(r"(?m)^verify:", mk))
    any_csp = any(t.get("csp") for t in out.values())
    info["csp_mode"] = "strict" if any_csp or gate or (total >= 10 and reg / max(total, 1) >= 0.5) else "ready"
    env = _env(root)
    info["env"] = env
    guidance = [c for c in ("CLAUDE.md", "AGENTS.md", ".claude/CLAUDE.md", "figma-review.config.json", "phpcs.xml",
                            "phpcs.xml.dist", "phpstan.neon", "phpstan.neon.dist") if (root / c).exists()]
    for d in (".agents/skills/_shared",):
        if (root / d).is_dir():
            guidance += [f"{d}/{p.name}" for p in sorted((root / d).glob("*.md"))]
    info["guidance"] = guidance
    proj_skills = sorted(p.name for p in (root / ".claude/skills").iterdir()) if (root / ".claude/skills").is_dir() else []
    info["project_skills"] = proj_skills
    if re.search(r"(?m)^verify:", mk):
        info["gate"] = "make verify"
    elif "phpcs-phpstan" in proj_skills:
        info["gate"] = "skill:phpcs-phpstan"
    else:
        info["gate"] = "skill:magento2-linter"
    cmds = {}
    if env["tool"] != "unknown" and info["target_theme"]:
        tdir = out[info["target_theme"]]["dir"]
        scripts = tw.get("scripts", [])
        script = "build-prod" if "build-prod" in scripts else ("build" if "build" in scripts else None)
        if script:
            cmds["build"] = f"{env['npm']} --prefix {tdir}/web/tailwind run {script}"
        if "generate" in scripts:
            cmds["generate"] = f"{env['npm']} --prefix {tdir}/web/tailwind run generate"
        cmds["flush"] = f"{env['magento']} cache:flush layout block_html full_page"
        cmds["di"] = f"{env['magento']} setup:di:compile"
        cmds["css_out"] = f"{tdir}/web/css/styles.css"
    info["cmds"] = cmds
    return info


def project(root: Path, refresh: bool = False, theme: str = None) -> dict:
    cf = root / CACHE_DIR / "project.json"
    sig = _signature(root)
    info = None
    if not refresh and cf.exists():
        try:
            cached = json.loads(read(cf))
            if cached.get("sig") == sig and time.time() - cached.get("ts", 0) < CACHE_TTL:
                info = cached
        except ValueError:
            pass
    if info is None:
        info = collect(root)
        info["sig"] = sig
        try:
            cache_dir(root)
            cf.write_text(json.dumps(info, indent=1))
        except OSError:
            pass
    if theme and theme in info["themes"]:
        info["target_theme"] = theme
        info["tw"] = info["themes"][theme].get("tailwind", {}).get("major", info["tw"])
    return info


def theme_path(info: dict, root: Path, code: str = None) -> Path:
    return root / info["themes"][code or info["target_theme"]]["dir"]
