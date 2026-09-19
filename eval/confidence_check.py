"""Do low confidence scores point at the wrong values?

Usage: python eval/confidence_check.py [key folder ...] [--output output]

For every value in the answer key(s) that the program also produced, compare the program's confidence
score with whether the value is right. A useful score gives wrong values lower scores than right ones.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from evaluate import ROOT, align, match_sets, same

FIELDS = ["qty", "description", "catalog_number", "mfr", "finish"]
BANDS = [(0.0, 0.7, "needs checking (< 0.7)"), (0.7, 0.9, "medium (0.7-0.9)"), (0.9, 1.01, "high (>= 0.9)")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*", default=[str(ROOT / "eval" / "fresh_key")])
    ap.add_argument("--output", default=str(ROOT / "output"))
    args = ap.parse_args()

    right: Counter = Counter()
    wrong: Counter = Counter()
    wrong_list = []
    missed_rows = extra_rows = 0
    for folder in args.keys:
        for key_file in sorted(Path(folder).glob("*.json")):
            key = json.loads(key_file.read_text())
            pdf = Path(key["source_pdf"])
            got = json.loads((Path(args.output) / pdf.parent.name / f"{pdf.stem}.json").read_text())
            for ks, gs in match_sets(key["sets"], got["sets"]):
                if gs is None:
                    missed_rows += len(ks["components"])
                    continue
                for kc, gc in align(ks["components"], gs["components"]):
                    if kc is None:
                        extra_rows += 1
                        wrong_list.append((min(gc["confidence"].values()), f"extra row {gc['description']!r}",
                                           ks["set_number"], key_file.stem))
                        continue
                    if gc is None:
                        missed_rows += 1
                        continue
                    for f in FIELDS:
                        conf = gc["confidence"].get(f, 0.0)
                        band = next(name for lo, hi, name in BANDS if lo <= conf < hi)
                        if same(kc.get(f), gc.get(f)):
                            right[band] += 1
                        else:
                            wrong[band] += 1
                            wrong_list.append((conf, f"{f}: got {gc.get(f)!r}, key {kc.get(f)!r}",
                                               ks["set_number"], key_file.stem))
    print("| confidence | values | wrong | share wrong |")
    print("|---|---|---|---|")
    for _, _, name in BANDS:
        n = right[name] + wrong[name]
        share = f"{100 * wrong[name] / n:.1f}%" if n else "n/a"
        print(f"| {name} | {n} | {wrong[name]} | {share} |")
    total_wrong = sum(wrong.values())
    flagged = wrong[BANDS[0][2]]
    all_values = sum(right.values()) + total_wrong
    flagged_all = right[BANDS[0][2]] + flagged
    print(f"\nwrong values: {total_wrong}; of these, marked 'needs checking': {flagged}")
    share = 100 * flagged_all / max(all_values, 1)
    print(f"values marked 'needs checking': {flagged_all} of {all_values} ({share:.1f}%)")
    print(f"rows missed entirely: {missed_rows}; extra rows: {extra_rows}")
    for conf, what, number, book in sorted(wrong_list):
        print(f"  conf {conf:.2f}  {book} set {number}: {what}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
