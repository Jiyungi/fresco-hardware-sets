"""Run the whole extraction for one PDF."""
from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path

import pymupdf

from .assemble import Assembler
from .codes import CodeBook
from .columns import header_votes, infer_columns
from .furniture import find_furniture
from .lookup_tables import CodeTableReader
from .models import ExtractionResult, HardwareSet
from .page_finder import page_signals, select_pages
from .parser import Segmenter, _leading_qty, learn_layout
from .pdf_text import Line, drop_struck_words, read_page_lines


def extract_pdf(path: str | Path, pages: tuple[int, int] | None = None) -> ExtractionResult:
    """Extract every hardware set from a PDF. `pages` = (first, last), 1-based, limits the pages read."""
    path = Path(path)
    doc = pymupdf.open(path)
    book = CodeBook.load()
    tables = CodeTableReader()
    first, last = pages or (1, len(doc))

    # 1. Read every page once; keep the lines only for pages that might hold sets.
    signals, kept = {}, {}
    for page in (doc[i] for i in range(first - 1, min(last, len(doc)))):
        lines = read_page_lines(page)
        tables.feed_page(lines, page.rect.height)
        sig = page_signals(lines, book)
        signals[page.number + 1] = sig
        if sig.is_hardware or sig.maybe_continuation or sig.headings:
            kept[page.number + 1] = lines
    set_pages = [p for p in select_pages(signals) if p in kept]
    book.add_document_tables(tables.tables)
    result = ExtractionResult(source_file=str(path), page_count=len(doc), code_tables=tables.tables)
    if not set_pages:
        result.layout_notes.append("no hardware set pages found")
        return result

    # 2. Drop struck-out (deleted) text, and running headers/footers so sets flow across page breaks.
    for p in set_pages:
        kept[p] = drop_struck_words(doc[p - 1], kept[p])
    page_height = doc[set_pages[0] - 1].rect.height
    page_width = doc[set_pages[0] - 1].rect.width
    furniture = find_furniture({p: kept[p] for p in set_pages}, page_height)
    lines: list[Line] = [ln for p in set_pages for ln in kept[p] if id(ln) not in furniture]

    # 3. Learn the columns, then split the lines into sets and components. Each run of consecutive
    #    hardware pages is its own table (Morris has two sections with different column positions).
    raw_sets, layouts = [], []
    for run in _page_runs(lines):
        layout = learn_layout(run, book, page_width)
        layouts.append(layout)
        segmenter = Segmenter(book, layout)
        for ln in run:
            segmenter.feed(ln)
        raw_sets.extend(segmenter.finish())
    _learn_set_columns(raw_sets, book)
    _add_header_votes(raw_sets, book)

    # 4. Build the output.
    uses_glyphs = any(ln.glyphs for ln in lines)
    assembler = Assembler(book, tables.glyphs, uses_glyphs)
    sets = []
    for rs in raw_sets:
        hs = assembler.hardware_set(rs)
        sets.append(hs)
        for other in rs.also:  # "Hardware Group/Set #B1 and #B2": one list of components, two set numbers
            twin = copy.deepcopy(hs)
            twin.set_number = other
            twin.warnings.append(f"shares its title and components with set {hs.set_number}")
            sets.append(twin)
        if rs.also:
            hs.warnings.append(f"shares its title and components with set(s) {', '.join(rs.also)}")
    result.sets = _drop_empty_duplicates(_drop_false_sets(sets, result), result)
    _flag_duplicates(result.sets)

    result.layout_notes.append(f"hardware pages: {_ranges(set_pages)}")
    for layout in layouts:
        if layout.inferred is not None:
            result.layout_notes.append(f"columns learned from rows: {layout.inferred.describe()}")
    headers = {rc.model.describe() for rs in raw_sets for rc in rs.components if rc.model.source == "header"}
    for h in sorted(headers):
        result.layout_notes.append(f"columns from header row: {h}")
    return result


def _learn_set_columns(raw_sets, book: CodeBook) -> None:
    """Some books lay out each set's table with its own column positions (Commons Lane set 101 has its maker
    column at x=499 while the rest of the book has it at x=512). When a set without a header row has enough
    numbered rows, learn its columns from its own rows. The set's model is only used when it still finds the
    maker/finish columns the book-level model found; otherwise the book-level model stays."""
    for rs in raw_sets:
        comps = [rc for rc in rs.components if rc.model.source == "inferred"]
        starts = [rl for rc in comps for rl in rc.lines if rl.kind == "start" and rl.qty is not None]
        if len(starts) < 4:
            continue
        rows = []
        for rl in starts:
            skip = {id(rl.qty), id(rl.unit)} | {id(w) for w in rl.qty_extra}
            rows.append([w for w in rl.line.words if id(w) not in skip])
        model = infer_columns(rows, book)
        if model is None:
            continue
        book_roles = {c.role for c in comps[0].model.columns if c.role in ("finish", "mfr")}
        set_roles = {c.role for c in model.columns if c.role in ("finish", "mfr")}
        if book_roles <= set_roles and "description" in {c.role for c in model.columns}:
            # The labels come from this set's few values; how clearly makers and finishes separate is
            # better judged over the whole book, so keep the stronger of the two margins.
            model.label_margin = max(model.label_margin, comps[0].model.label_margin)
            for rc in comps:
                rc.model = model


def _add_header_votes(raw_sets, book: CodeBook) -> None:
    """Header tables name their own columns; still count maker/finish evidence for the confidence scores."""
    by_model: dict[int, tuple] = {}
    for rs in raw_sets:
        for rc in rs.components:
            if rc.model.source != "header":
                continue
            entry = by_model.setdefault(id(rc.model), (rc.model, []))
            for rl in rc.lines:
                if rl.kind == "start":
                    _, _, rest = _leading_qty(rl.line.words, book)
                    entry[1].append(rest)
    for model, rows in by_model.values():
        header_votes(model, rows, book)


def _drop_false_sets(sets: list[HardwareSet], result: ExtractionResult) -> list[HardwareSet]:
    """Keep empty sets only when they still look like a set title, not a sentence.

    A real title can have nothing under it (hospital sets 129 and 197 are followed by a blank page;
    Commons Lane E1 only has notes), so it is kept with a warning. A "title" that is really part of a
    sentence ("Hardware Group S52 Series, 200 pound capacity, with ...") is dropped.
    """
    kept = []
    for s in sets:
        words = (s.description or "").split()
        lower = sum(1 for w in words if w[:1].islower())
        sentence_like = len(words) > 12 or (len(words) >= 4 and lower / len(words) > 0.4)
        if s.components or s.not_used or not sentence_like:
            kept.append(s)
        else:
            page = s.location[0].page
            result.layout_notes.append(f"ignored title '{s.set_number}' on page {page}: no components")
    return kept


def _page_runs(lines: list[Line]) -> list[list[Line]]:
    """Split the lines where pages stop being consecutive."""
    runs: list[list[Line]] = []
    for ln in lines:
        if runs and ln.page - runs[-1][-1].page <= 1:
            runs[-1].append(ln)
        else:
            runs.append([ln])
    return runs


def _drop_empty_duplicates(sets: list[HardwareSet], result: ExtractionResult) -> list[HardwareSet]:
    """When a set number appears twice and one copy is only an empty reference to the other
    ("Hardware Group/Sets #103 and 104 - See Section 081713", Commons Lane), keep the copy with components."""
    with_parts = {s.set_number for s in sets if s.components}
    kept = []
    for s in sets:
        if not s.components and not s.not_used and s.set_number in with_parts:
            result.layout_notes.append(f"set {s.set_number} on page {s.location[0].page} only refers to the set "
                                       "printed elsewhere; kept the copy with components")
            continue
        kept.append(s)
    return kept


def _flag_duplicates(sets: list[HardwareSet]) -> None:
    counts = Counter(s.set_number for s in sets)
    for s in sets:
        if counts[s.set_number] > 1:
            s.warnings.append(f"set number {s.set_number} appears {counts[s.set_number]} times")


def _ranges(pages: list[int]) -> str:
    out, start, prev = [], pages[0], pages[0]
    for p in pages[1:] + [None]:
        if p is not None and p == prev + 1:
            prev = p
            continue
        out.append(f"{start}-{prev}" if start != prev else str(start))
        if p is not None:
            start = prev = p
    return ", ".join(out)
