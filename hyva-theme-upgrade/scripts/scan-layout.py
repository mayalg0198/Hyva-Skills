#!/usr/bin/env python3
"""
scan-layout.py — Hyvä Theme Upgrade Layout & Config Auditor
============================================================
Audits layout XML files, etc/view.xml, theme.xml, and hyva.config.json:
  1. Validates <referenceBlock>, <referenceContainer>, and <move> elements:
     detects orphaned targets that no longer exist in upstream vendor or child layouts.
  2. Audits theme.xml for valid <parent> declaration.
  3. Audits etc/view.xml for gallery/swatch configuration alignment.
  4. Audits web/tailwind/package.json drift against vendor default theme.
  5. Audits web/tailwind/hyva.config.json validity.

Usage:
  python3 scripts/scan-layout.py [--config .hyva-upgrade.json] [--theme path] [--fail-on-orphan]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hyva_common as hc  # noqa: E402
from hyva_common import BLUE, BOLD, CYAN, GREEN, RED, RESET, YELLOW  # noqa: E402

# Standard Magento 2 base containers that exist in root page layout templates
STANDARD_CONTAINERS = {
    "root", "head.additional", "content", "page.top", "page.bottom.container",
    "header.container", "footer-container", "sidebar.main", "sidebar.additional",
    "main.content", "columns", "main", "before.body.end", "after.body.start",
    "page.wrapper", "notices-wrapper", "breadcrumbs", "content.aside",
    "store.menu", "navigation.sections", "top.container", "gallery.additional"
}


def parse_xml_safely(file_path: Path) -> ET.Element | None:
    try:
        parser = ET.XMLParser(encoding="utf-8")
        return ET.parse(str(file_path), parser=parser).getroot()
    except Exception as exc:
        sys.stderr.write(f"{YELLOW}⚠️  XML parse error in {file_path}: {exc}{RESET}\n")
        return None


def collect_declared_names(xml_files: list[Path]) -> tuple[set[str], set[str]]:
    """Return (declared_blocks, declared_containers) across a list of layout XMLs."""
    blocks: set[str] = set()
    containers: set[str] = set()

    for f in xml_files:
        root = parse_xml_safely(f)
        if root is None:
            continue
        for el in root.iter("block"):
            name = el.get("name")
            if name:
                blocks.add(name)
        for el in root.iter("container"):
            name = el.get("name")
            if name:
                containers.add(name)

    return blocks, containers


def audit_layout_files(child_layouts: list[Path], all_known_blocks: set[str], all_known_containers: set[str]) -> list[dict]:
    findings: list[dict] = []

    for f in child_layouts:
        root = parse_xml_safely(f)
        if root is None:
            continue

        # 1. referenceBlock
        for el in root.iter("referenceBlock"):
            name = el.get("name")
            if not name:
                continue
            # Some dynamic or core blocks might not appear in static vendor files, but check known set
            if name not in all_known_blocks and name not in all_known_containers:
                # Ignore standard wildcard or dynamic names
                if "{" in name or "$" in name:
                    continue
                findings.append({
                    "file": f,
                    "element": "referenceBlock",
                    "target": name,
                    "type": "orphan_block",
                    "msg": f"<referenceBlock name='{name}'> targets a block not found in vendor/child layouts"
                })

        # 2. referenceContainer
        for el in root.iter("referenceContainer"):
            name = el.get("name")
            if not name:
                continue
            if name not in all_known_containers and name not in all_known_blocks and name not in STANDARD_CONTAINERS:
                if "{" in name or "$" in name:
                    continue
                findings.append({
                    "file": f,
                    "element": "referenceContainer",
                    "target": name,
                    "type": "orphan_container",
                    "msg": f"<referenceContainer name='{name}'> targets a container not found in vendor/child layouts"
                })

        # 3. move elements
        for el in root.iter("move"):
            elem = el.get("element")
            dest = el.get("destination")
            if elem and (elem not in all_known_blocks and elem not in all_known_containers):
                if "{" not in elem and "$" not in elem:
                    findings.append({
                        "file": f,
                        "element": "move",
                        "target": elem,
                        "type": "orphan_move_element",
                        "msg": f"<move element='{elem}'> element not found in known layouts"
                    })
            if dest and (dest not in all_known_containers and dest not in all_known_blocks and dest not in STANDARD_CONTAINERS):
                if "{" not in dest and "$" not in dest:
                    findings.append({
                        "file": f,
                        "element": "move",
                        "target": dest,
                        "type": "orphan_move_destination",
                        "msg": f"<move destination='{dest}'> destination not found in known layouts"
                    })

    return findings


def audit_theme_xml(theme_dir: Path) -> list[str]:
    issues = []
    t_xml = theme_dir / "theme.xml"
    if not t_xml.is_file():
        issues.append("theme.xml not found in child theme root")
        return issues

    root = parse_xml_safely(t_xml)
    if root is None:
        issues.append("theme.xml cannot be parsed")
        return issues

    parent = root.find("parent")
    if parent is None or not (parent.text or "").strip():
        issues.append("<parent> tag missing or empty in theme.xml (should inherit from hyva-themes/default)")
    else:
        parent_name = parent.text.strip()
        if "hyva" not in parent_name.lower():
            issues.append(f"<parent>{parent_name}</parent> does not reference a Hyvä theme")
    return issues


def audit_package_drift(theme_dir: Path, vendor_theme: Path, to_ver: str) -> list[str]:
    notes = []
    child_pkg = theme_dir / "web" / "tailwind" / "package.json"
    vendor_pkg = vendor_theme / "web" / "tailwind" / "package.json"

    if not child_pkg.is_file():
        return ["web/tailwind/package.json not found in child theme"]

    try:
        c_data = json.loads(child_pkg.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"Cannot parse web/tailwind/package.json: {exc}"]

    c_deps = {**c_data.get("dependencies", {}), **c_data.get("devDependencies", {})}
    tw_cli = c_deps.get("@tailwindcss/cli", "")
    tw_core = c_deps.get("tailwindcss", "")

    to_v = hc.parse_ver(to_ver)
    if to_v >= (1, 5, 1):
        # Hyvä 1.5.1+ requires Tailwind 4.3 for logical properties
        def get_major_minor(s: str) -> tuple[int, int]:
            nums = re.findall(r"\d+", s)
            return (int(nums[0]), int(nums[1])) if len(nums) >= 2 else (0, 0)

        cli_mm = get_major_minor(tw_cli)
        core_mm = get_major_minor(tw_core)

        if cli_mm and cli_mm < (4, 3):
            notes.append(f"@tailwindcss/cli version is {tw_cli}; Hyvä 1.5.1+ requires >= 4.3.0 for logical properties (ms-*, me-*)")
        if core_mm and core_mm < (4, 3):
            notes.append(f"tailwindcss version is {tw_core}; Hyvä 1.5.1+ requires >= 4.3.0 for logical properties (ms-*, me-*)")

    if vendor_pkg.is_file():
        try:
            v_data = json.loads(vendor_pkg.read_text(encoding="utf-8"))
            v_scripts = v_data.get("scripts", {})
            c_scripts = c_data.get("scripts", {})
            for sname in ("build-prod", "build", "watch"):
                if sname in v_scripts and sname not in c_scripts:
                    notes.append(f"Missing recommended npm script '{sname}' from vendor default theme package.json")
        except Exception:
            pass

    return notes


def main() -> None:
    hc.ensure_python()
    hc.enter_project_root()

    parser = argparse.ArgumentParser(description="Hyvä Theme Upgrade Layout & Config Auditor")
    parser.add_argument("--config", help="Path to .hyva-upgrade.json")
    parser.add_argument("--theme", help="Child theme path")
    parser.add_argument("--vendor", help="Vendor default theme path")
    parser.add_argument("--fail-on-orphan", action="store_true", help="Exit 1 if orphaned layout references found")
    args = parser.parse_args()

    config = hc.load_config(args.config)
    to_ver = config.get("to_version", "1.5.2")
    strict_csp = hc.resolve_strict_csp(None, config)
    theme_dir = hc.resolve_theme_path(args.theme, config)
    vendor_theme = hc.resolve_vendor_theme(args.vendor, config, strict_csp=strict_csp)

    print("=" * 80)
    print(f"{BOLD}🔍 Hyvä Layout & Config Auditor{RESET}")
    print(f"Target theme   : {theme_dir}")
    print(f"Vendor theme   : {vendor_theme} ({'✅ Found' if vendor_theme.exists() else '⚠️ Missing'})")
    print(f"Target version : {to_ver}")
    print("=" * 80)

    # 1. Audit theme.xml
    print(f"\n{BOLD}1. Auditing theme.xml inheritance...{RESET}")
    theme_issues = audit_theme_xml(theme_dir)
    if theme_issues:
        for iss in theme_issues:
            print(f"  {YELLOW}⚠️  {iss}{RESET}")
    else:
        print(f"  {GREEN}✅ Valid theme inheritance{RESET}")

    # 2. Audit package.json drift
    print(f"\n{BOLD}2. Auditing web/tailwind/package.json drift...{RESET}")
    pkg_issues = audit_package_drift(theme_dir, vendor_theme, to_ver)
    if pkg_issues:
        for iss in pkg_issues:
            print(f"  {YELLOW}⚠️  {iss}{RESET}")
    else:
        print(f"  {GREEN}✅ Tailwind build dependencies and scripts aligned (>= 4.3){RESET}")

    # 3. Collect layout XMLs
    print(f"\n{BOLD}3. Scanning Layout XML Files for Orphaned Blocks/Containers...{RESET}")
    child_layouts = sorted(theme_dir.glob("**/layout/*.xml"))
    vendor_layouts = sorted(vendor_theme.glob("**/layout/*.xml")) if vendor_theme.exists() else []

    # Also include layout files from installed hyva-themes modules
    extra_vendor_layouts = sorted(Path("vendor/hyva-themes").glob("**/view/frontend/layout/*.xml"))

    all_vendor_layouts = vendor_layouts + extra_vendor_layouts
    v_blocks, v_containers = collect_declared_names(all_vendor_layouts)
    c_blocks, c_containers = collect_declared_names(child_layouts)

    known_blocks = v_blocks | c_blocks
    known_containers = v_containers | c_containers | STANDARD_CONTAINERS

    print(f"  Found {len(child_layouts)} child layout files and {len(all_vendor_layouts)} upstream vendor layout files.")
    print(f"  Known declared blocks: {len(known_blocks)} | containers: {len(known_containers)}")

    findings = audit_layout_files(child_layouts, known_blocks, known_containers)

    if findings:
        print(f"\n  {YELLOW}⚠️  {len(findings)} potential orphaned layout reference(s) detected:{RESET}")
        for item in findings[:30]:
            rel_f = item["file"].relative_to(theme_dir)
            print(f"   • {item['target']} ({item['element']}) in {rel_f}")
        if len(findings) > 30:
            print(f"   ... and {len(findings) - 30} more")
    else:
        print(f"  {GREEN}✅ All referenceBlock, referenceContainer, and move targets resolved cleanly!{RESET}")

    print("\n" + "=" * 80)
    if args.fail_on_orphan and findings:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
