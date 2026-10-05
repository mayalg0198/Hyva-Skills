#!/usr/bin/env python3
"""
==============================================================================
Hyvä i18n Translation Auditor: audit-i18n.py
Purpose: find every __('...') phrase used by the child-theme templates and
         check it has an explicit translation in the theme's i18n/*.csv.

Usage (from anywhere inside the project):
    audit-i18n.py [SUBPATH] [--theme PATH] [--locale fr_FR] [--limit N]
                  [--fail-on-missing]

Source-language locales (en_*) are skipped unless named with --locale, because
untranslated English phrases are expected there.
Exit codes: 0 = ok · 1 = missing translations (with --fail-on-missing) · 2 = setup error
==============================================================================
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hyva_common as hc  # noqa: E402

# __('text')  __("text")  __('text %1', $arg)   — supports escaped quotes (Don\'t)
PHRASE_RE = re.compile(r"""__\(\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")\s*[),]""")


def extract_phrases(text: str) -> list:
    """Return the translatable phrases of one template, escapes resolved."""
    phrases = []
    for single, double in PHRASE_RE.findall(text):
        phrases.append(re.sub(r"\\(.)", r"\1", single or double))
    return phrases


def collect_phrases(theme_base: Path, target_path: Path) -> dict:
    """{phrase: [template paths relative to the theme]} — never skips real templates."""
    found: dict = {}
    for phtml in sorted(target_path.glob("**/*.phtml")):
        rel = phtml.relative_to(theme_base)
        # Compare path *segments*: a substring test would drop any module or
        # checkout directory that merely contains "web" (e.g. /home/me/website).
        if "node_modules" in rel.parts or rel.parts[0] == "web":
            continue
        for phrase in extract_phrases(phtml.read_text(encoding="utf-8", errors="ignore")):
            found.setdefault(phrase, []).append(str(rel))
    return found


def load_translations(csv_file: Path) -> set:
    keys = set()
    with open(csv_file, "r", encoding="utf-8", errors="ignore", newline="") as handle:
        for row in csv.reader(handle):
            if row and len(row) >= 2:
                phrase = row[0].strip()
                trans = row[1].strip()
                if phrase and trans:
                    keys.add(phrase)
    return keys


def main() -> None:
    hc.ensure_python()
    parser = argparse.ArgumentParser(description="Hyvä i18n translation auditor")
    parser.add_argument("subpath", nargs="?", default="", help="Optional sub-path, e.g. Magento_Catalog")
    parser.add_argument("--module", "-m", dest="module", help="Optional module filter (e.g. Magento_Catalog)")
    parser.add_argument("--config", help="Path to .hyva-upgrade.json")
    parser.add_argument("--theme", help="Hyvä child theme directory")
    parser.add_argument("--locale", help="Audit one locale only (e.g. fr_FR); also audits source locales")
    parser.add_argument("--limit", type=int, default=25, help="Max missing phrases printed per locale (default 25)")
    parser.add_argument("--fail-on-missing", action="store_true", help="Exit 1 if any phrase is untranslated")
    args = parser.parse_args()

    hc.enter_project_root()
    config = hc.load_config(args.config)
    theme_base = hc.resolve_theme_path(args.theme, config)
    i18n_dir = theme_base / "i18n"
    subpath = args.module or args.subpath
    target_path = theme_base / subpath if subpath else theme_base
    if not target_path.is_dir():
        sys.stderr.write(f"❌ Audit target not found: {target_path}\n")
        sys.exit(2)

    if args.locale:
        csv_files = [i18n_dir / f"{args.locale}.csv"]
        if not csv_files[0].is_file():
            sys.stderr.write(f"❌ Translation dictionary not found: {csv_files[0]}\n")
            sys.exit(2)
    else:
        csv_files = [f for f in sorted(i18n_dir.glob("*.csv")) if not f.stem.lower().startswith("en_")]
    if not i18n_dir.is_dir() or not csv_files:
        print(f"⚠️  No non-source locale dictionaries in {i18n_dir} — nothing to compare against.")

    print("=" * 80)
    print("🔍 Hyvä i18n Translation Auditor")
    print(f"Theme base  : {theme_base}")
    print(f"Audit target: {target_path}")
    print(f"Locales     : {', '.join(f.stem for f in csv_files) or 'None'}")
    print("=" * 80)

    found = collect_phrases(theme_base, target_path)
    print(f"\nScanned templates. Distinct phrases found: {len(found)}\n")
    if not found:
        print("⚠️  0 phrases found — check the sub-path / theme (a clean report here would be meaningless).\n")

    any_missing = False
    for csv_file in csv_files:
        locale = csv_file.stem
        translations = load_translations(csv_file)
        missing = {k: v for k, v in found.items() if k not in translations}
        any_missing = any_missing or bool(missing)
        covered = len(found) - len(missing)
        pct = (covered / len(found) * 100) if found else 0.0

        print(f"--- 🌐 Locale [{locale}] ---")
        print(f"Explicit theme translations : {covered} / {len(found)} ({pct:.1f}%)")
        print(f"Missing from {locale}.csv   : {len(missing)}")
        if missing:
            shown = sorted(missing.items())[: args.limit]
            if len(missing) > args.limit:
                print(f"   (showing first {args.limit} of {len(missing)} — raise with --limit)")
            for phrase, files in shown:
                where = files[0] if len(files) == 1 else f"{files[0]} (+{len(files) - 1} more)"
                print(f'   • "{phrase}"  --> [{where}]')
        elif found:
            print(f"   ✅ All phrases have an explicit translation in {locale}.csv")
        print()
    print("=" * 80)
    sys.exit(1 if (args.fail_on_missing and any_missing) else 0)


if __name__ == "__main__":
    main()
