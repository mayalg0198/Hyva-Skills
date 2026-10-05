#!/usr/bin/env bash
# ==============================================================================
# Helper Script: scan-legacy-directives.sh
# Purpose: fast pre-flight scan of the child theme for known upgrade breakers:
#          Alpine v2 leftovers, undefined x-bind targets, obsolete Hyvä APIs,
#          fragile CSS selectors / unlayered form rules, unsafe tree traversal,
#          and a malformed pub/static/deployed_version.txt.
#
# Usage (from anywhere inside the project):
#   scan-legacy-directives.sh [-h] [Module_Name | path-inside-theme]
#
# Examples:
#   scan-legacy-directives.sh                    # whole theme
#   scan-legacy-directives.sh Magento_Checkout   # one module of the active flow
#
# Exit codes: 0 = no FATAL finding (warnings may exist) · 1 = FATAL finding(s) · 2 = setup error
# ==============================================================================

# shellcheck source=_lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
cd "$(hyva_find_root)" || exit 2

TARGET_INPUT=""
while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        --module|-m)
            TARGET_INPUT="${2:-}"
            [ -n "${2:-}" ] && shift 2 || shift
            ;;
        --locale|--config|--limit|--theme|--php-cmd)
            # Safely skip flags taking an argument so the value isn't treated as a directory
            [ -n "${2:-}" ] && shift 2 || shift
            ;;
        --*)
            # Ignore single flags intended for downstream auditors (e.g. --strict-csp, --lint-php, --fail-on-warning)
            shift
            ;;
        *)
            TARGET_INPUT="$1"
            shift
            ;;
    esac
done

THEME_BASE="$(hyva_detect_theme)"
if [ -z "$THEME_BASE" ] || [ ! -d "$THEME_BASE" ]; then
    echo "❌ Could not detect the Hyvä child theme. Set themePath in .hyva-upgrade.json or export HYVA_THEME_PATH." >&2
    exit 2
fi

TARGET_DIR="${TARGET_INPUT:-$THEME_BASE}"
if [ "$TARGET_DIR" != "$THEME_BASE" ] && [ ! -d "$TARGET_DIR" ]; then
    TARGET_DIR="$THEME_BASE/$TARGET_DIR"
fi
if [ ! -d "$TARGET_DIR" ]; then
    echo "❌ Scan target not found: $TARGET_DIR" >&2
    exit 2
fi
CSS_DIR="$THEME_BASE/web/tailwind"

echo "=============================================================================="
echo "🔍 Hyvä Upgrade Pre-Flight Scanner"
echo "Target directory: $TARGET_DIR"
echo "=============================================================================="

ERRORS_FOUND=0
WARNINGS_FOUND=0

# 1. x-spread (removed in Alpine v3 → fatal)
echo -n "1. Deprecated 'x-spread' directives... "
OUT=$(grep -rn "x-spread" "$TARGET_DIR" --include="*.phtml" 2>/dev/null || true)
if [ -n "$OUT" ]; then
    echo -e "\n❌ FATAL 'x-spread' usage (use x-bind=\"obj\"):"; echo "$OUT"
    ERRORS_FOUND=$((ERRORS_FOUND + 1))
else
    echo "✅ Clean"
fi

# 2. x-bind="eventListeners" without a definition in the module
echo -n "2. Risky 'x-bind=\"eventListeners\"'... "
RISKY=0
while IFS= read -r file; do
    if grep -q 'x-bind="eventListeners"' "$file" 2>/dev/null; then
        # 1. Defined in the same template?
        if grep -q 'eventListeners:' "$file" 2>/dev/null; then
            continue
        fi
        # 2. Defined in companion template / script within the same module directory?
        MODULE_DIR="$(echo "$file" | sed -E 's|(.*/templates)/.*|\1|; s|/templates$||')"
        if [ -d "$MODULE_DIR" ] && grep -rnq "eventListeners:" "$MODULE_DIR" --include="*.phtml" --include="*.js" 2>/dev/null; then
            continue
        fi
        # 3. Defined in the upstream vendor module?
        REL_FILE="${file#"$THEME_BASE"/}"
        MOD_NAME="$(echo "$REL_FILE" | cut -d'/' -f1)"
        if [ -n "$MOD_NAME" ] && find vendor -maxdepth 4 -type d -iname "*${MOD_NAME#*_}*" 2>/dev/null | xargs -I{} grep -rnq "eventListeners:" "{}" --include="*.phtml" --include="*.js" 2>/dev/null; then
            continue
        fi
        [ $RISKY -eq 0 ] && echo
        echo "⚠️  $file uses x-bind=\"eventListeners\" but 'eventListeners:' is not defined in this module or vendor — verify against component data factory."
        RISKY=$((RISKY + 1))
    fi
done < <(find "$TARGET_DIR" -type f -name "*.phtml")
if [ $RISKY -eq 0 ]; then echo "✅ Clean"; else WARNINGS_FOUND=$((WARNINGS_FOUND + RISKY)); fi

# 3. $el.__x (Alpine v2 internal API → fatal)
echo -n "3. Legacy Alpine v2 '\$el.__x'... "
OUT=$(grep -rn '\$el\.__x' "$TARGET_DIR" --include="*.phtml" 2>/dev/null || true)
if [ -n "$OUT" ]; then
    echo -e "\n❌ FATAL '\$el.__x' usage:"; echo "$OUT"
    ERRORS_FOUND=$((ERRORS_FOUND + 1))
else
    echo "✅ Clean"
fi

# 4. initConfigurableOptions (replaced by PHP-rendered swatches in 1.5.1)
echo -n "4. Obsolete 'initConfigurableOptions'... "
OUT=$(grep -rn "initConfigurableOptions" "$TARGET_DIR" --include="*.phtml" 2>/dev/null || true)
if [ -n "$OUT" ]; then
    echo -e "\n⚠️  Obsolete in Hyvä >= 1.5.1 (PHP-rendered swatches) — review against the vendor template:"; echo "$OUT"
    WARNINGS_FOUND=$((WARNINGS_FOUND + 1))
else
    echo "✅ Clean"
fi

CSS_FREEZE="$(hyva_config_get cssFreeze)"

# 5. Raw `label {` rules outside :where() (specificity trap for flex/inline labels)
echo -n "5. Unlayered form-label CSS rules... "
if [ "$CSS_FREEZE" = "true" ]; then
    echo "ℹ️  Skipped (cssFreeze is true)"
elif [ -d "$CSS_DIR" ]; then
    OUT=$(grep -rnE '(^|[[:space:],>+~])label[[:space:]]*\{' "$CSS_DIR" --include="*.css" --exclude-dir=node_modules 2>/dev/null | grep -v ":where" | grep -vE '(\.|\#|\[)[^\{]*label' || true)
    if [ -n "$OUT" ]; then
        echo -e "\n⚠️  Raw 'label {' without :where() (can override .flex/.inline-flex layouts):"; echo "$OUT"
        WARNINGS_FOUND=$((WARNINGS_FOUND + 1))
    else
        echo "✅ Clean"
    fi
else
    echo "ℹ️  skipped (no $CSS_DIR)"
fi

# 6. [class^="…"] prefix selectors (miss when Magento prepends layout classes to <body>)
echo -n "6. Fragile '[class^=\"...\"]' selectors... "
if [ "$CSS_FREEZE" = "true" ]; then
    echo "ℹ️  Skipped (cssFreeze is true)"
elif [ -d "$CSS_DIR" ]; then
    OUT=$(grep -rnE '\[class\^="[a-zA-Z0-9_-]+"' "$CSS_DIR" --include="*.css" --exclude-dir=node_modules 2>/dev/null || true)
    if [ -n "$OUT" ]; then
        echo -e "\n⚠️  Prefix selector fails when another class comes first (e.g. page-layout-1column). Use [class*=\"...\"]:"; echo "$OUT"
        WARNINGS_FOUND=$((WARNINGS_FOUND + 1))
    else
        echo "✅ Clean"
    fi
else
    echo "ℹ️  skipped (no $CSS_DIR)"
fi

# 7. .children.length without optional chaining (TypeError on leaf nodes)
echo -n "7. Unguarded '.children.length' in templates... "
OUT=$(grep -rn '\.children\.length' "$TARGET_DIR" --include="*.phtml" 2>/dev/null | grep -vF '?.children?.length' || true)
if [ -n "$OUT" ]; then
    echo -e "\n⚠️  Leaf nodes have no 'children' — guard with '?.' to avoid a fatal TypeError:"; echo "$OUT"
    WARNINGS_FOUND=$((WARNINGS_FOUND + 1))
else
    echo "✅ Clean"
fi

# 8. deployed_version.txt trailing newline (breaks THEME_PATH → 'BASE_URL is not defined')
echo -n "8. pub/static/deployed_version.txt trailing newline... "
VERSION_FILE="pub/static/deployed_version.txt"
if [ -f "$VERSION_FILE" ]; then
    if tr -d '\r\n' < "$VERSION_FILE" | cmp -s - "$VERSION_FILE"; then
        echo "✅ Clean"
    else
        echo -e "\n❌ FATAL: trailing newline in $VERSION_FILE — hyva-variables.js will throw a SyntaxError."
        echo "   Fix: printf \"%s\" \"\$(tr -d '\\r\\n' < $VERSION_FILE)\" > $VERSION_FILE"
        ERRORS_FOUND=$((ERRORS_FOUND + 1))
    fi
else
    echo "ℹ️  skipped (file not present — normal on a fresh checkout)"
fi

echo "=============================================================================="
if [ $ERRORS_FOUND -gt 0 ]; then
    echo "🚨 $ERRORS_FOUND FATAL issue(s), $WARNINGS_FOUND warning(s). Resolve the fatals before continuing!"
    echo "=============================================================================="
    exit 1
fi
if [ $WARNINGS_FOUND -gt 0 ]; then
    echo "⚠️  No fatal issues, but $WARNINGS_FOUND warning group(s) need a look (see above)."
else
    echo "🎉 Pre-flight scan completed with no findings."
fi
echo "=============================================================================="
exit 0
