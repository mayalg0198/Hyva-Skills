#!/usr/bin/env bash
# ==============================================================================
# Hyvä Theme Upgrade Toolkit — Unified CLI Entrypoint: run.sh
# ==============================================================================
# A single command runner for all upgrade scripts and diagnostics.
# Works out of the box for all team members (junior, mid, senior) and CI/CD.
#
# Usage:
#   ./run.sh doctor                        # Check environment and setup health
#   ./run.sh audit [--strict-csp] [...]    # Run full pre-flight audit suite
#   ./run.sh diff <template-path>          # Diff template against upstream vendor
#   ./run.sh vendor [--csp-only] [--diff]  # Batch compare all overrides with vendor
#   ./run.sh i18n [--locale fr_FR]         # Check translation phrase coverage
#   ./run.sh changelog [--module theme]    # Extract relevant changelog for range
#   ./run.sh visual [path]                 # Run screenshot visual diff comparison
# ==============================================================================
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$SKILL_DIR/scripts"

# shellcheck source=scripts/_lib.sh
source "$SCRIPTS_DIR/_lib.sh"
cd "$(hyva_find_root)" || exit 2

# Colors
CYAN="\033[96m"
GREEN="\033[92m"
YELLOW="\033[93m"
RED="\033[91m"
BOLD="\033[1m"
RESET="\033[0m"

# ─── Help / Usage ─────────────────────────────────────────────────────────────
show_help() {
    echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
    echo -e "${BOLD}${CYAN}🚀 Hyvä Theme Upgrade Toolkit (Unified CLI)${RESET}"
    echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
    echo -e "Usage: ${BOLD}./run.sh <command> [options]${RESET}\n"
    echo -e "${BOLD}Commands:${RESET}"
    echo -e "  ${GREEN}doctor${RESET}               Verify environment, config, dependencies and theme health"
    echo -e "  ${GREEN}audit${RESET} [options]      Run pre-flight scanner + AST theme auditor + i18n check"
    echo -e "                         ${YELLOW}--strict-csp${RESET}       Treat CSP findings as fatal"
    echo -e "                         ${YELLOW}--audit-csp${RESET}        Audit CSP findings as warnings (when strictCsp is false)"
    echo -e "                         ${YELLOW}--module <name>${RESET}    Filter to single module (e.g. Magento_Catalog)"
    echo -e "                         ${YELLOW}--lint-php${RESET}         Validate PHP syntax (php -l)"
    echo -e "                         ${YELLOW}--fail-on-warning${RESET}  Exit with code 1 if warnings found"
    echo -e "  ${GREEN}diff${RESET} <template>      Diff child-theme template against upstream (default or 3rd-party)"
    echo -e "  ${GREEN}vendor${RESET} [options]     Batch compare child-theme templates against upstream"
    echo -e "                         ${YELLOW}--modified-only${RESET}    Only list templates that differ from upstream"
    echo -e "                         ${YELLOW}--identical-only${RESET}   Only list identical templates (redundant overrides)"
    echo -e "                         ${YELLOW}--diff${RESET}             Show unified diffs for modified templates"
    echo -e "                         ${YELLOW}--module <name>${RESET}    Filter to specific module or vendor"
    echo -e "                         ${YELLOW}--csp-only${RESET}         Only list templates with CSP violations"
    echo -e "  ${GREEN}i18n${RESET} [options]       Audit translatable __('...') phrase coverage against CSV"
    echo -e "                         ${YELLOW}--locale <loc>${RESET}     Target specific locale (e.g. fr_FR)"
    echo -e "                         ${YELLOW}--fail-on-missing${RESET}  Exit 1 on untranslated phrases"
    echo -e "  ${GREEN}changelog${RESET} [opts]     Fetch changelog scoped to your from_version → to_version"
    echo -e "                         ${YELLOW}--module theme|commerce|all${RESET}"
    echo -e "  ${GREEN}layout${RESET} [options]     Audit layout XMLs, view.xml, theme.xml inheritance, package drift"
    echo -e "                         ${YELLOW}--fail-on-orphan${RESET}   Exit 1 if orphaned layout targets found"
    echo -e "  ${GREEN}visual${RESET} [path] [opts] Compare baseline vs target storefront with pixel-diff heatmap"
    echo -e "                         ${YELLOW}--viewport desktop|tablet|mobile${RESET}"
    echo -e "                         ${YELLOW}--height <px>${RESET}      Full page height override"
    echo -e "  ${GREEN}help${RESET}                 Show this help menu\n"
    echo -e "${BOLD}Examples:${RESET}"
    echo -e "  ./run.sh doctor"
    echo -e "  ./run.sh audit --module Magento_Catalog"
    echo -e "  ./run.sh diff Magento_Theme/templates/html/header.phtml"
    echo -e "  ./run.sh vendor --csp-only --module 'Amasty_*'"
    echo -e "  ./run.sh changelog"
    echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
}

# ─── Doctor / Health Check ───────────────────────────────────────────────────
run_doctor() {
    echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
    echo -e "${BOLD}${CYAN}🩺 Hyvä Theme Upgrade — Environment & Health Doctor${RESET}"
    echo -e "${BOLD}${CYAN}==============================================================================${RESET}"

    local errors=0
    local warnings=0

    # 1. Python 3
    echo -n "Checking Python interpreter... "
    if command -v python3 >/dev/null 2>&1; then
        PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
        if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'; then
            echo -e "${GREEN}✅ Python $PY_VER${RESET}"
        else
            echo -e "${RED}❌ Python $PY_VER (Requires >= 3.8)${RESET}"
            errors=$((errors + 1))
        fi
    else
        echo -e "${RED}❌ python3 not found!${RESET}"
        errors=$((errors + 1))
    fi

    # 2. Config file
    echo -n "Checking .hyva-upgrade.json... "
    if [ -f ".hyva-upgrade.json" ]; then
        FROM_V="$(hyva_config_get from_version)"
        TO_V="$(hyva_config_get to_version)"
        if [ -n "$FROM_V" ] && [ -n "$TO_V" ]; then
            echo -e "${GREEN}✅ Configured ($FROM_V → $TO_V)${RESET}"
        else
            echo -e "${YELLOW}⚠️  Present, but from_version / to_version missing${RESET}"
            warnings=$((warnings + 1))
        fi
    else
        echo -e "${YELLOW}⚠️  Not found (using default discovery). Copy from .hyva-upgrade.json.sample${RESET}"
        warnings=$((warnings + 1))
    fi

    # 3. Theme directory
    echo -n "Checking Hyvä child theme... "
    THEME_BASE="$(hyva_detect_theme)"
    if [ -n "$THEME_BASE" ] && [ -d "$THEME_BASE" ]; then
        COUNT="$(find "$THEME_BASE" -type f -name "*.phtml" 2>/dev/null | wc -l)"
        echo -e "${GREEN}✅ $THEME_BASE ($COUNT templates)${RESET}"
    else
        echo -e "${RED}❌ Child theme not found! Set themePath in .hyva-upgrade.json${RESET}"
        errors=$((errors + 1))
    fi

    # 4. Vendor default theme
    echo -n "Checking Hyvä default theme... "
    VENDOR_BASE="${HYVA_VENDOR_PATH:-$(hyva_config_get vendorThemePath)}"
    VENDOR_BASE="${VENDOR_BASE:-vendor/hyva-themes/magento2-default-theme}"
    if [ -d "$VENDOR_BASE" ]; then
        echo -e "${GREEN}✅ $VENDOR_BASE${RESET}"
    else
        echo -e "${YELLOW}⚠️  $VENDOR_BASE not found (run composer install)${RESET}"
        warnings=$((warnings + 1))
    fi

    # 5. Composer installed index & version alignment
    echo -n "Checking Composer vendor versions... "
    if [ -f "vendor/composer/installed.json" ]; then
        VERSIONS_INFO=$(python3 -c "
import json
with open('vendor/composer/installed.json') as f:
    d = json.load(f)
pkgs = d.get('packages', d) if isinstance(d, dict) else d
t_ver, m_ver = '', ''
for p in pkgs:
    if p.get('name') == 'hyva-themes/magento2-default-theme':
        t_ver = p.get('version', '').lstrip('v')
    elif p.get('name') == 'hyva-themes/magento2-theme-module':
        m_ver = p.get('version', '').lstrip('v')
print(f'{t_ver}|{m_ver}')
" 2>/dev/null || echo "|")

        INSTALLED_THEME_VER="${VERSIONS_INFO%%|*}"
        INSTALLED_MODULE_VER="${VERSIONS_INFO##*|}"

        if [ -n "$INSTALLED_THEME_VER" ]; then
            if [ -n "$TO_V" ] && [ "$INSTALLED_THEME_VER" != "$TO_V" ]; then
                echo -e "${YELLOW}⚠️  default-theme is $INSTALLED_THEME_VER, but to_version is $TO_V (composer update pending?)${RESET}"
                warnings=$((warnings + 1))
            elif [ -n "$INSTALLED_MODULE_VER" ] && [ "$INSTALLED_THEME_VER" != "$INSTALLED_MODULE_VER" ]; then
                echo -e "${YELLOW}⚠️  Drift: default-theme is $INSTALLED_THEME_VER but theme-module is $INSTALLED_MODULE_VER${RESET}"
                warnings=$((warnings + 1))
            else
                echo -e "${GREEN}✅ default-theme ($INSTALLED_THEME_VER) & theme-module ($INSTALLED_MODULE_VER) aligned${RESET}"
            fi
        else
            echo -e "${GREEN}✅ vendor/composer/installed.json present${RESET}"
        fi
    else
        echo -e "${YELLOW}⚠️  installed.json missing — 3rd-party vendor template matching will be limited${RESET}"
        warnings=$((warnings + 1))
    fi

    # 6. Deployed version trailing newline check
    echo -n "Checking deployed_version.txt... "
    VFILE="pub/static/deployed_version.txt"
    if [ -f "$VFILE" ]; then
        if tr -d '\r\n' < "$VFILE" | cmp -s - "$VFILE"; then
            echo -e "${GREEN}✅ Clean (no trailing newline)${RESET}"
        else
            echo -e "${RED}❌ Trailing newline detected! Breaks hyva-variables.js${RESET}"
            echo -e "   Fix: printf \"%s\" \"\$(cat $VFILE | tr -d '\\r\\n')\" > $VFILE"
            errors=$((errors + 1))
        fi
    else
        echo -e "${GREEN}ℹ️  Not created yet (normal before static deployment)${RESET}"
    fi

    # 7. Pillow (for visual diff)
    echo -n "Checking Pillow (visual-diff)... "
    if python3 -c 'import PIL' >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Installed${RESET}"
    else
        echo -e "${YELLOW}⚠️  Not installed (optional, needed only for ./run.sh visual)${RESET}"
        echo -e "   Install: pip install -r $SKILL_DIR/requirements.txt"
        warnings=$((warnings + 1))
    fi

    # 8. Chrome / Chromium (for visual diff)
    echo -n "Checking Chrome/Chromium... "
    if command -v google-chrome >/dev/null 2>&1 || command -v chromium >/dev/null 2>&1 || command -v chromium-browser >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Available${RESET}"
    else
        echo -e "${YELLOW}⚠️  Not found (optional, needed only for ./run.sh visual screenshots)${RESET}"
        warnings=$((warnings + 1))
    fi

    # 9. Tailwind build environment
    echo -n "Checking Tailwind build environment... "
    TW_DIR="$THEME_BASE/web/tailwind"
    if [ -f "$TW_DIR/package.json" ]; then
        if [ -d "$TW_DIR/node_modules" ]; then
            echo -e "${GREEN}✅ Ready (node_modules present)${RESET}"
        else
            echo -e "${YELLOW}⚠️  node_modules missing in $TW_DIR (run make npm_install)${RESET}"
            warnings=$((warnings + 1))
        fi
    else
        echo -e "${YELLOW}ℹ️  package.json not found in $TW_DIR${RESET}"
    fi

    # 10. Compiled CSS output
    echo -n "Checking compiled CSS output... "
    CSS_FILE="$THEME_BASE/web/css/styles.css"
    if [ -f "$CSS_FILE" ]; then
        CSS_SIZE="$(ls -lh "$CSS_FILE" | awk '{print $5}')"
        echo -e "${GREEN}✅ $CSS_FILE ($CSS_SIZE)${RESET}"
    else
        echo -e "${YELLOW}⚠️  $CSS_FILE not built yet (run make build)${RESET}"
        warnings=$((warnings + 1))
    fi

    echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
    if [ $errors -gt 0 ]; then
        echo -e "${RED}${BOLD}🚨 Doctor detected $errors error(s) and $warnings warning(s). Please fix before proceeding.${RESET}"
        return 1
    elif [ $warnings -gt 0 ]; then
        echo -e "${YELLOW}${BOLD}⚠️  Doctor passed with $warnings advisory note(s). Ready for upgrade work.${RESET}"
        return 0
    else
        echo -e "${GREEN}${BOLD}🎉 All health checks passed! Toolkit is 100% ready.${RESET}"
        return 0
    fi
}

# ─── Audit Command ────────────────────────────────────────────────────────────
run_audit() {
    local scan_args=()
    local theme_args=()
    local i18n_args=()

    while [ $# -gt 0 ]; do
        case "$1" in
            --module|-m)
                scan_args+=("--module" "$2")
                theme_args+=("--module" "$2")
                i18n_args+=("--module" "$2")
                shift 2
                ;;
            --strict-csp|--audit-csp|--lint-php|--fail-on-warning)
                theme_args+=("$1")
                shift
                ;;
            --locale)
                i18n_args+=("--locale" "$2")
                shift 2
                ;;
            --limit)
                i18n_args+=("--limit" "$2")
                shift 2
                ;;
            --fail-on-missing)
                i18n_args+=("$1")
                shift
                ;;
            --config)
                theme_args+=("--config" "$2")
                i18n_args+=("--config" "$2")
                shift 2
                ;;
            --theme)
                scan_args+=("$2")
                theme_args+=("--theme" "$2")
                i18n_args+=("--theme" "$2")
                shift 2
                ;;
            *)
                # Forward any unrecognized flag/arg to theme auditor
                theme_args+=("$1")
                shift
                ;;
        esac
    done

    local exit_code=0

    echo -e "${BOLD}Running Pre-Flight Directive Scanner...${RESET}"
    if ! "$SCRIPTS_DIR/scan-legacy-directives.sh" "${scan_args[@]}"; then
        exit_code=1
    fi

    echo -e "\n${BOLD}Running AST & Feature-Parity Theme Auditor...${RESET}"
    if ! python3 "$SCRIPTS_DIR/audit-theme.py" "${theme_args[@]}"; then
        exit_code=1
    fi

    echo -e "\n${BOLD}Running i18n Translation Phrase Auditor...${RESET}"
    if ! python3 "$SCRIPTS_DIR/audit-i18n.py" "${i18n_args[@]}"; then
        exit_code=1
    fi

    return $exit_code
}

# ─── Command Dispatcher ───────────────────────────────────────────────────────
CMD="${1:-help}"
shift || true

case "$CMD" in
    doctor)
        run_doctor
        ;;
    audit)
        run_audit "$@"
        ;;
    diff)
        "$SCRIPTS_DIR/diff-template.sh" "$@"
        ;;
    vendor)
        python3 "$SCRIPTS_DIR/scan-vendor-diffs.py" "$@"
        ;;
    i18n)
        python3 "$SCRIPTS_DIR/audit-i18n.py" "$@"
        ;;
    changelog)
        python3 "$SCRIPTS_DIR/fetch-changelog.py" "$@"
        ;;
    layout)
        python3 "$SCRIPTS_DIR/scan-layout.py" "$@"
        ;;
    visual)
        "$SCRIPTS_DIR/visual-diff.sh" "$@"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}❌ Unknown command: $CMD${RESET}\n" >&2
        show_help
        exit 2
        ;;
esac
