#!/usr/bin/env bash
# ==============================================================================
# verify-cache-pressure.sh — Storefront CSP verification under cache pressure
# ==============================================================================
#   - Cold cycle: 5 concurrent requests (after an FPC clean, if requested).
#   - Warm cycle: 40 sequential requests — the CSP header must not grow.
#   - Both cycles run twice. Exit 1 if any check fails.
#
# Usage:
#   verify-cache-pressure.sh <url> [--flush | --flush-cmd "<cmd>"] [--insecure]
#     --flush            run `bin/magento cache:clean full_page` before each cold cycle
#     --flush-cmd "<c>"  custom clean command, e.g. "govard tool magento cache:clean full_page"
#     --insecure         accept self-signed certificates (curl -k), for local envs
# Without --flush/--flush-cmd nothing is cleaned and the cold cycle may hit a warm cache.
# Only point this at a LOCAL/dev environment: it sends 90 requests.
# ==============================================================================
set -uo pipefail

CYAN="\033[96m"; GREEN="\033[92m"; YELLOW="\033[93m"; RED="\033[91m"; BOLD="\033[1m"; DIM="\033[2m"; RESET="\033[0m"

URL=""; FLUSH_CMD=""; CURL_OPTS=(-sS -L --max-time 30)
while [ $# -gt 0 ]; do
    case "$1" in
        --flush) FLUSH_CMD="bin/magento cache:clean full_page"; shift ;;
        --flush-cmd) FLUSH_CMD="${2:-}"; shift 2 ;;
        --insecure|-k) CURL_OPTS+=(-k); shift ;;
        -*) echo -e "${RED}❌ Unknown option: $1${RESET}" >&2; exit 2 ;;
        *) URL="$1"; shift ;;
    esac
done

if [ -z "$URL" ]; then
    echo -e "${RED}❌ Please specify a storefront URL to test.${RESET}" >&2
    echo "Usage: run.sh test-pressure <https://store.test/path> [--flush | --flush-cmd \"<cmd>\"] [--insecure]" >&2
    exit 2
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
CSP_RE='^content-security-policy(-report-only)?:'
TOTAL_FAILURES=0

echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
echo -e "${BOLD}${CYAN}🧪 Hyvä CSP Verification Under Cache Pressure${RESET}"
echo -e "${DIM}Target URL: $URL${RESET}"
echo -e "${BOLD}${CYAN}==============================================================================${RESET}\n"

flush_cache() {
    echo -n "Cleaning Full Page Cache... "
    if [ -z "$FLUSH_CMD" ]; then
        echo -e "${YELLOW}skipped (no --flush / --flush-cmd) — cold cycle may be served from cache${RESET}"
        return
    fi
    local out
    if out=$(sh -c "$FLUSH_CMD" 2>&1); then
        echo -e "${GREEN}done${RESET}"
    else
        echo -e "${RED}failed${RESET}: $out"
        TOTAL_FAILURES=$((TOTAL_FAILURES + 1))
    fi
}

run_cycle() {
    local cycle_num="$1" i
    echo -e "${BOLD}--- Cycle #$cycle_num ---${RESET}"
    flush_cache

    echo -e "${CYAN}Cold cycle (5 concurrent requests)...${RESET}"
    for i in 1 2 3 4 5; do
        curl "${CURL_OPTS[@]}" -D "$TMP_DIR/cold_$i.h" -o /dev/null "$URL" 2>"$TMP_DIR/cold_$i.err" &
    done
    wait

    local cold_failures=0 status csp
    for i in 1 2 3 4 5; do
        if [ ! -s "$TMP_DIR/cold_$i.h" ]; then
            echo -e "  ${RED}❌ Worker $i: no response ($(tr -d '\n' < "$TMP_DIR/cold_$i.err"))${RESET}"
            cold_failures=$((cold_failures + 1)); continue
        fi
        # with -L the last status line is the final response
        status=$(grep -E '^HTTP/' "$TMP_DIR/cold_$i.h" | tail -n 1 | awk '{print $2}')
        csp=$(grep -iE "$CSP_RE" "$TMP_DIR/cold_$i.h" | tail -n 1 || true)
        if [ "$status" != "200" ]; then
            echo -e "  ${RED}❌ Worker $i returned HTTP $status${RESET}"; cold_failures=$((cold_failures + 1))
        elif [ -z "$csp" ]; then
            echo -e "  ${RED}❌ Worker $i: no Content-Security-Policy header (FPC race?)${RESET}"; cold_failures=$((cold_failures + 1))
        fi
    done
    if [ "$cold_failures" -eq 0 ]; then
        echo -e "  ${GREEN}✅ Cold cycle passed (5 × HTTP 200 with a CSP header)${RESET}"
    else
        echo -e "  ${RED}🚨 Cold cycle: $cold_failures failure(s)${RESET}"
        TOTAL_FAILURES=$((TOTAL_FAILURES + cold_failures))
    fi

    echo -e "\n${CYAN}Warm cycle (40 sequential requests)...${RESET}"
    local min_len="" max_len=0 len errors=0
    for i in $(seq 1 40); do
        if ! curl "${CURL_OPTS[@]}" -D "$TMP_DIR/warm.h" -o /dev/null "$URL" 2>/dev/null; then
            errors=$((errors + 1)); continue
        fi
        csp=$(grep -iE "$CSP_RE" "$TMP_DIR/warm.h" | tail -n 1 || true)
        len=${#csp}
        [ -z "$min_len" ] || [ "$len" -lt "$min_len" ] && min_len=$len
        [ "$len" -gt "$max_len" ] && max_len=$len
    done
    if [ "$errors" -gt 0 ]; then
        echo -e "  ${RED}❌ $errors request(s) failed${RESET}"; TOTAL_FAILURES=$((TOTAL_FAILURES + errors))
    fi
    if [ -n "$min_len" ] && [ "$max_len" -gt "$min_len" ]; then
        echo -e "  ${RED}🚨 CSP header length varied ${min_len} → ${max_len} bytes: hashes accumulate.${RESET}"
        echo -e "  ${YELLOW}   Look for uniqid/time/rand output inside inline <script> (audit: nondeterministic_script_hash).${RESET}"
        TOTAL_FAILURES=$((TOTAL_FAILURES + 1))
    elif [ -n "$min_len" ]; then
        echo -e "  ${GREEN}✅ Warm cycle passed (CSP header constant at ${max_len} bytes)${RESET}"
    fi
    echo ""
}

run_cycle 1
run_cycle 2

echo -e "${BOLD}${CYAN}==============================================================================${RESET}"
if [ "$TOTAL_FAILURES" -gt 0 ]; then
    echo -e "${RED}${BOLD}❌ $TOTAL_FAILURES check(s) failed.${RESET}"
    exit 1
fi
echo -e "${GREEN}${BOLD}✅ All checks passed.${RESET}"
