"""Decide which pages hold hardware sets.

Spec books can be thousands of pages; the sets usually sit on a few dozen. A page
qualifies when it has a set title *and* component-like rows, or several
component-like rows ending in maker/finish codes. Looking for both keeps out
sentences that merely resemble a title ("Group 1 (A1) stainless steel bolts").
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import patterns as P
from .codes import CodeBook
from .columns import parse_header
from .pdf_text import Line


@dataclass
class PageSignals:
    headings: int = 0
    not_used_headings: int = 0
    part_rows: int = 0
    coded_rows: int = 0
    column_header: bool = False
    set_column_header: bool = False

    @property
    def is_hardware(self) -> bool:
        if self.set_column_header:
            return True  # a table header with a SET column and hardware columns (Roselle)
        if self.headings and (self.part_rows >= 2 or self.coded_rows >= 1 or self.not_used_headings):
            return True
        if self.headings >= 2 and self.coded_rows >= 1:
            return True
        if self.column_header and self.part_rows >= 2:
            return True
        return self.part_rows >= 3 and self.coded_rows >= 2

    @property
    def weak(self) -> bool:
        """A title and one component-like row: a set page only when next to a clear set page."""
        return self.headings >= 1 and self.part_rows >= 1

    @property
    def maybe_continuation(self) -> bool:
        return self.part_rows >= 1 or self.coded_rows >= 1 or self.column_header


def page_signals(lines: list[Line], book: CodeBook) -> PageSignals:
    sig = PageSignals()
    for ln in lines:
        text = ln.text
        h = P.match_heading(text)
        if h is not None:
            sig.headings += 1
            sig.not_used_headings += P.is_not_used(h.rest)
            continue
        header = parse_header(ln)
        if header is not None:
            sig.column_header = True
            sig.set_column_header |= header.has("set")
            continue
        chunks = ln.chunks()
        first = ln.words[0].text
        by_others = len(chunks) >= 2 and P.BY_OTHERS.match(" ".join(w.text for w in chunks[-1]))
        looks_like_row = ((P.QTY.match(first) or book.unit(first)) and len(chunks) >= 2) or by_others
        if looks_like_row and not P.DOOR_LINE.match(text) and not re.match(r"^\d+\.\s", text) \
                and not P.OUTLINE_PARAGRAPH.match(text):
            sig.part_rows += 1
            last = " ".join(w.text for w in chunks[-1])
            if book.is_known_mfr(last) or book.is_known_finish(last):
                sig.coded_rows += 1
    return sig


def select_pages(signals: dict[int, PageSignals]) -> list[int]:
    """Hardware pages, plus neighbouring pages that continue the table or carry a lone set title."""
    core = {p for p, s in signals.items() if s.is_hardware}
    # Weak pages next to clear ones join them (repeat, so a run of weak pages is picked up).
    while True:
        more = {p for p, s in signals.items() if s.weak and p not in core and (p - 1 in core or p + 1 in core)}
        if not more:
            break
        core |= more
    chosen = set(core)
    for p in sorted(core):
        nxt = signals.get(p + 1)
        if nxt is not None and (nxt.maybe_continuation or nxt.headings):
            chosen.add(p + 1)
        before = signals.get(p - 1)
        if before is not None and before.headings:
            chosen.add(p - 1)
    return sorted(chosen)
