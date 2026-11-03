#!/usr/bin/env bash
# ==============================================================================
# Hyvä Compatibility Module CSP Update Toolkit (Unified CLI)
# ==============================================================================
# Run from the Magento root:  bash <skill>/run.sh <command> [options]
#   doctor | audit <path> | fix-scripts <path> [--dry-run] | suggest <file> | test-pressure <url> | help
# Never runs git commands — review changes with `git diff` and commit yourself.
# ==============================================================================
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$SKILL_DIR/scripts"

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
    echo -e "${BOLD}${CYAN}🛡️  Hyvä Compatibility Module CSP Update Toolkit (Unified CLI)${RESET}"
    echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
    echo -e "Usage (from the Magento root): ${BOLD}bash $SKILL_DIR/run.sh <command> [options]${RESET}\n"
    echo -e "${BOLD}Commands:${RESET}"
    echo -e "  ${GREEN}doctor${RESET}                      Verify environment, Python, and CSP package presence"
    echo -e "  ${GREEN}audit${RESET} <path> [options]      Audit templates for strict CSP compliance"
    echo -e "                                ${YELLOW}--fail-on-warning${RESET}  Exit with code 1 if warnings found"
    echo -e "                                ${YELLOW}--output text|json${RESET} Output report format"
    echo -e "  ${GREEN}fix-scripts${RESET} <path> [opts]   Add registerInlineScript() after inline </script> (writes files)"
    echo -e "                                ${YELLOW}--dry-run${RESET}          Preview diffs without modifying files"
    echo -e "                                ${YELLOW}--guarded${RESET}          Use isset(\$hyvaCsp) form (modules that also render on Luma)"
    echo -e "                                ${YELLOW}--normalize${RESET}        Rewrite \$viewModels->require(HyvaCsp::class)->… to \$hyvaCsp->…"
    echo -e "                                ${YELLOW}--include-generated${RESET} Allow vendor/, var/, generated/, pub/static/"
    echo -e "  ${GREEN}suggest${RESET} <template.phtml>    Show before/after refactoring recipes for complex Alpine"
    echo -e "  ${GREEN}test-pressure${RESET} <URL> [opts]  Cold (5 concurrent) + warm (40) CSP header test — LOCAL env only"
    echo -e "                                ${YELLOW}--flush${RESET} | ${YELLOW}--flush-cmd \"<cmd>\"${RESET}  Clean FPC before cold cycles"
    echo -e "                                ${YELLOW}--insecure${RESET}         Accept self-signed certificates"
    echo -e "  ${GREEN}help${RESET}                        Show this help menu\n"
    echo -e "${BOLD}Examples:${RESET}"
    echo -e "  run.sh audit app/design/frontend/Vendor/theme/Magento_Catalog"
    echo -e "  run.sh fix-scripts app/code/Vendor/ModuleHyvaCompatibility --dry-run"
    echo -e "  run.sh suggest app/design/frontend/Vendor/theme/Magento_Search/templates/form.mini.phtml"
    echo -e "  run.sh test-pressure https://store.test/ --flush-cmd \"govard tool magento cache:clean full_page\" --insecure"
    echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
}

# ─── Doctor Command ───────────────────────────────────────────────────────────
run_doctor() {
    echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
    echo -e "${BOLD}${CYAN}🩺 Hyvä CSP Update Doctor${RESET}"
    echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
    local errors=0
    local warnings=0

    # 1. Python check
    echo -n "Checking Python interpreter... "
    if command -v python3 &>/dev/null; then
        PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
        echo -e "${GREEN}✅ Python $PY_VER${RESET}"
    else
        echo -e "${RED}❌ python3 not found!${RESET}"
        errors=$((errors + 1))
    fi

    # 2. Project root check
    echo -n "Checking Magento project root... "
    if [ -f "bin/magento" ]; then
        echo -e "${GREEN}✅ Detected ($(pwd))${RESET}"
    else
        echo -e "${YELLOW}⚠️  bin/magento not found — run from the Magento root${RESET}"
        warnings=$((warnings + 1))
    fi

    # 3. Hyvä theme presence
    echo -n "Checking Hyvä Default Theme... "
    if [ -d "vendor/hyva-themes/magento2-default-theme" ]; then
        echo -e "${GREEN}✅ vendor/hyva-themes/magento2-default-theme${RESET}"
    else
        echo -e "${YELLOW}⚠️  Default theme not found in vendor/${RESET}"
        warnings=$((warnings + 1))
    fi

    # 3b. theme-module version ($hyvaCsp is injected into every template by its PhpPlugin)
    echo -n "Checking \$hyvaCsp injection (theme-module)... "
    if grep -q "'hyvaCsp'" vendor/hyva-themes/magento2-theme-module/src/Plugin/TemplateEngine/PhpPlugin.php 2>/dev/null; then
        echo -e "${GREEN}✅ \$hyvaCsp available in all templates (bare calls OK in Hyvä-only code)${RESET}"
    else
        echo -e "${YELLOW}⚠️  theme-module does not inject \$hyvaCsp — always use the isset(\$hyvaCsp) form${RESET}"
        warnings=$((warnings + 1))
    fi

    # 4. Hyvä CSP package presence
    echo -n "Checking Hyvä CSP Theme Package... "
    if [ -d "vendor/hyva-themes/magento2-default-theme-csp" ]; then
        echo -e "${GREEN}✅ vendor/hyva-themes/magento2-default-theme-csp present${RESET}"
    else
        echo -e "${YELLOW}ℹ️  magento2-default-theme-csp not installed (optional if project uses custom CSP policy)${RESET}"
    fi

    echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
    if [ $errors -gt 0 ]; then
        echo -e "${RED}${BOLD}🚨 Doctor detected $errors error(s). Please fix before proceeding.${RESET}"
        return 1
    else
        echo -e "${GREEN}${BOLD}🎉 Environment ready ($warnings warning(s)).${RESET}"
        return 0
    fi
}

# ─── Command Dispatcher ───────────────────────────────────────────────────────
CMD="${1:-help}"
shift || true

case "$CMD" in
    doctor)
        run_doctor
        ;;
    audit)
        python3 "$SCRIPTS_DIR/audit-csp.py" "$@"
        ;;
    fix-scripts)
        python3 "$SCRIPTS_DIR/fix-inline-scripts.py" "$@"
        ;;
    suggest)
        python3 "$SCRIPTS_DIR/suggest-refactor.py" "$@"
        ;;
    test-pressure)
        bash "$SCRIPTS_DIR/verify-cache-pressure.sh" "$@"
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
