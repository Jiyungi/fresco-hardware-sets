"""Remove running page headers and footers ("DOOR HARDWARE  087100 - 19", copyright lines).

A line counts as page furniture when the same text (ignoring numbers) sits in the
top or bottom margin of many of the hardware pages. Removing it lets a set that
breaks across two pages read as one continuous list.
"""
from __future__ import annotations

import re
from collections import defaultdict

from . import patterns as P
from .columns import parse_header
from .pdf_text import Line

MARGIN = 0.12  # top and bottom 12% of the page
PAGE_NUMBER = re.compile(
    r"^(?:page\s+\d+(?:\s+of\s+\d+)?|\d{2}\s?\d{2}\s?\d{2}(?:\.\d+)?\s*[" + P.DASHES + r"]\s*\d+)$", re.I
)


def _key(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", text.lower())).strip()


def _protected(line: Line) -> bool:
    return (
        P.match_heading(line.text) is not None
        or bool(P.NEW_SECTION.search(line.text))
        or parse_header(line) is not None
        or bool(P.QTY.match(line.words[0].text) and len(line.chunks()) >= 2)
    )


def find_furniture(pages: dict[int, list[Line]], page_height: float) -> set[int]:
    """Return id()s of lines that are running headers/footers."""
    top, bottom = MARGIN * page_height, (1 - MARGIN) * page_height
    seen: dict[str, set[int]] = defaultdict(set)
    for page_no, lines in pages.items():
        for ln in lines:
            if ln.y1 <= top or ln.y0 >= bottom:
                seen[_key(ln.text)].add(page_no)
    needed = max(2, int(0.3 * len(pages)))
    repeated = {k for k, p in seen.items() if len(p) >= needed}

    out: set[int] = set()
    for lines in pages.values():
        for ln in lines:
            in_margin = ln.y1 <= top or ln.y0 >= bottom
            if not in_margin or _protected(ln):
                continue
            bare_number = ln.y0 >= bottom and ln.text.strip().isdigit()  # "13" at the top can be a wrapped value
            if _key(ln.text) in repeated or PAGE_NUMBER.match(ln.text.strip()) or bare_number:
                out.add(id(ln))
    return out
