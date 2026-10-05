#!/usr/bin/env bash
# Wrapper for visual-diff.py — forwards every argument.
#   visual-diff.sh                      # homepage
#   visual-diff.sh contact --height 4000
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/visual-diff.py" "$@"
