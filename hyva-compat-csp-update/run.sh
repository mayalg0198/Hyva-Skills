#!/usr/bin/env bash
# ==============================================================================
# Hyvä Compatibility Module CSP Update Toolkit (Unified CLI)
# ==============================================================================
# Usage:
#   ./run.sh doctor                        # Health & environment check
#   ./run.sh audit [path] [options]        # Audit templates for strict CSP compliance
#   ./run.sh fix-scripts [path] [--dry-run]# Automatically inject registerInlineScript nonces
#   ./run.sh suggest <template.phtml>      # View refactoring recipes for non-CSP expressions
#   ./run.sh help                          # Show help menu
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
    echo -e "Usage: ${BOLD}./run.sh <command> [options]${RESET}\n"
    echo -e "${BOLD}Commands:${RESET}"
    echo -e "  ${GREEN}doctor${RESET}                      Verify environment, Python, and CSP package presence"
    echo -e "  ${GREEN}audit${RESET} [path] [options]      High-precision AST/regex audit for strict CSP compliance"
    echo -e "                                ${YELLOW}--fail-on-warning${RESET}  Exit with code 1 if warnings found"
    echo -e "                                ${YELLOW}--output text|json${RESET} Output report format"
    echo -e "  ${GREEN}fix-scripts${RESET} [path] [opts]   Automatically inject registerInlineScript nonces"
    echo -e "                                ${YELLOW}--dry-run${RESET}          Preview diffs without modifying files"
    echo -e "  ${GREEN}suggest${RESET} <template.phtml>    Show before/after refactoring recipes for complex Alpine"
    echo -e "  ${GREEN}test-pressure${RESET} <URL>         Run Cold (5 concurrent) + Warm (40 repeated) cache stress test"
    echo -e "  ${GREEN}help${RESET}                        Show this help menu\n"
    echo -e "${BOLD}Examples:${RESET}"
    echo -e "  ./run.sh doctor"
    echo -e "  ./run.sh audit app/design/frontend/.../Amasty_XsearchHyvaCompatibility"
    echo -e "  ./run.sh fix-scripts app/code/Vendor/ModuleHyvaCompatibility --dry-run"
    echo -e "  ./run.sh suggest app/design/frontend/.../templates/search.phtml"
    echo -e "  ./run.sh test-pressure https://mystore.local/catalog/product/view/id/123"
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
    if [ -f "bin/magento" ] || [ -f "composer.json" ]; then
        echo -e "${GREEN}✅ Detected ($(pwd))${RESET}"
    else
        echo -e "${YELLOW}⚠️  Not in Magento root directory${RESET}"
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
        echo -e "${GREEN}${BOLD}🎉 Environment ready for CSP upgrade!${RESET}"
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
        "$SCRIPTS_DIR/verify-cache-pressure.sh" "$@"
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
