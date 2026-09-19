"""Read PDF pages into visual lines of words, each word with its position.

Coordinates are PDF points (1/72 inch) with the origin at the page's top-left
corner, the same system PyMuPDF uses. Page numbers are 1-based.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pymupdf

# Invisible characters that break text matching (zero-width space, soft hyphen, ...).
INVISIBLE = re.compile("[" + "".join(map(chr, (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD))) + "]")
# Icon-font glyphs (e.g. the "electrified opening" symbol) land in the Unicode
# private-use area. They are not text, so they are pulled out of the words and
# kept separately on the line.
PRIVATE_USE = re.compile("[" + chr(0xE000) + "-" + chr(0xF8FF) + "]")

TEXT_FLAGS = pymupdf.TEXT_PRESERVE_LIGATURES | pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_MEDIABOX_CLIP


@dataclass
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass
class Line:
    """Words that sit on the same visual row of a page, sorted left to right."""

    page: int
    words: list[Word]
    glyphs: list[tuple[float, str]] = field(default_factory=list)  # (x position, glyph)

    @property
    def x0(self) -> float:
        return self.words[0].x0

    @property
    def x1(self) -> float:
        return max(w.x1 for w in self.words)

    @property
    def y0(self) -> float:
        return min(w.y0 for w in self.words)

    @property
    def y1(self) -> float:
        return max(w.y1 for w in self.words)

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def height(self) -> float:
        return sorted(w.height for w in self.words)[len(self.words) // 2]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)

    def chunks(self) -> list[list[Word]]:
        """Split the line wherever the gap between two words is wider than a space."""
        out: list[list[Word]] = [[self.words[0]]]
        for a, b in zip(self.words, self.words[1:]):
            if b.x0 - a.x1 > max(4.0, 0.45 * a.height):
                out.append([b])
            else:
                out[-1].append(b)
        return out


def clean(text: str) -> str:
    return INVISIBLE.sub("", text).replace(chr(0xA0), " ").strip()


def _horizontal_line_keys(textpage: pymupdf.TextPage) -> set[tuple[int, int]]:
    """(block, line) numbers of text that runs left-to-right. Rotated margin text is dropped."""
    keys = set()
    for block in textpage.extractDICT()["blocks"]:
        for line_no, line in enumerate(block.get("lines", [])):
            dx, dy = line["dir"]
            if dx > 0.99 and abs(dy) < 0.01:
                keys.add((block["number"], line_no))
    return keys


def _text_char_starts(textpage: pymupdf.TextPage) -> list[tuple[float, float]]:
    """(left edge, vertical centre) of every real (non-icon) character on the page."""
    out = []
    for block in textpage.extractRAWDICT()["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                for ch in span["chars"]:
                    if not PRIVATE_USE.match(ch["c"]) and not ch["c"].isspace():
                        bx0, by0, _, by1 = ch["bbox"]
                        out.append((bx0, (by0 + by1) / 2))
    return out


def read_page_lines(page: pymupdf.Page) -> list[Line]:
    """Return the page's text as visual lines, top to bottom."""
    textpage = page.get_textpage(flags=TEXT_FLAGS)
    keep = _horizontal_line_keys(textpage)
    page_no = page.number + 1

    words: list[Word] = []
    glyphs: list[tuple[float, float, str]] = []  # (y center, x, glyph)
    char_starts: list[tuple[float, float]] | None = None
    for x0, y0, x1, y1, raw, block_no, line_no, _ in textpage.extractWORDS():
        if (block_no, line_no) not in keep:
            continue
        found = PRIVATE_USE.findall(raw)
        for g in found:
            glyphs.append(((y0 + y1) / 2, x0, g))
        text = clean(PRIVATE_USE.sub("", raw))
        if not text:
            continue
        if found and raw.lstrip("".join(found)) != raw:
            # An icon glued to the front of the word ("<icon>689"): use the real left edge of the
            # first letter, or the word lands in the column to the left.
            if char_starts is None:
                char_starts = _text_char_starts(textpage)
            yc = (y0 + y1) / 2
            x0 = min((cx for cx, cy in char_starts if x0 - 0.5 <= cx < x1 and abs(cy - yc) < 2.5), default=x0)
        words.append(Word(x0, y0, x1, y1, text))

    words.sort(key=lambda w: ((w.y0 + w.y1) / 2, w.x0))
    lines: list[Line] = []
    for w in words:
        yc = (w.y0 + w.y1) / 2
        tol = max(2.0, 0.35 * w.height)
        if lines and abs(lines[-1].yc - yc) <= tol:
            lines[-1].words.append(w)
        else:
            lines.append(Line(page_no, [w]))
    for line in lines:
        line.words.sort(key=lambda w: w.x0)
    for yc, x, g in glyphs:
        best = min(lines, key=lambda ln: abs(ln.yc - yc), default=None)
        if best is not None and abs(best.yc - yc) <= 4:
            best.glyphs.append((x, g))
    return lines


def _horizontal_segments(page: pymupdf.Page) -> list[tuple[float, float, float]]:
    """Thin horizontal strokes on the page as (x0, x1, y)."""
    segs = []
    for drawing in page.get_drawings():
        for item in drawing["items"]:
            if item[0] == "l" and abs(item[1].y - item[2].y) < 0.8:
                x0, x1 = sorted((item[1].x, item[2].x))
                segs.append((x0, x1, item[1].y))
            elif item[0] == "re" and item[1].height < 1.6 and item[1].width > 3:
                r = item[1]
                segs.append((r.x0, r.x1, (r.y0 + r.y1) / 2))
    return segs


def drop_struck_words(page: pymupdf.Page, lines: list[Line]) -> list[Line]:
    """Remove struck-out (deleted) words: a stroke through the middle of the word, not under it.

    Revised spec books strike out deleted sets and items (SJC, set HW 14B) instead of removing them.
    """
    segs = _horizontal_segments(page)
    if not segs:
        return lines
    out = []
    open_bracket = False  # a dropped line left a "[BULLETIN 023," revision tag open
    after_deleted_row = False
    for line in lines:
        kept = []
        for w in line.words:
            top, bottom = w.y0 + 0.35 * w.height, w.y0 + 0.72 * w.height
            width = max(w.x1 - w.x0, 0.1)
            through = [(x0, x1) for x0, x1, y in segs if top <= y <= bottom]
            struck = any((min(x1, w.x1) - max(x0, w.x0)) >= 0.6 * width for x0, x1 in through)
            if not struck:
                kept.append(w)
                continue
            # The stroke may miss a bracket or comma at the word's edge: "(DOGGING," -> keep "(" (Valor).
            cw = width / len(w.text)
            left = [ch for i, ch in enumerate(w.text)
                    if not any(x0 <= w.x0 + (i + 0.5) * cw <= x1 for x0, x1 in through)]
            rest = "".join(left).strip()
            if rest and all(ch in "()[],;" for ch in rest):
                kept.append(Word(w.x0, w.y0, w.x0 + cw * len(rest), w.y1, rest))
        if not kept:
            after_deleted_row = True
            continue  # the whole line is struck out
        text = " ".join(w.text for w in kept)
        if open_bracket and re.fullmatch(r"[^\[\]]*\]", text):
            open_bracket = False
            continue  # the rest of a revision tag that belonged to a deleted row
        if kept and kept[0].text != line.words[0].text and len(kept) < 0.6 * len(line.words):
            # The row itself was deleted (its first word is struck). What is left is a revision tag
            # such as "[BULLETIN 023, 251218]" (hospital), which must not be glued onto the row above.
            # A line whose first word survives only lost some words ("Doors 100A, 100B" in Valor).
            open_bracket = text.count("[") > text.count("]")
            after_deleted_row = True
            continue
        if after_deleted_row and text.startswith("["):
            # the deleted row's revision tag printed on the next line
            open_bracket = text.count("[") > text.count("]")
            continue
        after_deleted_row = False
        open_bracket = False
        if all(all(ch in "()[],;" for ch in w.text) for w in kept):
            continue  # only stray punctuation survived: the row was deleted
        out.append(line if kept == line.words else Line(line.page, kept, line.glyphs))
    return out
