"""Code tables that some spec books print next to their hardware sets.

Examples: National Doors p.406 ("Abbreviation / Name": IVE = H.B. Ives, ...),
Forest Park pp.261-262 (MANUFACTURER LIST, OPTION LIST, FINISH LIST), and the
icon legend used by several books ("Electrified Opening", "Link to catalog cut sheet").
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .pdf_text import Line

_TITLES = [
    (re.compile(r"^(?:manufacturer(?:'?s)?|mfr\.?|mfg\.?)\s*(?:list|abbreviations?|legend|key|codes?)\s*:?$", re.I),
     "manufacturers"),
    (re.compile(r"^abbreviations?\s+(?:name|manufacturer)s?\s*:?$", re.I), "manufacturers"),
    (re.compile(r"^finish(?:es)?\s*(?:list|legend|key|abbreviations?|codes?)\s*:?$", re.I), "finishes"),
    (re.compile(r"^options?\s*(?:list|legend|key|abbreviations?|codes?)\s*:?$", re.I), "options"),
]
_COLUMN_TITLES = re.compile(r"^(?:code|abbreviation|abbr\.?)\s*:?\s+(?:name|description)\s*:?$", re.I)
_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/\-&.\" ]{0,14}$")

# Default meaning of the icon glyphs; books that print a legend override this.
DEFAULT_GLYPHS = {chr(0xF07E): "Electrified Opening", chr(0xF09D): "Link to catalog cut sheet"}


@dataclass
class CodeTableReader:
    """Reads code tables line by line as pages go past; tables may continue onto the next page."""

    tables: dict[str, dict[str, str]] = field(default_factory=dict)
    glyphs: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_GLYPHS))
    _kind: str | None = None
    _misses: int = 0
    _legend_lines_left: int = 0

    def feed_page(self, lines: list[Line], page_height: float) -> None:
        for line in lines:
            self._read_legend(line)
            in_margin = line.y1 < 0.12 * page_height or line.y0 > 0.88 * page_height
            self._feed(line, in_margin=in_margin)

    def _read_legend(self, line: Line) -> None:
        """Legend entries follow a "Legend:" line: one icon, then a short phrase ("<icon>Electrified Opening")."""
        if line.text.strip().lower() == "legend:":
            self._legend_lines_left = 6
            return
        if self._legend_lines_left <= 0:
            return
        self._legend_lines_left -= 1
        if len(line.glyphs) == 1 and 1 <= len(line.words) <= 6 and not re.search(r"\d", line.text):
            self.glyphs[line.glyphs[0][1]] = line.text.strip()

    def _feed(self, line: Line, in_margin: bool) -> None:
        text = line.text.strip()
        for pattern, kind in _TITLES:
            if pattern.match(text):
                self._kind, self._misses = kind, 0
                self.tables.setdefault(kind, {})
                return
        if self._kind is None:
            return
        if _COLUMN_TITLES.match(text):
            return
        chunks = line.chunks()
        if len(chunks) == 2:
            code = " ".join(w.text for w in chunks[0]).strip()
            name = " ".join(w.text for w in chunks[1]).strip()
            if _CODE.match(code) and len(name) > len(code) - 1 and not re.match(r"^\d+\.\d", code):
                self.tables[self._kind][code.upper()] = name
                self._misses = 0
                return
        if in_margin:
            return  # running page header/footer between the two halves of a table
        self._misses += 1
        if self._misses >= 2 or len(text) > 60:
            self._kind = None
