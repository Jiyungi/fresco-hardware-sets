"""Scan every extracted set for results that look wrong, without needing an answer key.

Usage: python eval/audit.py [--output output]

Each rule below describes something that is almost never right in a real hardware set. Flags are
leads to look at on the page, not proven errors.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hardware_sets.codes import CodeBook  # noqa: E402

BOOK = CodeBook.load()


def component_flags(c: dict) -> list[str]:
    flags = []
    if not c.get("description") and not c.get("catalog_number"):
        flags.append("no description and no catalog number")
    mfr, fin = c.get("mfr"), c.get("finish")
    if mfr and BOOK.is_known_finish(mfr) and not BOOK.is_known_mfr(mfr):
        flags.append(f"maker {mfr!r} looks like a finish")
    if fin and BOOK.is_known_mfr(fin) and not BOOK.is_known_finish(fin):
        flags.append(f"finish {fin!r} looks like a maker")
    if mfr and len(mfr.split()) > 3:
        flags.append(f"maker is long text {mfr[:30]!r}")
    if fin and len(fin.split()) > 4:
        flags.append(f"finish is long text {fin[:30]!r}")
    if c.get("qty") is not None and c["qty"] > 60:
        flags.append(f"quantity {c['qty']}")
    desc = c.get("description") or ""
    if desc and re.fullmatch(r"[\d\s.,\-/]+", desc):
        flags.append(f"description is only numbers {desc!r}")
    return flags


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=str(Path(__file__).resolve().parent.parent / "output"))
    args = ap.parse_args()
    counts: Counter = Counter()
    n_sets = n_comps = 0
    for f in sorted(Path(args.output).glob("*/*.json")):
        d = json.loads(f.read_text())
        for s in d["sets"]:
            n_sets += 1
            where = f"{f.parent.name[:20]} / set {s['set_number']} p{[b['page'] for b in s['location']]}"
            if not s["components"] and not s["not_used"]:
                counts["set with no components (not marked not used)"] += 1
                print(f"{where}: set with no components; notes: {(s.get('set_notes') or '')[:70]!r}")
            for c in s["components"]:
                n_comps += 1
                for flag in component_flags(c):
                    counts[re.sub(r" [\"'].*", "", flag)] += 1
                    print(f"{where}: {flag} | row: {c.get('qty')} | {c.get('description')} | {c.get('catalog_number')}")
    print(f"\nscanned {n_sets} sets, {n_comps} components")
    for k, v in counts.most_common():
        print(f"  {v:4d}  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
