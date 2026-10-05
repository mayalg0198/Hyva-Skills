#!/usr/bin/env python3
"""
==============================================================================
hyva_common.py — shared helpers for the hyva-theme-upgrade toolkit
------------------------------------------------------------------------------
Single source of truth for everything the scripts used to copy/paste between
each other: project-root discovery, config loading + validation, version maths,
theme / vendor resolution and the Alpine / CSP template detectors.

Rules for this module:
  * stdlib only (the scripts must run on a fresh machine);
  * must stay importable on Python >= 3.8 (macOS ships 3.9) — no `X | Y`
    runtime unions, no `match`, no `str.removeprefix`;
  * never print on import, never exit on import.
==============================================================================
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

MIN_PYTHON = (3, 8)
CONFIG_NAMES = (".hyva-upgrade.json", "hyva-upgrade.json")
DEFAULT_VENDOR_THEME = "vendor/hyva-themes/magento2-default-theme"

# ─── Colours (auto-disabled for pipes, CI logs and NO_COLOR) ──────────────────
_USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
GREEN = "\033[92m" if _USE_COLOR else ""
YELLOW = "\033[93m" if _USE_COLOR else ""
RED = "\033[91m" if _USE_COLOR else ""
BLUE = "\033[94m" if _USE_COLOR else ""
CYAN = "\033[96m" if _USE_COLOR else ""
BOLD = "\033[1m" if _USE_COLOR else ""
RESET = "\033[0m" if _USE_COLOR else ""


def ensure_python() -> None:
    """Fail early with a readable message on an unsupported interpreter."""
    if sys.version_info < MIN_PYTHON:
        need = ".".join(map(str, MIN_PYTHON))
        have = ".".join(map(str, sys.version_info[:3]))
        sys.stderr.write(f"❌ Python >= {need} is required (found {have}).\n")
        sys.exit(2)


# ─── Project root & config ────────────────────────────────────────────────────

def find_project_root(start: Path | None = None) -> Path:
    """
    Walk up from `start` (default: CWD) to the Magento project root, so every
    script works no matter which sub-directory the user runs it from.
    Override with the HYVA_PROJECT_ROOT environment variable.
    """
    env_root = os.environ.get("HYVA_PROJECT_ROOT")
    if env_root and Path(env_root).is_dir():
        return Path(env_root).resolve()
    here = Path(start or Path.cwd()).resolve()
    for candidate in [here, *here.parents]:
        if (
            any((candidate / n).is_file() for n in CONFIG_NAMES)
            or (candidate / "bin" / "magento").is_file()
            or (candidate / "app" / "design" / "frontend").is_dir()
        ):
            return candidate
    return here


def enter_project_root() -> Path:
    """chdir() into the project root and return it."""
    root = find_project_root()
    os.chdir(root)
    return root


def validate_config(config: dict) -> list[str]:
    """Return human readable problems found in a loaded config (empty = OK)."""
    problems: list[str] = []
    ver_re = re.compile(r"^\d+\.\d+(\.\d+)?$")
    for key in ("from_version", "to_version"):
        val = config.get(key)
        if not val:
            problems.append(f"'{key}' is missing (e.g. \"1.4.3\")")
        elif not ver_re.match(str(val)):
            problems.append(f"'{key}' = {val!r} is not a x.y[.z] version")
    if (
        config.get("from_version")
        and config.get("to_version")
        and parse_ver(config["from_version"]) > parse_ver(config["to_version"])
    ):
        problems.append("'from_version' is greater than 'to_version'")
    if "strictCsp" in config and not isinstance(config["strictCsp"], bool):
        problems.append("'strictCsp' must be true or false")
    if "locales" in config and not (
        isinstance(config["locales"], list) and all(isinstance(x, str) for x in config["locales"])
    ):
        problems.append("'locales' must be a list of strings")
    for key in ("baselineUrl", "targetUrl"):
        val = config.get(key)
        if val and not str(val).startswith(("http://", "https://")):
            problems.append(f"'{key}' must start with http:// or https://")
    theme = config.get("themePath")
    if theme and not Path(theme).is_dir():
        problems.append(f"'themePath' does not exist: {theme}")
    return problems


def load_config(explicit: str | None = None, quiet: bool = False) -> dict:
    """
    Load .hyva-upgrade.json from `explicit` or the project root.
    Invalid JSON is reported (never silently ignored) and yields {}.
    """
    candidates = [Path(explicit)] if explicit else [find_project_root() / n for n in CONFIG_NAMES]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            sys.stderr.write(f"{YELLOW}⚠️  Cannot parse {path}: {exc}{RESET}\n")
            return {}
        if not quiet:
            for problem in validate_config(config):
                sys.stderr.write(f"{YELLOW}⚠️  {path.name}: {problem}{RESET}\n")
        return config
    if not explicit and not quiet:
        sys.stderr.write(
            f"{YELLOW}⚠️  No .hyva-upgrade.json found in project root! Defaulting to fallback parameters.\n"
            f"   Copy .hyva-upgrade.json.sample to .hyva-upgrade.json to define your exact upgrade scope.{RESET}\n"
        )
    return {}


def resolve_strict_csp(cli_value: bool | None, config: dict) -> bool:
    """CLI flag wins, otherwise fall back to config `strictCsp` (default False)."""
    if cli_value is not None:
        return cli_value
    return bool(config.get("strictCsp", False))


# ─── Versions ─────────────────────────────────────────────────────────────────

def parse_ver(v) -> tuple:
    """'1.4.3' → (1, 4, 3); '1.4.7 → 1.4.10' → (1, 4, 7); garbage → (0,)."""
    parts = str(v).split()
    if not parts:
        return (0,)
    nums = re.findall(r"\d+", parts[0])
    return tuple(int(p) for p in nums[:3]) if nums else (0,)


def version_in_range(v: str, from_ver: str, to_ver: str) -> bool:
    """True if from_ver < v <= to_ver (exclusive start, inclusive end)."""
    return parse_ver(from_ver) < parse_ver(v) <= parse_ver(to_ver)


# ─── Theme & vendor resolution ────────────────────────────────────────────────

def find_hyva_themes() -> list[Path]:
    """Auto-discover Hyvä child themes in app/design/frontend/."""
    base = Path("app/design/frontend")
    found: list[Path] = []
    if not base.is_dir():
        return found
    for theme_xml in sorted(base.glob("*/*/theme.xml")):
        theme_dir = theme_xml.parent
        content = theme_xml.read_text(encoding="utf-8", errors="ignore")
        if "hyva" in content.lower() or (theme_dir / "web" / "tailwind").exists():
            found.append(theme_dir)
    return found


def resolve_theme_path(cli_path: str | None, config: dict) -> Path:
    """--theme > $HYVA_THEME_PATH > config.themePath > auto-discovery."""
    for source, value in (
        ("--theme", cli_path),
        ("$HYVA_THEME_PATH", os.environ.get("HYVA_THEME_PATH")),
        ("themePath", config.get("themePath")),
    ):
        if value:
            path = Path(value)
            if path.is_dir():
                return path
            sys.stderr.write(f"{RED}❌ Theme path from {source} not found: {value}{RESET}\n")
            sys.exit(2)

    candidates = find_hyva_themes()
    if not candidates:
        sys.stderr.write(
            f"{RED}❌ No Hyvä child theme found in app/design/frontend/. "
            f"Set themePath in .hyva-upgrade.json or pass --theme.{RESET}\n"
        )
        sys.exit(2)
    if len(candidates) > 1:
        print(f"{BLUE}ℹ️  Multiple Hyvä themes found — using {candidates[0]}:{RESET}", file=sys.stderr)
        for c in candidates:
            print(f"     • {c}", file=sys.stderr)
        print("   (set themePath in .hyva-upgrade.json or pass --theme to choose)", file=sys.stderr)
    return candidates[0]


DEFAULT_VENDOR_THEME_CSP = "vendor/hyva-themes/magento2-default-theme-csp"


def resolve_vendor_theme(cli_path: str | None, config: dict, strict_csp: bool = False) -> Path:
    """--vendor > $HYVA_VENDOR_PATH > config.vendorThemePath > default-theme-csp (if strict CSP) > composer default."""
    if cli_path:
        return Path(cli_path)
    if os.environ.get("HYVA_VENDOR_PATH"):
        return Path(os.environ["HYVA_VENDOR_PATH"])
    if config.get("vendorThemePath"):
        return Path(config["vendorThemePath"])
    if strict_csp and Path(DEFAULT_VENDOR_THEME_CSP).is_dir():
        return Path(DEFAULT_VENDOR_THEME_CSP)
    return Path(DEFAULT_VENDOR_THEME)


def detect_tailwind_version(theme_dir: Path) -> int:
    """Returns 4 for Tailwind v4, 3 for Tailwind v3, or 0 if undetected."""
    pkg = theme_dir / "web" / "tailwind" / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            tw_ver = deps.get("tailwindcss", "") or deps.get("@tailwindcss/cli", "")
            nums = re.findall(r"\d+", str(tw_ver))
            if nums:
                return int(nums[0])
        except Exception:
            pass
    if (theme_dir / "web" / "tailwind" / "tailwind-source.css").exists():
        return 4
    if (theme_dir / "web" / "tailwind" / "tailwind.config.js").exists():
        return 3
    return 0


def build_vendor_module_index() -> dict:
    """Map Magento module names → vendor package dirs (via composer metadata)."""
    index: dict = {}
    composer_file = Path("vendor/composer/installed.json")
    if not composer_file.is_file():
        return index
    try:
        data = json.loads(composer_file.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        sys.stderr.write(f"{YELLOW}⚠️  Cannot index vendor modules: {exc}{RESET}\n")
        return index
    packages = data.get("packages", data) if isinstance(data, dict) else data
    for pkg in packages:
        install_path = pkg.get("install-path")
        if install_path:
            pkg_dir = Path("vendor/composer") / install_path
            if not pkg_dir.exists():
                pkg_dir = Path(install_path)
        else:
            pkg_dir = Path("vendor") / pkg.get("name", "")
        reg = pkg_dir / "registration.php"
        if not reg.is_file():
            continue
        text = reg.read_text(encoding="utf-8", errors="ignore")
        for name in re.findall(r"ComponentRegistrar::MODULE,\s*['\"]([^'\"]+)['\"]", text):
            index.setdefault(name, []).append(pkg_dir)
            index.setdefault(name.lower().replace("_", ""), []).append(pkg_dir)
    return index


_TEMPLATE_ROOTS = (
    "view/frontend/templates",
    "view/base/templates",
    "src/view/frontend/templates",
    "src/view/base/templates",
    "src/components-base/view/frontend/templates",
)


def resolve_vendor_template(rel: Path, vendor_theme: Path, module_index: dict):
    """
    Find the upstream counterpart of a child-theme template.
    Returns (path | None, human readable source).
    """
    direct = vendor_theme / rel
    if direct.exists():
        return direct, "Hyvä Default Theme"

    parts = rel.parts
    module = parts[0]
    if len(parts) > 1 and parts[1] == "templates":
        tpl_sub = Path(*parts[2:]) if len(parts) > 2 else Path()
    else:
        tpl_sub = Path(*parts[1:]) if len(parts) > 1 else Path()

    # Hyvä compatibility packages win over the base (Luma) module.
    names = []
    if "_" in module:
        vendor_prefix, mod_name = module.split("_", 1)
        names += [
            f"{vendor_prefix}_{mod_name}HyvaCompatibility",
            f"{vendor_prefix}_{mod_name}Hyva",
            f"{vendor_prefix}_{mod_name}Compatibility",
            f"{vendor_prefix}_Custom{mod_name}HyvaCompatibility",
            f"{vendor_prefix}_{mod_name}CustomAttributesHyva",
        ]
    names.append(module)

    for name in names:
        for key in (name, name.lower().replace("_", "")):
            for pkg_dir in module_index.get(key, []):
                for sub in _TEMPLATE_ROOTS:
                    cand = pkg_dir / sub / tpl_sub
                    if cand.exists():
                        return cand, pkg_dir.name

    return None, "Not Found (Custom Only)"


# ─── Template detectors (Alpine v3 / Hyvä strict CSP) ─────────────────────────

_PHP_BLOCK = re.compile(r"<\?(?:php|=).*?\?>", re.DOTALL)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_SCRIPT_BLOCK = re.compile(r"<script\b.*?</script>", re.DOTALL | re.IGNORECASE)

# Executable inline <script> (not src=, not data blocks like ld+json / x-magento-init).
RAW_INLINE_SCRIPT_RE = re.compile(
    r"<script\b(?![^>]*\bsrc=)"
    r"(?![^>]*type=['\"](?:text/(?:x-magento-init|template|html)|application/(?:ld\+json|json))['\"])"
    r"[^>]*>",
    re.IGNORECASE,
)
_SCRIPT_WITH_BODY_RE = re.compile(
    r"<script\b(?![^>]*type=['\"](?:text/(?:x-magento-init|template|html)|application/(?:ld\+json|json))['\"])"
    r"[^>]*>(.*?)</script>",
    re.DOTALL | re.IGNORECASE,
)
_DIRECTIVE_RE = re.compile(
    r"(?P<dir>@[a-zA-Z0-9_.-]+|x-on:[a-zA-Z0-9_.-]+|(?<!:):[a-zA-Z0-9_.-]+|x-bind:[a-zA-Z0-9_.-]+"
    r"|x-show|x-text|x-html|x-model|x-if)\s*=\s*"
    r"(?:\"(?P<v1>[^\"]*)\"|'(?P<v2>[^']*)')",
    re.DOTALL,
)
_SKIPPED_DIRECTIVES = ("x-for", "x-ref", "x-defer", "x-cloak", "x-ignore")


def strip_php_and_comments(content: str, drop_scripts: bool = False) -> str:
    out = _PHP_BLOCK.sub("", content)
    out = _HTML_COMMENT.sub("", out)
    if drop_scripts:
        out = _SCRIPT_BLOCK.sub("", out)
    return out


def inline_script_stats(content: str) -> tuple:
    """(executable inline <script> tags, registerInlineScript() calls)."""
    return (
        len(RAW_INLINE_SCRIPT_RE.findall(content)),
        len(re.findall(r"registerInlineScript\s*\(", content)),
    )


def has_unguarded_hyva_csp(content: str) -> bool:
    """registerInlineScript() without isset($hyvaCsp) → fatal when CSP is off."""
    return any(
        "$hyvaCsp->registerInlineScript" in line and "isset($hyvaCsp)" not in line
        for line in content.splitlines()
    )


def has_inline_event_handlers(content: str) -> bool:
    clean = strip_php_and_comments(content, drop_scripts=True)
    return bool(
        re.search(
            r"\bon(click|change|submit|keydown|keyup|keypress|load|mouseover|mouseout|focus|blur)\s*=",
            clean,
            re.IGNORECASE,
        )
    )


def has_php_in_alpine_directives(content: str) -> bool:
    pattern = re.compile(
        r"(?::[a-zA-Z0-9_-]+|@[a-zA-Z0-9_.-]+|x-on:[a-zA-Z0-9_.-]+|x-(?:show|text|html|model|init))"
        r"\s*=\s*(?:\"([^\"]*<\?[^\"]*)\"|'([^']*<\?[^']*)')",
        re.DOTALL,
    )
    for m in pattern.finditer(content):
        val = m.group(1) or m.group(2) or ""
        if "/* @noEscape */ match(" in val:
            continue
        return True
    return False


def has_misplaced_hyva_csp(content: str) -> bool:
    """registerInlineScript() placed inside <script> instead of immediately after </script>."""
    for m in _SCRIPT_WITH_BODY_RE.finditer(content):
        if "registerInlineScript" in (m.group(1) or ""):
            return True
    return False


def has_dynamic_script_hash(content: str) -> bool:
    """uniqid()/microtime()/rand() inside an inline script → a new CSP hash on every render."""
    patterns = ("uniqid(", "$uniqueId", "microtime(", "random_int(", "mt_rand(", "rand(")
    return any(
        any(p in (m.group(1) or "") for p in patterns)
        for m in _SCRIPT_WITH_BODY_RE.finditer(content)
    )


def has_dynamic_script_php(content: str) -> bool:
    """Dynamic PHP data / JSON.parse('<?= inside <script> (FPC hash bloat)."""
    for m in _SCRIPT_WITH_BODY_RE.finditer(content):
        script = m.group(1) or ""
        if re.search(r"JSON\.parse\(\s*['\"]<\?=", script):
            return True
        clean = re.sub(
            r"<\?php\s+isset\(\$hyvaCsp\)\s*&&\s*\$hyvaCsp->registerInlineScript\(\);\s*\?>", "", script
        )
        clean = re.sub(r"<\?php\s+/\*.*?\*/\s*\?>", "", clean, flags=re.DOTALL)
        if re.search(r"<\?=", clean) and any(
            k in clean for k in ("$block->get", "$viewModel", "$user->", "$role->")
        ):
            return True
    return False


def has_complex_inline_xdata(content: str) -> bool:
    """Inline x-data="{ ... }" that defines methods / init() / dynamic JS."""
    for match in re.finditer(r"x-data=([\"'])\s*\{", content):
        start = match.end() - 1
        depth = 0
        for i in range(start, len(content)):
            ch = content[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    block = content[start : i + 1]
                    if any(w in block for w in ("()", "function", "=>", "Date.", "Math.", "this.")):
                        return True
                    break
    return False


def alpine_csp_violations(content: str) -> list[str]:
    """
    Alpine expressions the Hyvä CSP build (`alpine3-csp.js`) cannot evaluate.
    The CSP evaluator only resolves bare dot-paths (`product.name`) against the
    scope stack — calls with args, operators, ternaries, object/array literals,
    assignments and `?.` are all unsupported. Returns [] when clean.
    """
    clean = strip_php_and_comments(content)
    found: list[str] = []

    away = re.findall(r"(@[a-zA-Z0-9_.-]*\.away\b|x-on:[a-zA-Z0-9_.-]*\.away\b)", clean)
    if away:
        found.append(f"legacy Alpine v2 .away modifier ({', '.join(sorted(set(away)))}) — use .outside")

    for m in re.finditer(r"x-data\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", clean):
        val = (m.group(1) or m.group(2) or "").strip()
        if "(" in val or "{" in val:
            found.append(
                f'x-data="{val[:35]}" has arguments/inline object — CSP needs a bare registered Alpine.data name'
            )

    for m in _DIRECTIVE_RE.finditer(clean):
        directive = m.group("dir")
        val = (m.group("v1") if m.group("v1") is not None else m.group("v2")).strip()
        if directive.lstrip(":").startswith("x-transition") or directive in _SKIPPED_DIRECTIVES:
            continue
        if "match(" in val or "/* @noEscape */" in val:
            continue
        reason = None
        if re.search(r"(?<![=!<>])=(?![=])", val):
            reason = "assignment"
        elif "(" in val or ")" in val:
            reason = "function call / parentheses"
        elif "{" in val or "}" in val:
            reason = "object literal"
        elif "[" in val or "]" in val:
            reason = "array lookup"
        elif any(op in val for op in ("&&", "||", "===", "==", "!==", "!=", "?", "+")):
            reason = "operator / ternary / optional chaining"
        elif ";" in val:
            reason = "multiple statements"
        elif re.search(r"(?<![a-zA-Z0-9_$.])!(?![=])", val):
            reason = "negation"
        if reason:
            found.append(f'{directive}="{val[:35]}" uses {reason}')
    return found
