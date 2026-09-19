"""Mechanical check of an answer key: does every value it contains actually appear on its PDF page(s)?

Usage: python eval/check_key.py [key folder ...]

A value "appears" when its words occur in the same order in the text of the set's pages (ignoring case,
spacing and line breaks). This catches typos and values copied from the wrong place. It cannot catch a value
that is printed on the page but put in the wrong field, or struck-out text that was copied anyway; those
need the page image (see eval/compare_keys.py and the review of disagreements).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["description", "catalog_number", "finish", "mfr", "notes"]
QUOTES = {0x201C: '"', 0x201D: '"', 0x2019: "'", 0x2018: "'", 0x2013: "-", 0x2014: "-"}


def squash(text: str) -> str:
    """Letters and digits only, upper case: robust to spacing, line breaks and punctuation spacing."""
    return re.sub(r"[^A-Z0-9]", "", text.translate(QUOTES).upper())


def squash_words(text: str) -> list[str]:
    return [w for w in (squash(t) for t in text.split()) if w]


def in_order(needle: list[str], words: list[str], max_gap: int = 60) -> bool:
    """True when the needle's words occur in order in `words`, each within `max_gap` words of the previous."""
    joined = "".join(needle)
    for start in range(len(words)):
        if not joined.startswith(words[start]) and not words[start].startswith(needle[0]):
            continue
        # consume the needle letter by letter, word by word (a word on the page may hold several needle words)
        rest, i, gap = joined, start, 0
        while rest and i < len(words) and gap <= max_gap:
            w = words[i]
            if rest.startswith(w):
                rest, gap = rest[len(w):], 0
            elif w.startswith(rest):
                rest = ""
            else:
                gap += 1
            i += 1
        if not rest:
            return True
    return False


def main(folders: list[str]) -> int:
    problems = total = 0
    for folder in folders:
        for key_file in sorted(Path(folder).glob("*.json")):
            key = json.loads(key_file.read_text())
            doc = pymupdf.open(ROOT / key["source_pdf"])
            for s in key["sets"]:
                pages = s.get("pages") or []
                text = squash(" ".join(doc[p - 1].get_text() for p in pages))
                checks = [("set_number", s["set_number"])]
                if s.get("description"):
                    checks.append(("set description", s["description"]))
                for c in s["components"]:
                    checks += [(f, c[f]) for f in FIELDS if c.get(f)]
                    if c.get("qty") is not None:
                        checks.append(("qty", str(int(c["qty"])) if float(c["qty"]).is_integer() else str(c["qty"])))
                words = [w for w in (squash(w[4]) for p in pages for w in doc[p - 1].get_text("words")) if w]
                for field, value in checks:
                    total += 1
                    if squash(str(value)) in text:
                        continue
                    if in_order(squash_words(str(value)), words):
                        continue  # words of a table cell interleaved with other columns in the page's text order
                    problems += 1
                    print(f"{key_file.parent.name}/{key_file.name} set {s['set_number']} p{pages}: "
                          f"{field} {value!r} not found on the page")
    print(f"\n{total} values checked, {problems} not found on their page")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or [str(ROOT / "eval" / "answer_key"), str(ROOT / "eval" / "holdout_key")]))
