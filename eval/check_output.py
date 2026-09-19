"""Checks on the tool's output that need no answer sheet.

Usage: python eval/check_output.py [--output output]

1. Nothing invented: every value the tool wrote (set number, description, each part's fields) must appear on the
   PDF page(s) where the tool says the set is. This proves the tool only copies what is printed; it cannot prove a
   value landed in the right field.
2. The hospital door index: the hospital folder has a separate PDF listing which set each door uses. Every set
   number in that list must be among the sets the tool found in the hardware PDF.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pymupdf

from check_key import in_order, squash, squash_words

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["description", "catalog_number", "finish", "mfr", "notes"]


def nothing_invented(output: Path) -> None:
    total = missing = 0
    examples = []
    for f in sorted(output.glob("*/*.json")):
        d = json.loads(f.read_text())
        if not d["sets"]:
            continue
        doc = pymupdf.open(ROOT / d["source_file"])
        for s in d["sets"]:
            pages = sorted({b["page"] for b in s["location"]})
            text = squash(" ".join(doc[p - 1].get_text() for p in pages))
            words = [w for w in (squash(w[4]) for p in pages for w in doc[p - 1].get_text("words")) if w]
            values = [s["set_number"]] + ([s["description"]] if s["description"] else [])
            values += [c[k] for c in s["components"] for k in FIELDS if c.get(k)]
            for v in values:
                total += 1
                if squash(v) not in text and not in_order(squash_words(v), words):
                    missing += 1
                    if len(examples) < 10:
                        examples.append(f"{f.parent.name} set {s['set_number']} p{pages}: {v[:70]!r}")
    print(f"1. Nothing invented: {total - missing} of {total} values found on their page ({missing} not found)")
    for e in examples:
        print("     not found:", e)


def hospital_index(output: Path) -> None:
    index = pymupdf.open(ROOT / "HFH DG - HOSPITAL/08 71 00.01 - DOOR HARDWARE INDEX cut up.pdf")
    listed = set(re.findall(r"\b\d{2}-\d{4}[A-Z]?\s+(\d{3}[A-Z]?)\b", "\n".join(p.get_text() for p in index)))
    result = json.loads((output / "HFH DG - HOSPITAL/08 71 00 - DOOR HARDWARE.json").read_text())
    found = {s["set_number"] for s in result["sets"]}
    print(f"2. Hospital door index: {len(listed & found)} of {len(listed)} set numbers the index uses were found; "
          f"missing: {sorted(listed - found)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=str(ROOT / "output"))
    out = Path(ap.parse_args().output)
    nothing_invented(out)
    hospital_index(out)
