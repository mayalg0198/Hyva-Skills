#!/usr/bin/env python3
"""Versioned spec cache + Figma-component -> partial map, stored in <root>/var/figma-to-hyva/.

Usage:
  cache.py get  FILE_KEY NODE_ID [--version V]     # prints spec prefix when fresh; exit 0 fresh, 2 stale, 3 miss
  cache.py put  FILE_KEY NODE_ID --version V --prefix PATH_PREFIX   # registers PATH_PREFIX.md/.json
  cache.py path FILE_KEY NODE_ID                   # where to write the spec (PREFIX to pass to condense/figma_api)
  cache.py list
  cache.py map get [NAME] | map set NAME TEMPLATE_PATH [--note TEXT]   # component-map.json

`--version` is the Figma file version/lastModified (figma_api.py version, or get_metadata). A cached
spec whose version differs is STALE -> refetch only that node. Without --version a hit is returned
as 'unverified' (exit 0) so offline / quota-limited sessions can still reuse it.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402


def key(file_key, node_id):
    return f"{file_key}_{node_id.replace(':', '-')}"


def index_path(root):
    return _lib.cache_dir(root) / "index.json"


def load_index(root):
    try:
        return json.loads(_lib.read(index_path(root)) or "{}")
    except ValueError:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["get", "put", "path", "list", "map"])
    ap.add_argument("args", nargs="*")
    ap.add_argument("--version")
    ap.add_argument("--prefix")
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    root = _lib.find_root()
    idx = load_index(root)

    if a.cmd == "path":
        print(_lib.cache_dir(root) / key(a.args[0], a.args[1]))
    elif a.cmd == "put":
        k = key(a.args[0], a.args[1])
        idx[k] = {"version": a.version, "prefix": a.prefix or str(_lib.cache_dir(root) / k), "ts": time.time()}
        index_path(root).write_text(json.dumps(idx, indent=1))
        print(f"cached {k} version={a.version}")
    elif a.cmd == "get":
        k = key(a.args[0], a.args[1])
        e = idx.get(k)
        if not e or not os.path.exists(e["prefix"] + ".json"):
            print("MISS")
            sys.exit(3)
        if a.version and e.get("version") != a.version:
            print(f"STALE cached={e.get('version')} current={a.version}")
            sys.exit(2)
        print(f"{'FRESH' if a.version else 'UNVERIFIED'} {e['prefix']}  (read {e['prefix']}.md)")
    elif a.cmd == "list":
        for k, e in sorted(idx.items()):
            print(f"{k} version={e.get('version')} age={int((time.time() - e['ts']) / 3600)}h {e['prefix']}")
        if not idx:
            print("(empty)")
    else:
        mp = _lib.cache_dir(root) / "component-map.json"
        data = json.loads(_lib.read(mp) or "{}")
        sub = a.args[0] if a.args else "get"
        if sub == "set":
            data[a.args[1]] = {"template": a.args[2], "note": a.note}
            mp.write_text(json.dumps(data, indent=1))
            print(f"mapped {a.args[1]} -> {a.args[2]}")
        else:
            name = a.args[1] if len(a.args) > 1 else None
            for n, v in sorted(data.items()):
                if name is None or name.lower() in n.lower():
                    print(f"{n} -> {v['template']} {v.get('note', '')}")
            if not data:
                print("(empty)")


if __name__ == "__main__":
    main()
