"""Are the locations meaningful? Checks every set and part the tool found, using only the PDF.

Usage: python eval/check_locations.py [--output output]

For each set:
  1. its set number is printed inside the box the tool gives for the set's first page;
  2. every part's box lies inside the set's box on that page;
  3. the part's own text (first word of its description or catalog number) is printed inside the part's box.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pymupdf

from check_key import squash

ROOT = Path(__file__).resolve().parent.parent


def inside(inner, outer, tol=2.0) -> bool:
    return (inner[0] >= outer[0] - tol and inner[1] >= outer[1] - tol
            and inner[2] <= outer[2] + tol and inner[3] <= outer[3] + tol)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=str(ROOT / "output"))
    out = Path(ap.parse_args().output)
    counts: Counter = Counter()
    examples: list[str] = []
    for f in sorted(out.glob("*/*.json")):
        d = json.loads(f.read_text())
        if not d["sets"]:
            continue
        doc = pymupdf.open(ROOT / d["source_file"])
        for s in d["sets"]:
            boxes = {b["page"]: b["bbox"] for b in s["location"]}
            first = s["location"][0]
            clip = doc[first["page"] - 1].get_text("text", clip=pymupdf.Rect(first["bbox"]))
            counts["sets"] += 1
            if squash(s["set_number"]) in squash(clip):
                counts["set number inside set box"] += 1
            elif len(examples) < 8:
                examples.append(f"{f.parent.name} set {s['set_number']} p{first['page']}: number not in box")
            for c in s["components"]:
                counts["parts"] += 1
                ok_inside = all(b["page"] in boxes and inside(b["bbox"], boxes[b["page"]]) for b in c["location"])
                counts["part box inside set box"] += ok_inside
                word = (c.get("description") or c.get("catalog_number") or "").split()
                b = c["location"][0]
                clip = pymupdf.Rect(b["bbox"]) + (-1, -1, 1, 1)  # one point of slack around the box
                text = squash(doc[b["page"] - 1].get_text("text", clip=clip))
                ok_text = not word or squash(word[0]) in text
                counts["part text inside part box"] += ok_text
                if not (ok_inside and ok_text) and len(examples) < 8:
                    examples.append(f"{f.parent.name} set {s['set_number']} p{b['page']}: part {word[:3]} "
                                    f"inside={ok_inside} text={ok_text}")
    print(f"sets: {counts['sets']}; set number printed inside the set's box: {counts['set number inside set box']}")
    print(f"parts: {counts['parts']}; part box inside its set's box: {counts['part box inside set box']}; "
          f"part's text printed inside its box: {counts['part text inside part box']}")
    for e in examples:
        print("   ", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
