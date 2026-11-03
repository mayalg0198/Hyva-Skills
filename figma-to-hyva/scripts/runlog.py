#!/usr/bin/env python3
"""Run log + aggregate for measuring the skill (var/figma-to-hyva/runs.jsonl).

Usage:
  runlog.py log key=value ...      # e.g. runlog.py log node=12:345 figma_calls=2 minutes=18 tokens_k=140 outcome=ok
  runlog.py summary                # count, averages of numeric fields, last 5 runs
report.py already appends files / lint_errors / figma_calls / browser / visual_diff on every run.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402


def main():
    root = _lib.find_root()
    path = _lib.cache_dir(root) / "runs.jsonl"
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summary"
    if cmd == "log":
        entry = {"ts": int(time.time())}
        for kv in sys.argv[2:]:
            k, _, v = kv.partition("=")
            try:
                entry[k] = float(v) if "." in v else int(v)
            except ValueError:
                entry[k] = v
        with open(path, "a") as fh:
            fh.write(json.dumps(entry) + "\n")
        print("logged")
        return
    rows = [json.loads(l) for l in _lib.read(path).splitlines() if l.strip()]
    if not rows:
        print("no runs logged yet")
        return
    nums = {}
    for r in rows:
        for k, v in r.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool) and k != "ts":
                nums.setdefault(k, []).append(v)
    print(f"{len(rows)} run(s)")
    for k, vs in sorted(nums.items()):
        print(f"  {k}: avg {sum(vs) / len(vs):.1f} (n={len(vs)}, min {min(vs):g}, max {max(vs):g})")
    for r in rows[-5:]:
        print("  " + " ".join(f"{k}={v}" for k, v in r.items() if k != "ts"))


if __name__ == "__main__":
    main()
