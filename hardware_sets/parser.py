"""Turn the lines of the hardware pages into sets and components.

Walks the lines in reading order (page by page, top to bottom). Each line is one of:
  - a set title            -> starts a new set
  - a column header row    -> (re)defines the columns
  - a component row        -> starts a new component (it has a quantity, or is a "by others" item)
  - a continuation line    -> wrapped text of the component above
  - door / description / note lines around the components
Sets continue across page breaks; running page headers and footers are removed
before this step (see furniture.py).
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from . import patterns as P
from .codes import CodeBook
from .columns import ColumnModel, chunk_words, infer_columns, parse_header
from .pdf_text import Line, Word


@dataclass
class RawLine:
    line: Line
    kind: str                       # "start", "cont" or "note"
    qty: Word | None = None
    unit: Word | None = None
    by_others: bool = False
    qty_extra: list[Word] = field(default_factory=list)  # second word of "As Req."


@dataclass
class RawComponent:
    lines: list[RawLine]
    model: ColumnModel


@dataclass
class RawSet:
    set_number: str
    lines: list[Line] = field(default_factory=list)
    description: list[str] = field(default_factory=list)
    not_used: bool = False
    doors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    components: list[RawComponent] = field(default_factory=list)
    state: str = "pre"              # pre -> parts -> post
    expecting_doors: bool = False
    door_block: bool = False         # "For use on Door #(s):" with the list on the following lines
    in_door_list: bool = False       # the previous line was a line of door numbers
    header_seen: bool = False        # a column header row appeared inside this set
    pending: list[Line] = field(default_factory=list)  # table-column text seen before the first component
    also: list[str] = field(default_factory=list)      # other set numbers sharing the title ("#B1 and #B2")
    from_table_column: bool = False  # set number came from a SET column (table format)


# ---------------------------------------------------------------------------
# Pass 0: learn where quantities and columns are in this book
# ---------------------------------------------------------------------------
@dataclass
class BookLayout:
    qty_x: float | None
    inferred: ColumnModel | None


def _leading_qty(words: list[Word], book: CodeBook) -> tuple[Word | None, Word | None, list[Word]]:
    """Split '3 EA HINGE ...' into (qty word, unit word, remaining words)."""
    qty = unit = None
    rest = list(words)
    if rest and P.QTY.match(rest[0].text):
        qty = rest.pop(0)
    if rest and book.unit(rest[0].text) and (qty is not None or len(rest) > 1):
        unit = rest.pop(0)
    return qty, unit, rest


def learn_layout(lines: list[Line], book: CodeBook, page_width: float) -> BookLayout:
    candidates = []
    for ln in lines:
        w0 = ln.words[0]
        if len(ln.words) < 2 or not re.match(r"^\d{1,3}(?:\.\d{1,2})?$", w0.text):
            continue
        if w0.x0 > 0.45 * page_width or P.DOOR_LINE.match(ln.text) or len(ln.chunks()) < 2:
            continue
        candidates.append(ln)
    if not candidates:
        return BookLayout(None, None)
    qty_x = statistics.median(ln.words[0].x0 for ln in candidates)
    rows = []
    for ln in candidates:
        if abs(ln.words[0].x0 - qty_x) > 12:
            continue
        _, _, rest = _leading_qty(ln.words, book)
        rows.append(rest)
    return BookLayout(qty_x, infer_columns(rows, book))


# ---------------------------------------------------------------------------
# Pass 1: segment lines into sets and components
# ---------------------------------------------------------------------------
class Segmenter:
    def __init__(self, book: CodeBook, layout: BookLayout):
        self.book = book
        self.layout = layout
        self.sets: list[RawSet] = []
        self.cur: RawSet | None = None
        self.header: ColumnModel | None = None
        self.last_line: Line | None = None
        self.prev_line: Line | None = None
        self.prev_was_start = False      # the previous line started a component
        self.recent: list[str] = []   # the last few lines before a title
        self.skipping = False          # inside a sample format (not a real set)

    # -- helpers -------------------------------------------------------------
    @property
    def model(self) -> ColumnModel | None:
        return self.header or self.layout.inferred

    def _close(self) -> None:
        if self.cur is not None:
            self.sets.append(self.cur)
        self.cur = None

    def _new_set(self, number: str, line: Line) -> RawSet:
        self._close()
        self.cur = RawSet(set_number=number, lines=[line])
        return self.cur

    def _qty_x(self) -> float | None:
        if self.header is not None:
            return self.header.x_of("qty")
        return self.layout.qty_x

    def _text_x(self) -> float | None:
        m = self.model
        return m.text_start if m is not None else None

    def _start_row(self, line: Line) -> RawLine | None:
        """Is this line the first line of a component? (It has a quantity in the quantity column.)"""
        words = line.words
        if P.DOOR_LINE.match(line.text) or P.OUTLINE_PARAGRAPH.match(line.text):
            return None
        model = self.model
        if model is not None and model.source == "header" and not model.qty_is_first and model.has("qty"):
            # Table where quantity is a middle column (Roselle): look inside that column.
            # The product text can run into the quantity column ("..., A 1"), so look for the number itself.
            qty = next((w for w in words if model.role_at(w.x0) == "qty" and P.QTY.match(w.text)), None)
            return RawLine(line, "start", qty=qty) if qty is not None else None
        w0 = words[0]
        qty_x, text_x = self._qty_x(), self._text_x()
        if len(words) >= 3 and P.AS_REQUIRED.match(f"{words[0].text} {words[1].text}") \
                and (text_x is None or words[1].x1 < text_x):
            return RawLine(line, "start", qty=w0, qty_extra=[words[1]])  # quantity "As Req." -> null
        if P.QTY.match(w0.text) and len(words) >= 2:
            if text_x is not None and w0.x0 >= text_x - 2:
                return None      # a number inside the text columns ("24 VDC" wrapped under a catalog number)
            if qty_x is not None and abs(w0.x0 - qty_x) > 15 and (text_x is None or w0.x0 > text_x):
                return None
            if P.QTY_PLACEHOLDER.match(w0.text) and len(line.chunks()) < 2:
                return None
            qty, unit, _ = _leading_qty(words, self.book)
            return RawLine(line, "start", qty=qty, unit=unit)
        # No quantity, but the row has its own description and its own maker/finish value: a separate item
        # ("DIAGRAMS  PROVIDE FACTORY POINT TO POINT WIRING DIAGRAMS  B/O", hospital and Oswego).
        # A wrapped line of the row above never repeats a maker or finish.
        if model is not None and model.columns and text_x is not None and abs(w0.x0 - text_x) <= 8 \
                and not P.PART_NOTE_LABEL.match(line.text):
            coded = [w for w in words if model.role_at(w.x0) in ("mfr", "finish")]
            if coded and all(self.book.is_known_mfr(w.text) or self.book.finish_score(w.text) >= 0.7 for w in coded):
                return RawLine(line, "start")
        # Quantity missing but the unit is there ("EA  AUTOMATIC OPERATOR", hospital)
        if self.book.unit(w0.text) and len(line.chunks()) >= 2 and text_x is not None and w0.x0 < text_x - 4:
            return RawLine(line, "start", unit=w0)
        # "By others" items often carry no quantity (JC Ryan: "Hanging Device   By Balanced Door Manufacturer";
        # hospital: "SEALS   BY DOOR / FRAME MANUFACTURER"). In header tables the line must also have a description,
        # so a wrapped "BY ..." catalog line is not mistaken for a new item.
        if model is not None and text_x is not None and w0.x0 >= text_x - 10:
            chunks = chunk_words(words)
            later = [c for c in chunks if c[0].x0 > text_x + 40]
            has_description = chunks[0][0].x0 < text_x + 40
            prev = self.prev_line
            half_line_below = (self.prev_was_start and prev is not None and prev.page == line.page
                               and 0 < line.yc - prev.yc < 0.75 * line.height)  # lower half of a centred row
            if later and P.BY_OTHERS.match(" ".join(w.text for w in later[0])) and not half_line_below \
                    and (model.source == "inferred" or has_description):
                return RawLine(line, "start", by_others=True)
        return None

    def _doors_from(self, text: str) -> list[str]:
        tokens = [t for t in re.split(r"[,\s;]+", text) if t]
        return [t for t in tokens if P.DOOR_TOKEN.match(t) and re.search(r"\d", t)]

    def _is_door_number_line(self, line: Line) -> bool:
        """A line made only of door numbers ("120  157")."""
        tokens = [t for t in re.split(r"[,\s;]+", line.text) if t]
        return bool(tokens) and len(tokens) <= 24 and all(
            P.DOOR_TOKEN.match(t) and re.search(r"\d", t) for t in tokens
        )

    def _clearly_a_part(self, line: Line) -> bool:
        """A component row beyond doubt: a quantity followed by a unit ("3 EA HINGE"), or ending in a known code."""
        start = self._start_row(line)
        if start is None:
            return P.OPENING_PHRASE.match(line.text) is not None
        last = " ".join(w.text for w in line.chunks()[-1])
        return start.unit is not None or self.book.is_known_mfr(last) or self.book.is_known_finish(last)

    # -- main loop -----------------------------------------------------------
    def feed(self, line: Line) -> None:
        """Take the next line of the hardware pages and decide what it is."""
        text = line.text.strip()
        prev = self.last_line
        self.prev_line = prev
        self.last_line = line
        if prev is not None and line.page - prev.page > 1:
            self._close()  # pages in between were not hardware pages
        if self._section_break(line, text) or self._header_row(line, text) or self._set_title(line, text):
            return
        self.recent = (self.recent + [text])[-3:]
        if self.skipping:
            return
        if self.header is not None and self.header.has("set"):
            # Table format: the set number sits in a SET column (Roselle).
            line = self._take_set_column(line)
            if line is None:
                return
            text = line.text.strip()
        cur = self.cur
        if cur is None:
            return
        if cur.state == "post" and (P.OUTLINE_PARAGRAPH.match(text) or len(cur.notes) > 40):
            self._close()  # ran past the end of the sets into ordinary spec text
            return
        cur.lines.append(line)
        self._classify(cur, line, text)

    # -- the kinds of line, checked in this order ----------------------------
    def _section_break(self, line: Line, text: str) -> bool:
        """End of the spec section, or the start of the next one: the sets are over."""
        if not (P.SECTION_END.match(text) or P.NEW_SECTION.search(text)):
            return False
        if P.NEW_SECTION.search(text) and self.cur is not None:
            # Spec sections start on a new page: nothing on this page belongs to the set above.
            self.cur.components = [c for c in self.cur.components if c.lines[0].line.page != line.page]
            self.cur.lines = [ln for ln in self.cur.lines if ln.page != line.page]
        self._close()
        self.header = None
        return True

    def _header_row(self, line: Line, text: str) -> bool:
        """A column header row ("QTY  DESCRIPTION  CATALOG NUMBER  FINISH  MFR") sets the columns."""
        header = parse_header(line)
        if header is not None:
            self.header = header
            if self.cur is not None:
                self.cur.header_seen = True
                self.cur.door_block = False
            return True
        # the rest of a header word split over two lines ("QT" / "Y")
        return self.cur is not None and self.cur.state == "pre" and text.upper() in {"Y", "TY", "Y."}

    def _set_title(self, line: Line, text: str) -> bool:
        """A set title ("Hardware Group No. 01", "Set: 1.0", ...) starts a new set."""
        heading = P.match_heading(text)
        if heading is None or self._looks_like_component(line):
            return False
        if any(P.SAMPLE.search(t) for t in self.recent):
            self._close()                 # a sample format printed in the instructions, not a set
            self.skipping = True
            return True
        self.skipping = False
        s = self._new_set(heading.set_number, line)
        s.also = heading.also
        rest = heading.rest
        if not rest:
            return True
        if P.is_not_used(rest):
            s.not_used = True
        elif rest.startswith("["):
            s.notes.append(rest)          # revision note on the title: "[BULLETIN 023, 251218]"
        elif P.MOVED.search(rest):
            s.not_used = True             # "Moved to Exterior Set HW E18": the reason, not a name
            s.notes.append(rest)
        else:
            s.description.append(rest)
        return True

    def _looks_like_component(self, line: Line) -> bool:
        return bool(P.QTY.match(line.words[0].text)) and len(line.words) > 1

    def _take_set_column(self, line: Line) -> Line | None:
        header = self.header
        assert header is not None
        set_words = [w for w in line.words if header.role_at(w.x0) == "set"]
        others = [w for w in line.words if header.role_at(w.x0) != "set"]
        if set_words:
            label = " ".join(w.text for w in set_words)
            if re.fullmatch(P.SET_ID, label):
                s = self._new_set(label, line)
                s.from_table_column = True
                s.state = "parts"
            elif self.cur is not None and self.cur.from_table_column:
                self.cur.description.append(label)
        if not others:
            if self.cur is not None and line not in self.cur.lines:
                self.cur.lines.append(line)
            return None
        return Line(line.page, others, line.glyphs)

    def _classify(self, cur: RawSet, line: Line, text: str) -> None:
        """A line inside a set: door information, a new component, or text around the components."""
        if self._door_information(cur, line, text):
            return
        start = self._start_row(line)
        self.prev_was_start = start is not None
        if start is not None:
            self._add_component(cur, start)
        elif cur.state == "pre":
            if self._qtyless_row(cur, line, text):
                self._add_component(cur, RawLine(line, "start"))
            else:
                self._classify_pre(cur, line, text)
        else:
            self._classify_after_first_part(cur, line, text)

    def _door_information(self, cur: RawSet, line: Line, text: str) -> bool:
        """Door lines and door lists are not components."""
        if P.DOOR_LINE.match(text):   # "1 Pair Doors #101 ...", "Item #1 1 Single door 101, ..."
            m = re.search(r"doors?\s*#?\s*([\w\-]+)", text, re.I)
            if m:
                cur.doors.extend(self._doors_from(m.group(1)))
            return True
        if cur.state != "pre":
            return False
        if cur.door_block and not self._clearly_a_part(line):
            # Everything between "For use on Door #(s):" and "Provide each ..." / the header row is the door list,
            # even when it is a grid of room names ("CLASSROOM / 119", "ENGLISH / CLASSROOM / 116", Lyons).
            cur.doors.extend(self._doors_from(text))
            return True
        right_under_title = not cur.components and not cur.header_seen and len(cur.lines) <= 3
        if (cur.expecting_doors or right_under_title or cur.in_door_list) and self._is_door_number_line(line):
            # a wrapped "Doors:" list, or bare door numbers under the title, over one or more lines (National)
            cur.doors.extend(self._doors_from(text))
            cur.in_door_list = True
            return True
        cur.in_door_list = False
        return False

    def _classify_after_first_part(self, cur: RawSet, line: Line, text: str) -> None:
        """After the first component: wrapped text, part notes, or notes for the whole set."""
        text_x = self._text_x() or line.x0
        last = cur.components[-1].lines[-1].line
        far_below = last.page == line.page and line.y0 - last.y1 > 2.5 * line.height
        if P.SET_NOTE_LABEL.match(text) and not (cur.state == "parts" and P.PART_NOTE_LABEL.match(text)
                                                 and line.x0 >= text_x - 4):
            self._set_note(cur, text)
            return
        if cur.state == "post":
            if self._row_after_notes(line, text):
                self._add_component(cur, RawLine(line, "start"))   # "DIAGRAMS  PROVIDE FACTORY ..." after NOTE rows
            else:
                cur.notes.append(text)
            return
        if self._centred_quantity(cur, line, text, text_x) or self._sub_heading(cur, line, text, text_x):
            return
        if P.PART_NOTE_LABEL.match(text):
            if self._is_set_note(line, text):
                self._set_note(cur, text)
            else:
                cur.components[-1].lines.append(RawLine(line, "note"))
            return
        prev_raw = cur.components[-1].lines[-1]
        if prev_raw.kind == "note" and line.x0 >= prev_raw.line.x0 - 2 and not far_below:
            cur.components[-1].lines.append(RawLine(line, "note"))  # a note wrapping onto a second line
            return
        qty_x = self._qty_x()
        at_left_margin = line.x0 < text_x - 10 and (qty_x is None or line.x0 < qty_x - 3)
        if at_left_margin or self._is_prose(line) or far_below:
            self._set_note(cur, text)
            return
        model = self.model
        if model is not None and model.has("set") and model.has("notes") \
                and all(model.role_at(w.x0) == "notes" for w in line.words):
            cur.notes.append(text)  # a separate grid row with only a NOTES entry ("COORDINATE W/ ... MFR.", Roselle)
            return
        cur.components[-1].lines.append(RawLine(line, "cont"))  # the part's text wrapping onto the next line

    def _row_after_notes(self, line: Line, text: str) -> bool:
        """A table row that comes after the set's NOTE rows (hospital: "DIAGRAMS | PROVIDE FACTORY POINT TO ...").
        It must line up exactly with the description and catalog columns; a note does not."""
        model = self.model
        if model is None or P.PART_NOTE_LABEL.match(text) or P.SET_NOTE_LABEL.match(text):
            return False
        desc_x, cat_x = model.x_of("description"), model.x_of("catalog")
        chunks = line.chunks()
        return (desc_x is not None and cat_x is not None and len(chunks) >= 2
                and abs(chunks[0][0].x0 - desc_x) <= 4 and abs(chunks[1][0].x0 - cat_x) <= 6)

    def _set_note(self, cur: RawSet, text: str) -> None:
        cur.state = "post"
        cur.notes.append(text)

    def _centred_quantity(self, cur: RawSet, line: Line, text: str, text_x: float) -> bool:
        """The row's quantity printed on its own, centred between two text lines (JC Ryan "Door Closer")."""
        first = cur.components[-1].lines[0]
        start = next((rl for rl in cur.components[-1].lines if rl.kind == "start"), None)
        if (len(line.words) == 1 and P.QTY.match(text) and start is not None and start.qty is None
                and line.x0 < text_x - 2                      # in the quantity column, not a wrapped "13"
                and line.page == first.line.page and line.yc - first.line.yc < 1.5 * line.height):
            start.qty = line.words[0]
            cur.components[-1].lines.append(RawLine(line, "cont", qty=line.words[0]))
            return True
        return False

    def _sub_heading(self, cur: RawSet, line: Line, text: str, text_x: float) -> bool:
        """Text starting where quantities start, without a quantity, is not a wrapped cell (those start in the
        text column): a sub-heading such as "Hardware provided by Section 08 71 00" (JC Ryan)."""
        qty_x = self._qty_x()
        starts_at_qty = qty_x is not None and abs(line.x0 - qty_x) <= 3 and not P.QTY.match(line.words[0].text)
        if len(line.chunks()) == 1 and (starts_at_qty or (text.endswith(":") and line.x0 < text_x - 4)):
            self._set_note(cur, text)
            return True
        return False

    def _in_table(self, line: Line) -> bool:
        text_x = self._text_x()
        return text_x is not None and line.x0 >= text_x - 4

    def _qtyless_row(self, cur: RawSet, line: Line, text: str) -> bool:
        """A component row with no quantity, before any component of the set.

        - under a column header: any line inside the table ("ALL HARDWARE BY DOOR MANUFACTURER", hospital)
        - without a header: a line with text in two or more columns ("Specialty Door ... 00", Livelle)
        """
        if not self._in_table(line) or P.OPENING_PHRASE.match(text) or P.DESCRIPTION_LABEL.match(text):
            return False
        if cur.header_seen:
            return True
        model = self.model
        if model is None or model.source != "inferred":
            return False
        chunks = line.chunks()
        first = " ".join(w.text for w in chunks[0])
        if len(chunks) < 2 or first.endswith(":") or first[:1].islower():
            return False  # a label and its value ("Opening Description:  3' 0" x 8' 0"), or running text
        roles = {model.role_at(c[0].x0) for c in chunks}
        return len(roles) >= 2 and "description" in roles

    def _classify_pre(self, cur: RawSet, line: Line, text: str) -> None:
        if P.DESCRIPTION_LABEL.match(text):
            cur.description.append(P.DESCRIPTION_LABEL.sub("", text).strip())
            return
        m = P.DOOR_LIST_LABEL.match(text)
        if m:
            # After an explicit "Doors:" label every listed token is a door, even odd ones ("2p57a").
            listed = [t for t in re.split(r"[,;\s]+", text[m.end():]) if re.search(r"\d", t)]
            cur.doors.extend(listed)
            cur.expecting_doors = True
            # "For use on Door #(s):" with nothing after it: the door list (possibly a grid of room names)
            # follows on the next lines, up to "Provide each ..." / the header row.
            cur.door_block = not listed and text.lower().startswith("for use on")
            return
        if P.is_not_used(text) and len(cur.lines) <= 2:
            cur.not_used = True        # "NOT USED" on the line right under the title
            return
        if P.OPENING_PHRASE.match(text):
            cur.expecting_doors = cur.door_block = False
            cur.notes.append(text)
            return
        if self._is_door_number_line(line) and (cur.expecting_doors or not cur.notes):
            cur.doors.extend(self._doors_from(text))
            return
        header_words = sum(1 for w in line.words if w.text.upper().strip(":.") in P.HEADER_WORDS)
        if cur.description and cur.description[-1].count("(") > cur.description[-1].count(")") \
                and header_words < len(line.words):
            cur.description[-1] += " " + text  # title wrapped onto a second line (Market View)
            return
        if self._in_table(line):
            cur.pending.append(line)
        cur.notes.append(text)

    def _is_set_note(self, line: Line, text: str) -> bool:
        """A note about the whole set rather than the row above it.

        - numbered notes: "Note: 1. Integrated Seals ... 2. Closer drop plates ..." (Morris)
        - a NOTE row of the table: the label alone in the description column, its text in the next column
          ("NOTE:  FURNISH 5BB1HW 5" X 4.5" HINGES AT DOORS OVER 3'0" WIDE", hospital)
        """
        after = P.PART_NOTE_LABEL.sub("", text).strip(" -")
        if re.match(r"^1[.)]\s", after):
            return True
        chunks = line.chunks()
        return len(chunks) >= 2 and bool(P.PART_NOTE_LABEL.fullmatch(" ".join(w.text for w in chunks[0]).strip()))

    def _is_prose(self, line: Line) -> bool:
        """Running text rather than a table row: a long line, or one run of words that crosses from one
        column into the next ("Both Doors Are Free Egress Out At All Times" under Bridgeport's last row).
        A wrapped table cell stays inside its own column."""
        chunks = line.chunks()
        model = self.model
        if model is None or len(chunks) != 1 or len(line.words) < 4:
            return False
        start_role = model.role_at(line.x0)
        if start_role not in ("description", "qty"):
            return False  # a long catalog cell may run on for lines and spread over the code columns (Commons Lane)
        if len(line.words) >= 12:
            return True
        later = [c.x for c in model.columns if c.x > line.x0 + 10 and c.role != start_role]
        return bool(later) and line.x1 > later[0] + 15

    def _add_component(self, cur: RawSet, start: RawLine) -> None:
        model = self.model
        if model is None:
            model = ColumnModel([], source="none")
        comp = RawComponent([start], model)
        # Vertically centred table cells: text can sit half a line *above* the row that carries the
        # quantity ("Hardware is furnished complete by" / "Specialty Door ... 00" / "Vendor", Livelle).
        if not cur.components and cur.notes and cur.pending:
            above = cur.pending[-1]
            if above.page == start.line.page and 0 < start.line.yc - above.yc < 0.75 * start.line.height \
                    and cur.notes[-1] == above.text.strip():
                cur.notes.pop()
                comp.lines.insert(0, RawLine(above, "cont"))
        if cur.components:
            prev = cur.components[-1]
            last = prev.lines[-1]
            # The row's own cells are empty where the line half a line above has text: that text is the top
            # half of this row's centred cells ("Fail Safe Rim Exit Device with | [12] 55 PE8875 ETMI" above
            # "1 ... Sargent", JC Ryan). A line a full row above belongs to the previous row.
            # Same when another cell is centred: "K1050 F =34" high BEV CSK (F @" half a line above
            # "1 Armor Plate", "rated)" half a line below (Livelle set 45.0); finish "Dark" / "Bronze" around
            # "1 Seal Kit" (set 106.0). The line must sit nearer this row than the line above it, and fill
            # only cells this row leaves empty.
            mine, theirs = self._roles(start.line, start), self._roles(last.line, last)
            gap_above = last.line.yc - prev.lines[-2].line.yc if len(prev.lines) >= 2 else 0.0
            if (last.kind == "cont" and last.line.page == start.line.page
                    and start.line.yc - last.line.yc < 0.75 * start.line.height
                    and (("description" not in mine and "description" in theirs
                          and theirs <= {"description", "catalog", "notes"})
                         or (theirs and "description" not in theirs and not theirs & mine
                             and prev.lines[-2].line.page == last.line.page
                             and gap_above > 2 * (start.line.yc - last.line.yc)))):
                prev.lines.pop()
                comp.lines.insert(0, RawLine(last.line, "cont"))
        cur.components.append(comp)
        cur.state = "parts"
        cur.expecting_doors = cur.door_block = False

    def _roles(self, line: Line, raw: RawLine) -> set[str]:
        model = self.model
        if model is None or not model.columns:
            return set()
        skip = {id(raw.qty), id(raw.unit)} | {id(w) for w in raw.qty_extra}
        roles = {model.role_at(w.x0) for w in line.words if id(w) not in skip}
        return {"description" if r in ("qty", "unit") else r for r in roles}

    def _has_text_in(self, raw: RawLine, role: str) -> bool:
        model = self.model
        if model is None:
            return True
        skip = {id(raw.qty), id(raw.unit)}
        return any(model.role_at(w.x0) in (role, "qty") and id(w) not in skip for w in raw.line.words)

    def finish(self) -> list[RawSet]:
        self._close()
        return self.sets
