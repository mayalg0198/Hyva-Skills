#!/usr/bin/env python3
"""Find __('...') strings in changed templates and sync them into the right i18n CSV files.

Usage:
  python3 -I i18n_sync.py FILE... | --changed [--base REF] [--write] [--translations map.json]

Resolves the CSV dir per file: app/design/frontend/V/T/** -> that theme's i18n/, app/code/V/M/** ->
the module's i18n/. Reports strings missing from each CSV (read-only by default). With --write it
appends missing rows to every existing locale CSV of that scope; the value is the source string
unless --translations gives {"source string": {"fr_FR": "...", "en_US": "..."}} (then each locale
gets its translation). Never overwrites existing rows. Rows needing a real translation are listed.
"""
import argparse
import csv
import io
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

PHRASE = re.compile(r"""__\(\s*(?:(')((?:\\.|[^'\\])*)'|(")((?:\\.|[^"\\])*)")""")


def i18n_dir(root: Path, f: Path):
    rel = f.relative_to(root).parts
    if rel[:3] == ("app", "design", "frontend") and len(rel) > 5:
        return root.joinpath(*rel[:5], "i18n")
    if rel[:2] == ("app", "code") and len(rel) > 4:
        return root.joinpath(*rel[:4], "i18n")
    return None


def extract(text: str):
    found = []
    for m in PHRASE.finditer(text):
        s = m.group(2) if m.group(1) else m.group(4)
        s = s.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")
        if s:
            found.append(s)
    return found


def keys_of(csv_path: Path) -> set:
    try:
        return {row[0] for row in csv.reader(io.StringIO(_lib.read(csv_path))) if row}
    except csv.Error:
        return set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--changed", action="store_true")
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--translations")
    a = ap.parse_args()
    root = _lib.find_root(os.path.dirname(os.path.abspath(a.files[0])) if a.files else None)
    files = [Path(f).resolve() for f in a.files]
    if a.changed:
        files += _lib.git_changed(root, a.base, (".phtml", ".php", ".js"))
    trans = json.loads(_lib.read(a.translations)) if a.translations else {}

    per_dir = {}
    for f in dict.fromkeys(files):
        if f.suffix not in (".phtml", ".php", ".js"):
            continue
        d = i18n_dir(root, f)
        if d is None:
            continue
        per_dir.setdefault(d, {}).update({s: str(f.relative_to(root)) for s in extract(_lib.read(f))})

    total_missing = 0
    for d, strings in sorted(per_dir.items()):
        csvs = sorted(d.glob("*.csv"))
        if not csvs:
            print(f"{d.relative_to(root)}: no CSV files (create fr_FR.csv?) — {len(strings)} string(s) unchecked")
            continue
        for c in csvs:
            have = keys_of(c)
            missing = [s for s in strings if s not in have]
            total_missing += len(missing)
            loc = c.stem
            print(f"{c.relative_to(root)}: {len(missing)} missing of {len(strings)}")
            for s in missing:
                tr = trans.get(s, {}).get(loc)
                print(f"  + {s!r}" + ("" if tr else "   <- needs translation") + f"  ({strings[s]})")
            if a.write and missing:
                raw = _lib.read(c)
                buf = io.StringIO()
                if raw and not raw.endswith("\n"):
                    buf.write("\n")
                w = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
                for s in missing:
                    w.writerow([s, trans.get(s, {}).get(loc, s)])
                with open(c, "a", encoding="utf-8") as fh:
                    fh.write(buf.getvalue())
                print(f"  wrote {len(missing)} row(s)")
    print(f"i18n: {total_missing} missing row(s) across {len(per_dir)} scope(s)" + ("" if a.write or not total_missing else " (re-run with --write)"))
    sys.exit(1 if total_missing and not a.write else 0)


if __name__ == "__main__":
    main()
