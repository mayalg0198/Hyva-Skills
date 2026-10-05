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

HYVA_CSP_REGISTER_CALL_RE = re.compile(
    r"\$hyvaCsp\s*->\s*(?:registerInlineScript|registerInlineStyle)\s*\(",
    re.IGNORECASE
)

HYVA_CSP_SAFE_REGISTER_RE = re.compile(
    r"<\?php\s+(?:if\s*\(\s*isset\(\s*\$hyvaCsp\s*\)\s*\)\s*|\s*isset\(\s*\$hyvaCsp\s*\)\s*&&\s*)\$hyvaCsp->registerInlineScript\(\s*\)\s*;?\s*\?>",
    re.IGNORECASE
)

HYVA_CSP_UNSAFE_CALL_RE = re.compile(
    r"<\?php\s+(?!\s*if\s*\(\s*isset|\s*isset\(\s*\$hyvaCsp\))(?:\s*)(\$hyvaCsp->(registerInlineScript|registerInlineStyle)\s*\([^)]*\)\s*;?)\s*\?>",
    re.IGNORECASE
)

ALPINE_ATTR_RE = re.compile(
    r"""(?:\b|@|:|x-)(?:bind:?|on:?|model|data|init|show|if|text|html|transition|cloak|ref|teleport|[a-zA-Z0-9_\-\.]+)=["']([^"']*)["']""",
    re.IGNORECASE | re.DOTALL
)


def strip_php(text: str) -> str:
    """Replace PHP blocks with whitespace preserving character positions and line numbers."""
    return _PHP_BLOCK.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def strip_html_comments(text: str) -> str:
    """Replace HTML comments with whitespace preserving character positions and line numbers."""
    return _HTML_COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def find_templates(target_path: Path) -> list[Path]:
    """Find all .phtml files within target_path (file or directory)."""
    if target_path.is_file():
        return [target_path] if target_path.suffix == ".phtml" else []
    if target_path.is_dir():
        return sorted([
            p for p in target_path.glob("**/*.phtml")
            if "node_modules" not in p.parts and ".git" not in p.parts
        ])
    return []
