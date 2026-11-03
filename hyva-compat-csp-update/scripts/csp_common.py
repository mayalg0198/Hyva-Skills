#!/usr/bin/env python3
"""
csp_common.py — Shared Utilities for Hyvä Compatibility Module CSP Update
==========================================================================
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# ANSI colors
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def ensure_python():
    if sys.version_info < (3, 8):
        sys.stderr.write(f"{RED}❌ Python 3.8+ is required (found {sys.version}){RESET}\n")
        sys.exit(2)


def display_path(path: Path) -> str:
    """Path relative to the project root when possible (Path.is_relative_to needs 3.9)."""
    try:
        return str(path.relative_to(find_project_root()))
    except ValueError:
        return str(path)


SKILL_DIR = Path(__file__).resolve().parent.parent


def run_cmd(sub: str) -> str:
    """Copy-pasteable runner invocation for hints."""
    return f"bash {SKILL_DIR}/run.sh {sub}"


def find_project_root() -> Path:
    cwd = Path.cwd().resolve()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / "bin" / "magento").is_file() or (candidate / "composer.json").is_file():
            return candidate
    return cwd


def enter_project_root() -> Path:
    root = find_project_root()
    os.chdir(root)
    return root


# ─── Template cleaning & tokenizing ───────────────────────────────────────────

_PHP_BLOCK = re.compile(r"<\?(?:php|=).*?\?>", re.DOTALL)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_SCRIPT_BLOCK = re.compile(r"<script\b.*?</script>", re.DOTALL | re.IGNORECASE)

RAW_INLINE_SCRIPT_RE = re.compile(
    r"<script\b(?![^>]*\bsrc=)"
    r"(?![^>]*\btype=[\"'](?:application/ld\+json|text/x-magento-init)[\"'])"
    r"[^>]*>",
    re.IGNORECASE
)

# Both `$hyvaCsp->registerInlineScript()` and the non-standard
# `$viewModels->require(HyvaCsp::class)->registerInlineScript()` register the script:
# the view model is a shared instance and the call only reads the output buffer.
HYVA_CSP_REGISTER_CALL_RE = re.compile(
    r"(?:\$hyvaCsp|HyvaCsp::class\s*\))\s*->\s*(?:registerInlineScript|registerInlineStyle)\s*\(",
    re.IGNORECASE
)

NONSTANDARD_CSP_CALL_RE = re.compile(
    r"\$viewModels\s*->\s*require\(\s*\\?(?:[\w\\]*\\)?HyvaCsp::class\s*\)\s*->\s*"
    r"(?P<method>registerInlineScript|registerInlineStyle)\s*\(\s*\)",
    re.IGNORECASE
)


HYVA_CSP_UNSAFE_CALL_RE = re.compile(
    r"<\?php\s+(?!\s*if\s*\(\s*isset|\s*isset\(\s*\$hyvaCsp\))(?:\s*)(\$hyvaCsp->(registerInlineScript|registerInlineStyle)\s*\([^)]*\)\s*;?)\s*\?>",
    re.IGNORECASE
)



# Script types that are data/templates, not executed JS → no nonce/hash needed.
NON_EXECUTABLE_SCRIPT_TYPES = {
    "application/ld+json", "application/json", "text/x-magento-init",
    "text/x-magento-template", "text/html", "text/template", "text/x-template",
}
_SRC_ATTR = re.compile(r"(?<![\w-])src\s*=", re.IGNORECASE)
_TYPE_ATTR = re.compile(r"""(?<![\w-])type\s*=\s*["']?([^"'\s>]+)""", re.IGNORECASE)


NONDETERMINISTIC_CALL = re.compile(
    r"\b(?:uniqid|random_int|rand|mt_rand|random_bytes|microtime|time|hrtime|getRandomString|getUniqueHash)\s*\(",
    re.IGNORECASE,
)


def nondeterministic_vars(content: str) -> set:
    """Variables fed by nondeterministic calls, e.g. `$uniqueId = '_' . uniqid();`."""
    return set(re.findall(r"\$(\w+)\s*=\s*[^;]*?" + NONDETERMINISTIC_CALL.pattern, content, re.IGNORECASE))


def nondeterministic_snippet(script_text: str, nondet_vars: set):
    """First PHP block inside a <script> whose output changes on every render, else None.
    Shared by the auditor (reports it) and the fixer (refuses to register such a script)."""
    for php in re.findall(r"<\?(?:php|=).*?\?>", script_text, re.DOTALL):
        if NONDETERMINISTIC_CALL.search(php) or set(re.findall(r"\$(\w+)", php)) & nondet_vars:
            return php.strip()
    return None


def hyva_csp_class_available(root: Path):
    """True/False when the theme module is installed, None when vendor/ is not there."""
    module = root / "vendor" / "hyva-themes" / "magento2-theme-module"
    if not module.is_dir():
        return None
    return (module / "src" / "ViewModel" / "HyvaCsp.php").is_file()


def is_executable_inline_script(attrs: str) -> bool:
    """True for an inline <script> whose body the browser executes (needs nonce/hash).
    Shared by the auditor and the fixer so they always agree."""
    if _SRC_ATTR.search(attrs):
        return False
    m = _TYPE_ATTR.search(attrs)
    return not (m and m.group(1).lower() in NON_EXECUTABLE_SCRIPT_TYPES)


_PHP_SPAN = re.compile(r"<\?(?:php\b|=).*?(?:\?>|\Z)", re.DOTALL | re.IGNORECASE)


def non_html_spans(text: str) -> list:
    """(start, end) of PHP blocks (unclosed one runs to EOF) and HTML comments.
    A <script> starting inside one of these is a PHP string/comment, not markup."""
    spans = [(m.start(), m.end()) for m in _PHP_SPAN.finditer(text)]
    spans += [(m.start(), m.end()) for m in _HTML_COMMENT.finditer(text)]
    return spans


def in_spans(pos: int, spans: list) -> bool:
    return any(s <= pos < e for s, e in spans)


def mask_php(text: str, token: str = "__PHP__") -> str:
    """Replace each PHP block with `token` (+ its newlines) so attribute values keep a
    visible placeholder, e.g. fn(<?= $id ?>) → fn(__PHP__), and line numbers stay right."""
    return _PHP_BLOCK.sub(lambda m: token + "\n" * m.group(0).count("\n"), text)


def strip_php(text: str) -> str:
    """Replace PHP blocks with whitespace preserving character positions and line numbers."""
    return _PHP_BLOCK.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def strip_html_comments(text: str) -> str:
    """Replace HTML comments with whitespace preserving character positions and line numbers."""
    return _HTML_COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


EXCLUDED_PARTS = {"node_modules", ".git"}
GENERATED_PARTS = {"vendor", "generated", "view_preprocessed", "page_cache"}


def find_templates(target_path: Path) -> list[Path]:
    """Find all .phtml files within target_path (file or directory)."""
    if target_path.is_file():
        return [target_path] if target_path.suffix == ".phtml" else []
    if target_path.is_dir():
        return sorted([
            p for p in target_path.glob("**/*.phtml")
            if not EXCLUDED_PARTS.intersection(p.parts)
        ])
    return []


_LEADING_PHP = re.compile(r"\s*(<\?(?:php\b|=).*?\?>)", re.DOTALL | re.IGNORECASE)


def registration_follows(content: str, end_idx: int) -> bool:
    """True if registerInlineScript() appears in the PHP block(s) directly after the
    </script> ending at end_idx (only whitespace/other PHP blocks in between)."""
    pos = end_idx
    while True:
        m = _LEADING_PHP.match(content, pos)
        if not m:
            return False
        if HYVA_CSP_REGISTER_CALL_RE.search(m.group(1)):
            return True
        pos = m.end()
