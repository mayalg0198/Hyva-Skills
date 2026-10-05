#!/usr/bin/env python3
"""
fetch-changelog.py — Hyvä Theme Upgrade Toolkit
================================================
Reads `.hyva-upgrade.json` to get from_version / to_version,
then extracts the relevant changelog sections from:
  - references/changelog-theme-upgrade.md
  - references/changelog-commerce-modules.md

Usage:
  python3 scripts/fetch-changelog.py [--config .hyva-upgrade.json] [--module theme|commerce|all]

Output:
  Prints the changes relevant to the configured version range.
"""

from __future__ import annotations

import json
import os
import re
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hyva_common as hc  # noqa: E402

parse_ver = hc.parse_ver


def latest_known_version(text: str) -> tuple:
    """Highest version mentioned in `## [..]` headings of a changelog file."""
    best = (0,)
    for m in re.finditer(r'^## \[([^\]]+)\]', text, re.MULTILINE):
        for found in re.findall(r'\d+(?:\.\d+)+', m.group(1)):
            best = max(best, parse_ver(found))
    return best


# ─── Helpers ──────────────────────────────────────────────────────────────────

def find_config(start: Path) -> Path | None:
    """Walk up from start directory to find .hyva-upgrade.json."""
    for parent in [start, *start.parents]:
        candidate = parent / ".hyva-upgrade.json"
        if candidate.exists():
            return candidate
    return None


def find_skill_root() -> Path:
    """Return the skill root directory (parent of scripts/)."""
    this_file = Path(__file__).resolve()
    return this_file.parent.parent  # scripts/ → skill root


def parse_version_range(text: str, from_ver: str, to_ver: str, target_module: str | None = None) -> list[dict]:
    """
    Parse changelog file with `## [x.y.z]` or `## [x.y.z → x.y.z]` or `## [module@x.y.z]` headings.
    Returns sections whose version range OVERLAPS with (from_ver, to_ver].
    If target_module is provided, only sections belonging to that module are returned.
    """
    sections = []
    current_section = None
    current_module = None
    current_ver_from = None
    current_ver_to = None
    current_lines = []

    for line in text.splitlines():
        m = re.match(r'^## \[([^\]]+)\]', line)
        if m:
            if current_section is not None and current_lines:
                sections.append({
                    "header": current_section,
                    "module": current_module,
                    "ver_from": current_ver_from,
                    "ver_to": current_ver_to,
                    "content": "\n".join(current_lines).strip()
                })
            current_section = line
            raw = m.group(1).strip()

            def extract_ver(s):
                s = s.split("@", 1)[1] if "@" in s else s
                found = re.findall(r'\d+(?:\.\d+)*', s)
                return found[0] if found else s.strip()

            if "@" in raw:
                current_module = raw.split("@", 1)[0].strip()
                current_ver_from = current_ver_to = extract_ver(raw)
            else:
                current_module = None
                arrow_parts = re.split(r'\s*(?:→|->|—|–)\s*|\s+-\s+', raw, maxsplit=1)
                current_ver_from = extract_ver(arrow_parts[0].strip())
                current_ver_to = extract_ver(arrow_parts[1].strip()) if len(arrow_parts) > 1 else current_ver_from
            current_lines = []

        elif current_section is not None:
            current_lines.append(line)

    if current_section and current_lines:
        sections.append({
            "header": current_section,
            "module": current_module,
            "ver_from": current_ver_from,
            "ver_to": current_ver_to,
            "content": "\n".join(current_lines).strip()
        })

    relevant = []
    try:
        v_from = parse_ver(from_ver)
        v_to = parse_ver(to_ver)
        for s in sections:
            if target_module and s.get("module") != target_module:
                continue
            try:
                if s["ver_to"].lower() in ("baseline", ""):
                    continue
                sv_from = parse_ver(s["ver_from"])
                sv_to = parse_ver(s["ver_to"])
                if sv_to > v_from and sv_from <= v_to:
                    s["version_key"] = s["ver_to"]
                    relevant.append(s)
            except Exception:
                continue
    except Exception as e:
        print(f"[WARN] Cannot parse version range: {e}", file=sys.stderr)
        return sections

    return relevant


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch Hyvä upgrade changelog by version range")
    parser.add_argument("--config", default=None, help="Path to .hyva-upgrade.json")
    parser.add_argument(
        "--module",
        choices=["theme", "commerce", "all"],
        default="all",
        help="Which changelog to fetch (default: all)"
    )
    args = parser.parse_args()

    # 1. Locate config (walks up to the project root, so any sub-directory works)
    hc.ensure_python()
    hc.enter_project_root()
    config_path = Path(args.config) if args.config else find_config(Path.cwd())
    if not config_path or not config_path.exists():
        print("❌ .hyva-upgrade.json not found. Copy from .hyva-upgrade.json.sample and fill in your version range.", file=sys.stderr)
        sys.exit(1)

    config = hc.load_config(str(config_path))

    from_ver = config.get("from_version", "")
    to_ver = config.get("to_version", "")

    if not from_ver or not to_ver:
        print("❌ Config is missing 'from_version' or 'to_version'.", file=sys.stderr)
        print('   Example: { "from_version": "1.4.3", "to_version": "1.5.2" }', file=sys.stderr)
        sys.exit(1)

    print(f"\n{'═'*60}")
    print(f"  Hyvä Changelog Extractor")
    print(f"  Upgrade path: {from_ver} → {to_ver}")
    print(f"{'═'*60}\n")

    skill_root = find_skill_root()
    refs_dir = skill_root / "references"

    # 2. Fetch theme changelog
    if args.module in ("theme", "all"):
        theme_file = refs_dir / "changelog-theme-upgrade.md"
        if theme_file.exists():
            text = theme_file.read_text(encoding="utf-8")
            if parse_ver(to_ver) > latest_known_version(text):
                known = ".".join(map(str, latest_known_version(text)))
                print(f"⚠️  This changelog only covers up to {known}; to_version {to_ver} is newer.\n"
                      f"   Check the upstream release notes and prepend a section (see README → Extending the Changelogs).\n")
            sections = parse_version_range(text, from_ver, to_ver)
            print(f"## 📦 Hyvä Theme ({from_ver} → {to_ver})\n")
            if sections:
                for s in reversed(sections):  # oldest → newest order
                    print(s["header"])
                    print(s["content"])
                    print()
            else:
                print(f"  ✅ No changes found in version range {from_ver} → {to_ver}.\n")
        else:
            print(f"[WARN] Not found: {theme_file}", file=sys.stderr)

    # 3. Fetch commerce changelog
    if args.module in ("commerce", "all"):
        commerce_ver = config.get("commerce_versions", {})
        commerce_file = refs_dir / "changelog-commerce-modules.md"
        if commerce_file.exists():
            text = commerce_file.read_text(encoding="utf-8")
            print(f"## 🏬 Hyvä Commerce Modules\n")

            if commerce_ver:
                # Per-module version ranges defined in config
                for module_key, ver_range in commerce_ver.items():
                    mod_from = ver_range.get("from", "0.0.0")
                    mod_to = ver_range.get("to", "99.99.99")
                    sections = parse_version_range(text, mod_from, mod_to, target_module=module_key)
                    if sections:
                        print(f"### {module_key} ({mod_from} → {mod_to})")
                        for s in reversed(sections):
                            print(s["header"])
                            print(s["content"])
                            print()
            else:
                # No per-module versions: show full changelog without version filtering
                print("  ℹ️  No 'commerce_versions' in config — showing full commerce changelog.\n")
                print(text)

    print(f"\n{'═'*60}")
    print(f"  📖 Full references: {refs_dir}")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()
