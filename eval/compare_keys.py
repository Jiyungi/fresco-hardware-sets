"""Compare two independent transcriptions of the same sets (double entry).

Usage: python eval/compare_keys.py <first key folder> <second key folder>

Every value where the two copies disagree is listed, so a person can look at the page and decide which
copy is right. Where both copies agree, the value is very likely right: two independent readers would
have to make the same mistake.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from evaluate import ALL_FIELDS, align, match_sets, same


def compare(first: dict, second: dict) -> tuple[Counter, list[str]]:
    stats: Counter = Counter()
    diffs: list[str] = []
    for a, b in match_sets(first["sets"], second["sets"]):
        stats["sets"] += 1
        if b is None:
            diffs.append(f"set {a['set_number']}: only in the first copy")
            continue
        for f in ("description", "not_used"):
            stats["values"] += 1
            if not same(a.get(f), b.get(f)):
                diffs.append(f"set {a['set_number']} p{a.get('pages')}: {f}: first {a.get(f)!r} / second {b.get(f)!r}")
            else:
                stats["agree"] += 1
        for ca, cb in align(a["components"], b["components"]):
            if ca is None or cb is None:
                row = ca or cb
                which = "first" if ca else "second"
                diffs.append(f"set {a['set_number']} p{a.get('pages')}: row only in the {which} copy: "
                             f"{row.get('qty')} | {row.get('description')} | {row.get('catalog_number')}")
                stats["values"] += len(ALL_FIELDS)
                continue
            for f in ALL_FIELDS:
                stats["values"] += 1
                if same(ca.get(f), cb.get(f)):
                    stats["agree"] += 1
                else:
                    diffs.append(f"set {a['set_number']} p{a.get('pages')}: {f} of {ca.get('description')!r}: "
                                 f"first {ca.get(f)!r} / second {cb.get(f)!r}")
    return stats, diffs


def main() -> int:
    first_dir, second_dir = Path(sys.argv[1]), Path(sys.argv[2])
    total: Counter = Counter()
    for second_file in sorted(second_dir.glob("*.json")):
        first_file = first_dir / second_file.name
        if not first_file.exists():
            print(f"(no first copy for {second_file.name})")
            continue
        stats, diffs = compare(json.loads(first_file.read_text()), json.loads(second_file.read_text()))
        total.update(stats)
        print(f"== {second_file.name}: {stats['agree']}/{stats['values']} values agree")
        for d in diffs:
            print("   ", d)
    for first_file in sorted(first_dir.glob("*.json")):
        if not (second_dir / first_file.name).exists():
            print(f"(no second copy for {first_file.name})")
    print(f"\nOVERALL: {total['agree']}/{total['values']} values agree between the two copies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
