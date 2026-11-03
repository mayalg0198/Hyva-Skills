#!/usr/bin/env python3
"""Figma REST access that keeps raw data OUT of the model context (needs FR_FIGMA_TOKEN or FIGMA_TOKEN).

Usage:
  figma_api.py version FILE_KEY                       # lastModified/version for cache checks (cheap)
  figma_api.py node    FILE_KEY NODE_ID [--out PREFIX] [--depth N]   # fetch -> condense -> PREFIX.md/.json
  figma_api.py export  FILE_KEY ID[,ID...] --out DIR [--format svg|png] [--scale 2]

NODE_ID uses ':' (12:345) — dashes from URLs are converted. The token is read from the environment
only, sent only to api.figma.com, and never printed. Exit 3 when no token (use the MCP path),
4 on HTTP/quota errors (stop calling Figma and ask for screenshots instead).
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import condense  # noqa: E402

API = "https://api.figma.com/v1"


def token() -> str:
    t = os.environ.get("FR_FIGMA_TOKEN") or os.environ.get("FIGMA_TOKEN")
    if not t:
        print("no FR_FIGMA_TOKEN/FIGMA_TOKEN in environment — use the MCP path", file=sys.stderr)
        sys.exit(3)
    return t


def get(path: str):
    req = urllib.request.Request(API + path, headers={"X-Figma-Token": token()})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        print(f"figma api HTTP {e.code} {e.reason} on {path.split('?')[0]} — stop and ask for screenshots/specs"
              if e.code in (403, 429) else f"figma api HTTP {e.code} {e.reason}", file=sys.stderr)
        sys.exit(4)
    except urllib.error.URLError as e:
        print(f"figma api unreachable: {e.reason}", file=sys.stderr)
        sys.exit(4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["version", "node", "export"])
    ap.add_argument("file_key")
    ap.add_argument("node", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--depth", type=int)
    ap.add_argument("--format", default="svg", choices=["svg", "png", "jpg"])
    ap.add_argument("--scale", type=float, default=2)
    a = ap.parse_args()
    nid = a.node.replace("-", ":") if a.node else None

    if a.cmd == "version":
        d = get(f"/files/{a.file_key}?depth=1")
        print(json.dumps({"version": d.get("version"), "lastModified": d.get("lastModified"), "name": d.get("name")}))
    elif a.cmd == "node":
        q = f"/files/{a.file_key}/nodes?ids={urllib.parse.quote(nid)}"
        if a.depth:
            q += f"&depth={a.depth}"
        d = get(q)
        lines, spec = condense.condense_rest(d)
        meta = {"version": d.get("version"), "lastModified": d.get("lastModified"), "name": d.get("name")}
        spec["meta"] = meta
        if a.out:
            os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
            open(a.out + ".md", "w").write("\n".join(lines) + "\n")
            open(a.out + ".json", "w").write(json.dumps(spec, indent=1))
            print(f"node {nid}: {len(lines)} layers, {len(spec['typography'])} text style(s), {len(spec['assets'])} asset(s), "
                  f"version {meta['version']} -> {a.out}.md/.json")
        else:
            print("\n".join(lines))
    else:
        os.makedirs(a.out, exist_ok=True)
        ids = ",".join(i.replace("-", ":") for i in a.node.split(","))
        d = get(f"/images/{a.file_key}?ids={urllib.parse.quote(ids)}&format={a.format}&scale={a.scale}")
        for i, url in (d.get("images") or {}).items():
            if not url:
                print(f"{i}: no export")
                continue
            dest = os.path.join(a.out, f"{i.replace(':', '-')}.{a.format}")
            with urllib.request.urlopen(url, timeout=60) as r, open(dest, "wb") as fh:  # S3 url, no token sent
                fh.write(r.read())
            print(f"{i}: {dest} ({os.path.getsize(dest)} bytes)")


if __name__ == "__main__":
    main()
