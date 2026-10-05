#!/usr/bin/env bash
# ==============================================================================
# verify-cache-pressure.sh — Storefront CSP Verification Under Cache Pressure
# ==============================================================================
# Implements the Sutunam BeBe9 Verification Protocol:
#   - Cold cycle: 5 concurrent requests after FPC flush (verifies no FPC race).
#   - Warm cycle: 40 repeated requests (verifies no dynamic hash accumulation).
#   - Runs both cycles twice.
# ==============================================================================
set -euo pipefail

CYAN="\033[96m"
GREEN="\033[92m"
YELLOW="\033[93m"
RED="\033[91m"
BOLD="\033[1m"
DIM="\033[2m"
RESET="\033[0m"

URL="${1:-}"

if [ -z "$URL" ]; then
    echo -e "${RED}❌ Please specify a storefront URL to test.${RESET}"
    echo -e "Usage: ./run.sh test-pressure <https://my-store.local/path>"
    exit 2
fi

echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
echo -e "${BOLD}${CYAN}🧪 Hyvä CSP Verification Under Cache Pressure${RESET}"
echo -e "${DIM}Target URL: $URL${RESET}"
echo -e "${BOLD}${CYAN}==============================================================================${RESET}\n"

run_cycle() {
    local cycle_num="$1"
    echo -e "${BOLD}--- Cycle #$cycle_num ---${RESET}"

    # 1. Flush FPC for Cold Cycle
    echo -n "Flushing Full Page Cache (FPC)... "
    if [ -f "bin/magento" ]; then
        bin/magento cache:clean full_page &>/dev/null || true
        echo -e "${GREEN}done${RESET}"
    else
        echo -e "${YELLOW}skipped (bin/magento not found in pwd)${RESET}"
    fi

    # 2. Cold Cycle: 5 concurrent requests
    echo -e "${CYAN}Executing Cold Cycle (5 concurrent requests)...${RESET}"
    local pids=()
    local tmp_dir
    tmp_dir=$(mktemp -d)

    for i in {1..5}; do
        curl -s -D "$tmp_dir/headers_cold_$i.txt" -o "$tmp_dir/body_cold_$i.html" "$URL" &
        pids+=($!)
    done

    # Wait for all 5 requests
    for pid in "${pids[@]}"; do
        wait "$pid" || true
    done

    # Validate Cold Responses
    local cold_failures=0
    for i in {1..5}; do
        local csp_header
        csp_header=$(grep -i "^content-security-policy:" "$tmp_dir/headers_cold_$i.txt" || true)
        local status_code
        status_code=$(head -n 1 "$tmp_dir/headers_cold_$i.txt" | awk '{print $2}')

        if [ "$status_code" != "200" ]; then
            echo -e "  ${RED}❌ Worker $i returned HTTP $status_code${RESET}"
            cold_failures=$((cold_failures + 1))
        elif [ -z "$csp_header" ]; then
            echo -e "  ${RED}❌ Worker $i missing Content-Security-Policy header (FPC race condition detected!)${RESET}"
            cold_failures=$((cold_failures + 1))
        fi
    done

    if [ "$cold_failures" -eq 0 ]; then
        echo -e "  ${GREEN}✅ Cold cycle passed! All 5 concurrent workers returned HTTP 200 with valid CSP headers.${RESET}"
    else
        echo -e "  ${RED}🚨 Cold cycle failed with $cold_failures error(s)! Check FPC response binding.${RESET}"
    fi

    # 3. Warm Cycle: 40 repeated requests
    echo -e "\n${CYAN}Executing Warm Cycle (40 repeated requests to test hash stability)...${RESET}"
    local first_csp_len=0
    local hash_growth_detected=0

    for i in {1..40}; do
        local headers_file="$tmp_dir/headers_warm_$i.txt"
        curl -s -D "$headers_file" -o /dev/null "$URL"
        local csp_line
        csp_line=$(grep -i "^content-security-policy:" "$headers_file" || true)
        local current_len=${#csp_line}

        if [ "$i" -eq 1 ]; then
            first_csp_len="$current_len"
        else
            if [ "$current_len" -gt "$first_csp_len" ]; then
                hash_growth_detected=$((hash_growth_detected + 1))
            fi
        fi
    done

    if [ "$hash_growth_detected" -gt 0 ]; then
        echo -e "  ${RED}🚨 Dynamic script hash growth detected! CSP header size grew across warm requests.${RESET}"
        echo -e "  ${YELLOW}⚠️  Check for nondeterministic PHP expressions (uniqid, time, rand) inside inline <script> blocks.${RESET}"
    else
        echo -e "  ${GREEN}✅ Warm cycle passed! CSP header length remained constant (${first_csp_len} bytes) across 40 requests.${RESET}"
    fi

    rm -rf "$tmp_dir"
    echo ""
}

# Run both cycles twice per protocol
run_cycle 1
run_cycle 2

echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
echo -e "${BOLD}Verification completed!${RESET}"
echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
