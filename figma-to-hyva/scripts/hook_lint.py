#!/usr/bin/env python3
"""PostToolUse hook: lint the .phtml/.php file just written by Edit/Write.

Reads the hook JSON on stdin. Silent (exit 0) when there is nothing to report or the file is not a
template/PHP file under app/. On errors prints them to stderr and exits 2 so Claude sees them
immediately. Never blocks on its own failure.
"""
import json
import os
import subprocess
import sys

try:
    data = json.load(sys.stdin)
    path = (data.get("tool_input") or {}).get("file_path", "")
    if not path.endswith((".phtml", ".php")) or "/app/" not in path or "/vendor/" in path:
        sys.exit(0)
    lint = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lint_phtml.py")
    r = subprocess.run([sys.executable, "-I", lint, path], capture_output=True, text=True, timeout=20)
    if r.returncode == 1:
        sys.stderr.write("figma-to-hyva lint:\n" + r.stdout)
        sys.exit(2)
except SystemExit:
    raise
except Exception:
    pass
sys.exit(0)
