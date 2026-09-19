"""Build the final output objects from the segmented lines (confidence scores: see confidence.py)."""
from __future__ import annotations

import re
import statistics
from collections import defaultdict

from . import patterns as P
from .codes import CodeBook
from .columns import chunk_words
from .confidence import score_component
from .models import Box, Component, HardwareSet
from .parser import RawComponent, RawLine, RawSet
from .pdf_text import Line, Word

HANDING = re.compile(r"^(?:RH|LH|RHR|LHR|RHRA|LHRA|LHA|RHA)$")


def boxes(lines: list[Line]) -> list[Box]:
    per_page: dict[int, list[float]] = {}
    for ln in lines:
        x0, y0, x1, y1 = ln.bbox
        b = per_page.get(ln.page)
        if b is None:
            per_page[ln.page] = [x0, y0, x1, y1]
        else:
            per_page[ln.page] = [min(b[0], x0), min(b[1], y0), max(b[2], x1), max(b[3], y1)]
    return [Box(page, [round(v, 1) for v in bb]) for page, bb in sorted(per_page.items())]


def _catalog_right_edge(model) -> float:
    """The catalog column ends where the next column starts (or at the page's usual right margin)."""
    cat_x = model.x_of("catalog")
    nxt = next((c.x for c in model.columns if cat_x is not None and c.x > cat_x + 10), None)
    return (nxt - 4) if nxt is not None else 540.0


CELL_GAP = 12.0  # points; wider than any word space, so a gap this big separates two table cells


def _next_text_column(piece: list[Word], model) -> str:
    text = " ".join(w.text for w in piece)
    if len(text) < 3 and any(ch.isalnum() for ch in text):
        return "description"  # a stray fragment of a broken word ("m" of "m ail@...", Commons Lane set 27)
    nxt = next((c for c in model.columns if c.x > model.text_start and c.role != "description"), None)
    if nxt is None or nxt.role not in ("catalog", "mfr_product"):
        return "description"
    # A stretched word space in a justified description ("and      Dustproof Keeper", Commons Lane set 20) stays
    # near the left of the cell; a real second cell starts well across towards the next column.
    halfway = model.text_start + 0.45 * (nxt.x - model.text_start)
    return nxt.role if piece[0].x0 >= halfway else "description"


def _cut_at_column_edges(chunk: list[Word], model, book: CodeBook, tolerance: float = 3.0) -> list[list[Word]]:
    """Cut a run of words where a maker/finish code starts right at its column's edge ("side 689", SJC).
    Ordinary words that happen to end near an edge (a justified line ending in "x", Commons Lane) stay."""
    if not model.columns:
        return [chunk]
    edges = {c.x: c.role for c in model.columns if c.role in ("finish", "mfr")}
    pieces = [[chunk[0]]]
    for w in chunk[1:]:
        role = next((r for x, r in edges.items() if abs(w.x0 - x) <= tolerance), None)
        code_like = (role == "finish" and book.finish_score(w.text) >= 0.7) or \
            (role == "mfr" and book.is_known_mfr(w.text))
        if role and code_like and role != model.role_at(pieces[-1][0].x0):
            pieces.append([w])
        else:
            pieces[-1].append(w)
    return pieces


def _join(parts: list[str], role: str) -> str | None:
    out = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if not out:
            out = part
        elif role == "finish" and (out.endswith(("-", "/")) or re.fullmatch(r"[A-Za-z]{1,2}", part)):
            out += part          # "630-" + "316", "643" + "e", "ANCL" + "R"
        else:
            out += " " + part
    return out or None


def _qty_value(word: Word | None) -> float | None:
    if word is None or P.QTY_PLACEHOLDER.match(word.text):
        return None
    try:
        return float(word.text)
    except ValueError:
        return None


class Assembler:
    def __init__(self, book: CodeBook, glyphs: dict[str, str], uses_glyphs: bool):
        self.book = book
        self.glyphs = glyphs
        self.uses_glyphs = uses_glyphs

    def component(self, raw: RawComponent) -> Component:
        model = raw.model
        fields: dict[str, list[str]] = defaultdict(list)
        pulled_from_above = raw.lines[0].kind == "cont"
        start = next((rl for rl in raw.lines if rl.kind == "start"), raw.lines[0])
        in_remark = False  # inside a bracketed remark under the catalog number, possibly over several lines
        start_roles = set(self._split_line(start, model)) if start.kind == "start" else set()
        prev_catalog_end = None  # where the catalog text on the previous line ended
        for rl in raw.lines:
            if rl.kind == "note":
                text = rl.line.text.strip()
                if P.PART_NOTE_LABEL.match(text):
                    text = P.PART_NOTE_LABEL.sub("", text).strip().removeprefix("- ").strip()
                fields["notes"].append(text)  # a wrapped second bullet keeps its "- "
                continue
            per_line = self._split_line(rl, model)
            if rl.kind == "cont":
                for role in ("finish", "mfr"):
                    other = next((r for r in ("catalog", "description") if per_line.get(r)), None)
                    if per_line.get(role) and not fields[role] and other and role not in start_roles:
                        # A code at the end of a wrapped line of text, with nothing in that column on the row's
                        # first line, is the end of the sentence ("... locking device) in 625 / polished chrome
                        # finish", Commons Lane), not the row's finish or maker.
                        per_line[other] = per_line[other] + " " + per_line.pop(role)
            catalog_words = [w for w in rl.line.words if model.columns and model.role_at(w.x0) == "catalog"]
            if rl.kind == "cont" and per_line.get("catalog"):
                text = per_line["catalog"]
                words_above = len(" ".join(fields["catalog"]).split())
                short_value_above = words_above <= 5  # not mid-paragraph
                # "(FAIL SECURE)" starts a new line although it would have fitted after "VDC" on the line above:
                # a separate remark, not a wrapped catalog number (Door Company).
                # Only after a model number, not after a paragraph of prose (Commons Lane captions stay put).
                would_have_fit = (words_above <= 8 and prev_catalog_end is not None and catalog_words
                                  and prev_catalog_end + 6 + (catalog_words[-1].x1 - catalog_words[0].x0)
                                  < _catalog_right_edge(model))
                if in_remark or (text.startswith("(") and (short_value_above or would_have_fit)):
                    # "(PROVIDE NRP @ OUTSWING," / "LOCKABLE DOORS)" under the catalog number is a remark (SAT)
                    per_line["notes"] = (per_line.get("notes", "") + " " + per_line.pop("catalog")).strip()
                    in_remark = text.count("(") > text.count(")") or (in_remark and ")" not in text)
            if catalog_words:
                prev_catalog_end = max(w.x1 for w in catalog_words)
            for role, text in per_line.items():
                fields[role].append(text)

        c = Component(
            qty=_qty_value(start.qty),
            unit=self.book.unit(start.unit.text) if start.unit else None,
            description=_join(fields["description"], "description"),
            catalog_number=_join(fields["catalog"], "catalog"),
            finish=_join(fields["finish"], "finish"),
            mfr=_join(fields["mfr"], "mfr"),
            notes=_join(fields["notes"], "notes"),
        )
        if fields["mfr_product"]:
            self._split_mfr_product(c, _join(fields["mfr_product"], "mfr_product") or "")
        for name in ("description", "catalog_number", "finish", "mfr", "notes"):
            if self.book.is_empty(getattr(c, name)):
                setattr(c, name, None)
        c.mfr_name = self.book.mfr_name(c.mfr)
        c.finish_name = self.book.finish_name(c.finish)
        c.catalog_codes = self.book.option_names(c.catalog_number)
        c.electrified = self._electrified(raw)
        c.location = boxes([rl.line for rl in raw.lines])
        c.confidence = self._confidence(c, raw, start, pulled_from_above)
        return c

    def _split_line(self, rl: RawLine, model) -> dict[str, str]:
        """Put the words of one line into columns.

        Words that run together (normal spacing) stay in one column even if a long sentence runs past
        the next column's left edge (Commons Lane). A run is only cut where a word starts right at a
        column edge ("... mount on public side 689": 689 starts exactly at the Finish column, SJC).
        """
        words: dict[str, list[str]] = defaultdict(list)
        skip = {id(rl.qty), id(rl.unit)} | {id(w) for w in rl.qty_extra}
        last_role = "description"
        prev_end = None
        for chunk in chunk_words([w for w in rl.line.words if id(w) not in skip]):
            for piece in _cut_at_column_edges(chunk, model, self.book):
                role = model.role_at(piece[0].x0) if model.columns else "description"
                gap = piece[0].x0 - prev_end if prev_end is not None else 0.0
                if role == "description" and words.get("description") and gap >= CELL_GAP:
                    # A second run of text after a clear gap on a line that already has a description: the next
                    # cell, which in this row starts left of the usual column edge (Commons Lane sets 03 and 11).
                    role = _next_text_column(piece, model)
                if role == "description" and last_role in ("catalog", "mfr_product"):
                    role = last_role  # columns run left to right: text after the catalog is not description again
                prev_end = piece[-1].x1
                if role in ("qty", "unit") and rl.kind == "cont":
                    role = "notes"  # a revision tag squeezed into the quantity column ("[BUL" / "LETI", hospital)
                elif role in ("qty", "unit", "set"):
                    role = "description"
                if role in ("finish", "mfr") and model.source == "inferred" and len(piece) > 2:
                    role = last_role  # maker/finish codes are short; a run of words is text overflowing its column
                last_role = role
                if len(piece) == 1 and HANDING.match(piece[0].text) and role in ("catalog", "description"):
                    role = "notes"  # door handing ("RH", "LHR") printed in its own narrow column (Morris)
                words[role].extend(w.text for w in piece)
        return {role: " ".join(ws) for role, ws in words.items()}

    def _split_mfr_product(self, c: Component, text: str) -> None:
        """'SCHLAGE - L9077, 18 LEVER' -> maker SCHLAGE, catalog 'L9077, 18 LEVER' (Roselle)."""
        parts = re.split(r"\s+-\s+", text, maxsplit=1)
        if len(parts) == 2 and len(parts[0]) <= 40:
            c.mfr, c.catalog_number = parts[0].strip(), _join([parts[1], c.catalog_number or ""], "catalog")
        else:
            c.catalog_number = _join([text, c.catalog_number or ""], "catalog")

    def _electrified(self, raw: RawComponent) -> bool | None:
        if not self.uses_glyphs:
            return None
        meanings = [self.glyphs.get(g, "") for rl in raw.lines for _, g in rl.line.glyphs]
        return any("electri" in m.lower() for m in meanings)

    def _confidence(self, c: Component, raw: RawComponent, start: RawLine, pulled: bool) -> dict[str, float]:
        return score_component(c, raw, start, self.book)

    def hardware_set(self, raw: RawSet) -> HardwareSet:
        comps = [self.component(rc) for rc in raw.components]
        description = " ".join(d for d in raw.description if d).strip() or None
        doors = list(raw.doors)
        if description and description.startswith("("):
            # "(Door U1 - Interior Unit Entry Swing Doors)": drop the brackets around the name
            description = description[1:-1] if description.endswith(")") else description[1:]
            description = description.strip() or None
        m = P.DOOR_PREFIX.match(description or "")
        if m and re.search(r"\d", m.group("doors")):
            # door numbers are not the set's name: "Doors U11 & U12 - Mechanical Closet Swing Doors"
            doors += [t for t in re.split(r"[\s,&]+|\band\b", m.group("doors")) if re.search(r"\d", t)]
            description = (m.group("rest") or "").strip() or None
        hs = HardwareSet(
            set_number=raw.set_number,
            description=description,
            not_used=raw.not_used,
            doors=list(dict.fromkeys(doors)),
            set_notes=" ".join(raw.notes).strip() or None,
            location=boxes(raw.lines),
            components=comps,
        )
        if comps:
            hs.confidence = round(statistics.mean(statistics.mean(c.confidence.values()) for c in comps), 2)
        elif raw.not_used:
            hs.confidence = 0.9
        else:
            hs.confidence = 0.3
            hs.warnings.append("no components found")
        return hs
