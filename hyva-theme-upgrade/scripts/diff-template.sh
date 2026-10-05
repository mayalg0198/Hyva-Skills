#!/usr/bin/env bash
# ==============================================================================
# Helper Script: diff-template.sh
# Purpose: diff a customised child-theme template against its upstream
#          counterpart (Hyvä default theme, or the 3rd-party module in vendor/).
#          Needs only POSIX `diff` — no git. Works on Linux and macOS.
#
# Usage (from anywhere inside the project):
#   diff-template.sh <Module_Name/templates/path/file.phtml | filename.phtml>
#
# Exit codes:
#   0 = identical, or no upstream counterpart (custom-only)
#   1 = files differ (expected during upgrade work — diff printed)
#   2 = error (bad usage, file not found, I/O problem)
# ==============================================================================
set -u  # catch typos; every optional variable below uses ${VAR:-}

# shellcheck source=_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
cd "$(hyva_find_root)" || exit 2

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ] || [ -z "${1:-}" ]; then
    sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    [ -z "${1:-}" ] && exit 2
    exit 0
fi

THEME_BASE="$(hyva_detect_theme)"
if [ -z "$THEME_BASE" ] || [ ! -d "$THEME_BASE" ]; then
    echo "❌ Could not detect the Hyvä child theme. Set themePath in .hyva-upgrade.json or export HYVA_THEME_PATH." >&2
    exit 2
fi
VENDOR_BASE="${HYVA_VENDOR_PATH:-$(hyva_config_get vendorThemePath)}"
VENDOR_BASE="${VENDOR_BASE:-vendor/hyva-themes/magento2-default-theme}"

INPUT_PATH="$1"
CLEAN_PATH="${INPUT_PATH#"$THEME_BASE"/}"
CLEAN_PATH="${CLEAN_PATH#./}"

THEME_FILE="$THEME_BASE/$CLEAN_PATH"
if [ ! -f "$THEME_FILE" ]; then
    # Fall back to a basename search inside the theme.
    FOUND="$(find "$THEME_BASE" -type f -name "$(basename "$INPUT_PATH")" 2>/dev/null | head -n 1)"
    if [ -z "$FOUND" ]; then
        echo "❌ Theme file does not exist: $THEME_FILE" >&2
        exit 2
    fi
    THEME_FILE="$FOUND"
    CLEAN_PATH="${THEME_FILE#"$THEME_BASE"/}"
    echo "ℹ️  Resolved to: $THEME_FILE"
fi
VENDOR_FILE="$VENDOR_BASE/$CLEAN_PATH"

echo "=============================================================================="
echo "🔍 Hyvä Template Diff Inspector"
echo "=============================================================================="
echo "Theme file  : $THEME_FILE"
echo "Vendor file : $VENDOR_FILE"
echo "=============================================================================="

if [ ! -f "$VENDOR_FILE" ]; then
    echo "ℹ️  No Hyvä default-theme counterpart. Searching vendor/ for a 3rd-party module template..."
    MODULE_NAME="$(echo "$CLEAN_PATH" | cut -d'/' -f1)"
    FILE_BASENAME="$(basename "$CLEAN_PATH")"

    # 1. Precise resolution via hyva_common (uses vendor/composer/installed.json)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    VENDOR_MATCH=""
    if command -v python3 >/dev/null 2>&1; then
        PY_MATCH="$(python3 - "$CLEAN_PATH" "$VENDOR_BASE" "$SCRIPT_DIR" <<'PY' 2>/dev/null
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[3])
try:
    import hyva_common as hc
    rel = Path(sys.argv[1])
    vendor_theme = Path(sys.argv[2])
    idx = hc.build_vendor_module_index()
    found, src = hc.resolve_vendor_template(rel, vendor_theme, idx)
    if found and found.exists():
        print(f"{found}\t{src}")
except Exception:
    pass
PY
)"
        if [ -n "$PY_MATCH" ]; then
            VENDOR_MATCH="$(echo "$PY_MATCH" | cut -f1)"
            VENDOR_SRC="$(echo "$PY_MATCH" | cut -f2)"
            echo "   Resolved via composer index: $VENDOR_SRC ($VENDOR_MATCH)"
        fi
    fi

    # 2. POSIX fallback if python is unavailable or did not find a match
    if [ -z "$VENDOR_MATCH" ]; then
        CANDIDATES="$(find vendor -type f -name "$FILE_BASENAME" -path '*templates*' 2>/dev/null)"
        VENDOR_MATCH="$(echo "$CANDIDATES" | grep -i "${MODULE_NAME#*_}" | head -n 1)"
        [ -z "$VENDOR_MATCH" ] && VENDOR_MATCH="$(echo "$CANDIDATES" | head -n 1)"
        if [ -z "$VENDOR_MATCH" ]; then
            echo "⚠️  No vendor counterpart found — this template appears custom-only."
            exit 0
        fi
        echo "   Found: $VENDOR_MATCH"
        echo "   (Several vendor files may share this name — verify it is the right module.)"
    fi
    VENDOR_FILE="$VENDOR_MATCH"
fi

hyva_diff "$VENDOR_FILE" "$THEME_FILE"
rc=$?
case $rc in
    0) echo "✅ Identical — no customisation vs upstream."; exit 0 ;;
    1) exit 1 ;;
    *) echo "❌ diff failed (permission or I/O error)." >&2; exit 2 ;;
esac
