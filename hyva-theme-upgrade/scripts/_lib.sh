#!/usr/bin/env bash
# ==============================================================================
# _lib.sh — shared helpers for the bash scripts of hyva-theme-upgrade.
# SOURCE this file, do not execute it:   source "$(dirname "$0")/_lib.sh"
#
# Portable on Linux AND macOS (bash 3.2, BSD grep/find/diff): no mapfile, no
# associative arrays, no GNU-only grep escapes (\s, \?), no `diff --color`
# without a capability probe.
# ==============================================================================

# Locate the Magento project root so scripts work from any sub-directory.
hyva_find_root() {
    local dir="${HYVA_PROJECT_ROOT:-$PWD}"
    while [ "$dir" != "/" ] && [ -n "$dir" ]; do
        if [ -f "$dir/.hyva-upgrade.json" ] || [ -f "$dir/hyva-upgrade.json" ] \
            || [ -f "$dir/bin/magento" ] || [ -d "$dir/app/design/frontend" ]; then
            echo "$dir"
            return 0
        fi
        dir="$(dirname "$dir")"
    done
    echo "$PWD"
}

# Read a top-level scalar from .hyva-upgrade.json (python3 → grep fallback).
# Prints "" when the key or the file is missing. Booleans print true/false.
hyva_config_get() {
    local key="$1" cfg
    for cfg in .hyva-upgrade.json hyva-upgrade.json; do
        [ -f "$cfg" ] || continue
        if command -v python3 >/dev/null 2>&1; then
            python3 - "$cfg" "$key" 2>/dev/null <<'PY'
import json, sys
try:
    v = json.load(open(sys.argv[1], encoding="utf-8")).get(sys.argv[2], "")
except Exception:
    v = ""
if isinstance(v, bool):
    v = str(v).lower()
print("" if v is None or isinstance(v, (dict, list)) else v)
PY
        else
            grep -m1 "\"$key\"" "$cfg" | cut -d'"' -f4
        fi
        return 0
    done
    return 0
}

# Resolve the Hyvä child theme: $HYVA_THEME_PATH > config themePath > discovery.
hyva_detect_theme() {
    if [ -n "${HYVA_THEME_PATH:-}" ] && [ -d "$HYVA_THEME_PATH" ]; then
        echo "$HYVA_THEME_PATH"
        return 0
    fi
    local configured
    configured="$(hyva_config_get themePath)"
    if [ -n "$configured" ] && [ -d "$configured" ]; then
        echo "$configured"
        return 0
    fi
    find app/design/frontend -mindepth 2 -maxdepth 2 -type d 2>/dev/null | sort | while read -r d; do
        if [ -d "$d/web/tailwind" ] || grep -qi "hyva" "$d/theme.xml" 2>/dev/null; then
            echo "$d"
            break
        fi
    done
}

# Portable colored unified diff (BSD diff on macOS has no --color).
hyva_diff() {
    if diff --color=always /dev/null /dev/null >/dev/null 2>&1; then
        diff -u --color=always "$@"
    else
        diff -u "$@"
    fi
}
