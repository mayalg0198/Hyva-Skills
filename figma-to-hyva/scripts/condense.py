#!/usr/bin/env python3
"""Condense a Figma node into a compact spec (tree text + JSON) the model can read cheaply.

Usage:
  condense.py tsx  FILE|-   [--out PREFIX] [--max-depth N]   # output of Figma MCP get_design_context
  condense.py rest FILE|-   [--out PREFIX] [--max-depth N]   # REST /v1/files/:key/nodes JSON (or a node)

Writes PREFIX.md (indented tree: name[id] size/layout/fill/font "text") and PREFIX.json
({typography, colors, spacing, assets, texts}) and prints a one-line summary. The JSON feeds
`tokens.py batch`. The tree is the only thing the model needs to read; keep raw output out of context.
"""
import argparse
import json
import re
import sys

WEIGHT_NAMES = {"thin": 100, "extralight": 200, "light": 300, "regular": 400, "normal": 400, "medium": 500,
                "semibold": 600, "bold": 700, "extrabold": 800, "black": 900}
VOID = {"img", "input", "br", "hr", "svg"}


def new_spec():
    return {"typography": [], "colors": [], "spacing": [], "assets": [], "texts": []}


def add_typo(spec, size, lh, weight, family, text, color=None, bp=None):
    if not size:
        return
    key = (size, lh, weight, family)
    for t in spec["typography"]:
        if (t["size"], t["lh"], t["weight"], t["family"]) == key:
            if len(t["samples"]) < 3 and text and text[:30] not in t["samples"]:
                t["samples"].append(text[:30])
            return
    spec["typography"].append({"size": size, "lh": lh, "weight": weight, "family": family, "color": color,
                               "text": (text or "")[:30], "samples": [text[:30]] if text else []})


def add_color(spec, hexv):
    h = hexv.lower()
    if len(h) in (4, 5):
        h = "#" + "".join(c * 2 for c in h[1:])
    h = h[:7]
    if h not in spec["colors"]:
        spec["colors"].append(h)


def fnum(s):
    try:
        v = float(s)
        return int(v) if v == int(v) else v
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ TSX (MCP)

def condense_tsx(src: str, max_depth: int = 12):
    spec = new_spec()
    for var, url in re.findall(r"const\s+(\w+)\s*=\s*\"(https://[^\"]+)\"", src):
        spec["assets"].append({"var": var, "url": url, "used_in": []})
    assets = {a["var"]: a for a in spec["assets"]}
    lines, stack = [], []
    tag_re = re.compile(r"<(/?)([A-Za-z][\w.]*)((?:[^<>{}]|\{[^{}]*\})*?)(/?)>|([^<>]+)")
    body = src[src.find("return") if "return" in src else 0:]
    for m in tag_re.finditer(body):
        closing, tag, attrs, selfclose, text = m.groups()
        if text is not None:
            t = re.sub(r"\{\s*[\"'`](.*?)[\"'`]\s*\}", r"\1", text).strip()
            if t and not t.startswith(("{", ")", ";", "}")) and lines and stack:
                lines[-1] = lines[-1] + f' "{t[:80]}"' if not lines[-1].endswith('"') else lines[-1]
            continue
        if closing:
            if stack:
                stack.pop()
            continue
        name = (re.search(r'data-name="([^"]*)"', attrs) or [None, tag])[1]
        nid = (re.search(r'data-node-id="([^"]*)"', attrs) or [None, ""])[1]
        cm = re.search(r'className=(?:"([^"]*)"|\{`([^`]*)`\})', attrs)
        cls = (cm.group(1) or cm.group(2) or "") if cm else ""
        for src_var in re.findall(r"src=\{(\w+)\}", attrs):
            if src_var in assets:
                assets[src_var]["used_in"].append(f"{name}[{nid}]")
        depth = len(stack)
        if depth <= max_depth:
            lines.append(f"{'  ' * depth}{name}[{nid}] <{tag}> {cls}".rstrip())
        if not selfclose and tag.lower() not in VOID:
            stack.append(tag)
        # style extraction from this element's classes
        size = fnum((re.search(r"text-\[(\d+(?:\.\d+)?)px\]", cls) or [0, None])[1])
        lh = fnum((re.search(r"leading-\[(\d+(?:\.\d+)?)px\]", cls) or [0, None])[1])
        wm = re.search(r"font-\[(?:weight:)?(\d{3})\]", cls)
        fm = re.search(r"font-\['([^':]+)(?::([\w ]+))?'", cls)
        weight = int(wm.group(1)) if wm else None
        if not weight and fm and fm.group(2):
            weight = WEIGHT_NAMES.get(fm.group(2).replace(" ", "").lower())
        if not weight:
            wc = re.search(r"\bfont-(thin|extralight|light|normal|medium|semibold|bold|extrabold|black)\b", cls)
            weight = WEIGHT_NAMES.get(wc.group(1)) if wc else None
        color = None
        for cm2 in re.finditer(r"(?:text|bg|border|fill|stroke)-\[(?:color:)?[^\]]*?(#[0-9a-fA-F]{3,8})[^\]]*\]", cls):
            add_color(spec, cm2.group(1))
            if cm2.group(0).startswith("text"):
                color = cm2.group(1).lower()
        if size:
            lines_idx = len(lines) - 1
            spec.setdefault("_pending", []).append((lines_idx, size, lh, weight, fm.group(1) if fm else None, color))
        for pm in re.finditer(r"\b(?:gap|p|px|py|pt|pb|pl|pr|m[xytblr]?|top|left|right|bottom|rounded)-\[(\d+(?:\.\d+)?)px\]", cls):
            v = fnum(pm.group(1))
            if v and v not in [s["px"] for s in spec["spacing"]]:
                spec["spacing"].append({"px": v, "from": pm.group(0)})
    for idx, size, lh, weight, family, color in spec.pop("_pending", []):
        m = re.search(r'"([^"]*)"$', lines[idx]) if idx < len(lines) else None
        add_typo(spec, size, lh, weight, family, m.group(1) if m else "", color)
        if m:
            spec["texts"].append(m.group(1))
    return lines, spec


# ------------------------------------------------------------------ REST

def hex_of(c, opacity=1.0):
    r, g, b = (round(c.get(k, 0) * 255) for k in ("r", "g", "b"))
    return f"#{r:02x}{g:02x}{b:02x}"


def condense_rest(data, max_depth: int = 8):
    spec = new_spec()
    node = data
    if "nodes" in data:
        node = next(iter(data["nodes"].values()))["document"]
    elif "document" in data:
        node = data["document"]
    lines = []

    def visit(n, depth):
        if n.get("visible") is False or depth > max_depth:
            return
        bb = n.get("absoluteBoundingBox") or {}
        parts = [f"{'  ' * depth}{n.get('name', '?')}[{n.get('id', '')}] {n.get('type', '')}"]
        if bb:
            parts.append(f"{round(bb.get('width', 0))}x{round(bb.get('height', 0))}")
        if n.get("layoutMode"):
            parts.append(f"{n['layoutMode'].lower()} gap{round(n.get('itemSpacing', 0))} pad"
                         f"{round(n.get('paddingTop', 0))}/{round(n.get('paddingRight', 0))}/"
                         f"{round(n.get('paddingBottom', 0))}/{round(n.get('paddingLeft', 0))}")
            for k in ("itemSpacing", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft"):
                v = n.get(k)
                if v and v not in [s["px"] for s in spec["spacing"]]:
                    spec["spacing"].append({"px": v, "from": k})
        if n.get("cornerRadius"):
            parts.append(f"r{round(n['cornerRadius'])}")
            if n["cornerRadius"] not in [s["px"] for s in spec["spacing"]]:
                spec["spacing"].append({"px": n["cornerRadius"], "from": "radius"})
        fills = [f for f in n.get("fills", []) if f.get("visible", True)]
        color = None
        if fills and fills[0].get("type") == "SOLID":
            color = hex_of(fills[0]["color"])
            add_color(spec, color)
            parts.append(f"fill{color}")
        if any(f.get("type") == "IMAGE" for f in fills) or n.get("type") in ("VECTOR", "BOOLEAN_OPERATION") \
                or n.get("exportSettings"):
            spec["assets"].append({"id": n.get("id"), "name": n.get("name"), "type": n.get("type")})
            parts.append("ASSET")
        if n.get("type") == "TEXT":
            st = n.get("style", {})
            lh = st.get("lineHeightPx")
            parts.append(f"font {round(st.get('fontSize', 0), 2):g}/{round(lh, 2):g} w{st.get('fontWeight')} "
                         f"{st.get('fontFamily')} {color or ''} \"{n.get('characters', '')[:80]}\"")
            add_typo(spec, fnum(st.get("fontSize")), fnum(round(lh, 2)) if lh else None, st.get("fontWeight"),
                     st.get("fontFamily"), n.get("characters", ""), color)
            spec["texts"].append(n.get("characters", ""))
        lines.append(" ".join(parts))
        for ch in n.get("children", []):
            visit(ch, depth + 1)

    visit(node, 0)
    return lines, spec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["tsx", "rest"])
    ap.add_argument("file")
    ap.add_argument("--out")
    ap.add_argument("--max-depth", type=int)
    a = ap.parse_args()
    raw = sys.stdin.read() if a.file == "-" else open(a.file, encoding="utf-8", errors="replace").read()
    if a.kind == "tsx":
        lines, spec = condense_tsx(raw, a.max_depth or 12)
    else:
        lines, spec = condense_rest(json.loads(raw), a.max_depth or 8)
    md = "\n".join(lines)
    if a.out:
        open(a.out + ".md", "w").write(md + "\n")
        open(a.out + ".json", "w").write(json.dumps(spec, indent=1))
    else:
        print(md)
    print(f"condensed: {len(raw)} chars -> {len(md)} chars tree, {len(spec['typography'])} text style(s), "
          f"{len(spec['colors'])} color(s), {len(spec['spacing'])} spacing value(s), {len(spec['assets'])} asset(s)"
          + (f" -> {a.out}.md/.json" if a.out else ""), file=sys.stderr if not a.out else sys.stdout)


if __name__ == "__main__":
    main()
