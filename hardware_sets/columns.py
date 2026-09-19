"""Which column of a hardware table is which.

Two ways to know the columns:
1. The table has a header row ("QTY  DESCRIPTION  CATALOG NUMBER  FINISH  MFR"):
   each header word marks where its column starts.
2. No header row (Livelle, Gerrard, Morris, ...): collect every component row in the
   book, find the x positions where text chunks keep starting, and treat each
   position as a column. The columns are then named from their contents:
   the first text column is the description, the next is the catalog number, and
   the short-code columns on the right are voted on as maker vs finish.

Maker vs finish is always decided per column, never per value, so an ambiguous
code like "PE" (Pemko, or Painted Enamel) takes the meaning of its column.
"""
from __future__ import annotations

import itertools
import statistics
from dataclasses import dataclass, field

from .codes import CodeBook
from .patterns import HEADER_WORDS
from .pdf_text import Line, Word

TOLERANCE = 6.0  # points a value may start to the left of its column's anchor


@dataclass
class Column:
    role: str   # set, qty, unit, description, catalog, mfr_product, finish, mfr, notes
    x: float    # left edge of the column


@dataclass
class ColumnModel:
    columns: list[Column]
    source: str  # "header" or "inferred"
    votes: dict[str, dict[str, float]] = field(default_factory=dict)  # role -> {"mfr": .., "finish": ..}
    label_margin: float = 1.0  # how clearly maker and finish columns were told apart (0..1)

    def __post_init__(self) -> None:
        self.columns.sort(key=lambda c: c.x)

    def role_at(self, x: float) -> str:
        role = self.columns[0].role
        for col in self.columns:
            if x >= col.x - TOLERANCE:
                role = col.role
            else:
                break
        return role

    def x_of(self, role: str) -> float | None:
        return next((c.x for c in self.columns if c.role == role), None)

    def has(self, role: str) -> bool:
        return any(c.role == role for c in self.columns)

    @property
    def qty_is_first(self) -> bool:
        first = [c.role for c in self.columns if c.role != "set"]
        return bool(first) and first[0] == "qty"

    @property
    def text_start(self) -> float:
        """Where the description (first text column) starts."""
        x = self.x_of("description")
        return x if x is not None else self.columns[0].x

    def describe(self) -> str:
        return ", ".join(f"{c.role}@{c.x:.0f}" for c in self.columns)


# ---------------------------------------------------------------------------
# 1. Header rows
# ---------------------------------------------------------------------------
def parse_header(line: Line) -> ColumnModel | None:
    """Return the column layout if this line is a table header row."""
    words = line.words
    found: dict[str, float] = {}
    for i, w in enumerate(words):
        key = w.text.upper().strip(":")
        role = HEADER_WORDS.get(key) or HEADER_WORDS.get(key + ".")
        if role is None:
            continue
        x = w.x0
        prev = words[i - 1].text.upper() if i else ""
        if role == "description" and key == "TYPE":
            if prev != "HARDWARE":
                continue
            x = words[i - 1].x0  # "HARDWARE TYPE"
        if role == "catalog" and key == "PRODUCT" and i >= 2 and words[i - 1].text == "-" \
                and words[i - 2].text.upper() == "MANUFACTURER":
            found.pop("mfr", None)
            found["mfr_product"] = words[i - 2].x0  # "MANUFACTURER - PRODUCT" (maker inside the product text)
            continue
        if role == "catalog" and key == "PART" and i + 1 < len(words) and words[i + 1].text.upper() != "NUMBER":
            continue
        found.setdefault(role, x)
    core = {"description", "catalog", "mfr_product"} & found.keys()
    other = {"qty", "finish", "mfr", "mfr_product"} & found.keys()
    if len(found) < 3 or not core or not other:
        return None
    # A header row is mostly header words, spread out in columns. A sentence that happens to
    # contain them ("NOTE: - Product shall be ... finish per catalog selections") is not.
    header_words = sum(1 for w in words if (HEADER_WORDS.get(w.text.upper().strip(":")) or w.text.upper() in
                                            {"NUMBER", "HARDWARE", "-", "NO.", "#"}))
    if header_words < 0.6 * len(words) or len(line.chunks()) < 3:
        return None
    return ColumnModel([Column(r, x) for r, x in found.items()], source="header")


# ---------------------------------------------------------------------------
# 2. Inferring columns from component rows
# ---------------------------------------------------------------------------
def chunk_words(words: list[Word], min_gap: float = 4.0) -> list[list[Word]]:
    """Split words into runs wherever the gap is wider than a normal space."""
    if not words:
        return []
    out = [[words[0]]]
    for a, b in zip(words, words[1:]):
        if b.x0 - a.x1 > max(min_gap, 0.45 * a.height):
            out.append([b])
        else:
            out[-1].append(b)
    return out


# When learning columns, only a clear gap separates columns: justified paragraphs (Commons Lane) have
# stretched word spaces that would otherwise look like extra column edges.
COLUMN_GAP = 8.0


def _cluster(xs: list[float], gap: float = 8.0) -> list[list[float]]:
    groups: list[list[float]] = []
    for x in sorted(xs):
        if groups and x - groups[-1][-1] <= gap:
            groups[-1].append(x)
        else:
            groups.append([x])
    return groups


def _is_short(values: list[str]) -> bool:
    if not values:
        return False
    words = statistics.mean(len(v.split()) for v in values)
    length = statistics.mean(len(v) for v in values)
    return words <= 2.2 and length <= 14


def infer_columns(rows: list[list[Word]], book: CodeBook) -> ColumnModel | None:
    """Work out the columns from component rows (each row given without its qty/unit words)."""
    rows = [r for r in rows if r]
    if len(rows) < 2:
        return None
    starts: list[float] = []
    for r in rows:
        starts.extend(c[0].x0 for c in chunk_words(r, COLUMN_GAP))
    min_support = max(2, int(0.06 * len(rows)))
    groups = [g for g in _cluster(starts) if len(g) >= min_support]
    if not groups:
        return None
    anchors = [sorted(g)[max(0, len(g) // 10)] for g in groups]

    values: dict[int, list[str]] = {i: [] for i in range(len(anchors))}
    for r in rows:
        for chunk in chunk_words(r, COLUMN_GAP):
            idx = _column_index(anchors, chunk[0].x0)
            values[idx].append(" ".join(w.text for w in chunk))

    roles = ["description"] + ["catalog"] * (len(anchors) - 1)
    # Short-code columns on the right are the maker / finish candidates.
    candidates: list[int] = []
    for i in range(len(anchors) - 1, 0, -1):
        if _is_short(values[i]) and len(candidates) < 3:
            candidates.append(i)
        else:
            break
    if len(anchors) >= 3 and len(candidates) == len(anchors) - 1:
        candidates = candidates[:-1]  # keep the column right after the description as the catalog number
    model = ColumnModel([Column(roles[i], anchors[i]) for i in range(len(anchors))], source="inferred")
    label_code_columns(model, {i: values[i] for i in candidates}, book)
    return model


def _column_index(anchors: list[float], x: float) -> int:
    idx = 0
    for i, a in enumerate(anchors):
        if x >= a - TOLERANCE:
            idx = i
    return idx


def column_votes(values: list[str], book: CodeBook) -> dict[str, float]:
    vals = [v for v in values if not book.is_empty(v)]
    if not vals:
        return {"mfr": 0.0, "finish": 0.0, "n": 0}
    return {
        "mfr": statistics.mean(book.mfr_score(v) for v in vals),
        "finish": statistics.mean(book.finish_score(v) for v in vals),
        "n": len(vals),
    }


def label_code_columns(model: ColumnModel, candidates: dict[int, list[str]], book: CodeBook) -> None:
    """Name the short-code columns maker / finish / notes by voting over all their values."""
    if not candidates:
        return
    ordered = sorted(model.columns, key=lambda c: c.x)
    votes = {i: column_votes(v, book) for i, v in candidates.items()}
    best, best_score = None, -1.0
    idxs = list(candidates)
    for mfr_i, fin_i in itertools.product([None] + idxs, [None] + idxs):
        if mfr_i is not None and mfr_i == fin_i:
            continue
        score = 0.0
        if mfr_i is not None:
            if votes[mfr_i]["mfr"] < 0.25:
                continue
            score += votes[mfr_i]["mfr"] - votes[mfr_i]["finish"]
        if fin_i is not None:
            if votes[fin_i]["finish"] < 0.25:
                continue
            score += votes[fin_i]["finish"] - votes[fin_i]["mfr"]
        if score > best_score:
            best, best_score = (mfr_i, fin_i), score
    mfr_i, fin_i = best or (None, None)
    for i in idxs:
        v = votes[i]
        if i == mfr_i or (i != fin_i and v["mfr"] >= 0.5 and v["mfr"] > v["finish"] + 0.3):
            role = "mfr"      # a second maker-like column (same column printed at another x in another section)
        elif i == fin_i or (v["finish"] >= 0.5 and v["finish"] > v["mfr"] + 0.3):
            role = "finish"
        else:
            role = "notes"    # e.g. door handing "RH"/"LH"
        ordered[i].role = role
        if i in (mfr_i, fin_i):
            model.votes[role] = v
    margins = [abs(votes[i]["mfr"] - votes[i]["finish"]) for i in (mfr_i, fin_i) if i is not None]
    model.label_margin = min(margins) if margins else 0.0


def header_votes(model: ColumnModel, rows: list[list[Word]], book: CodeBook) -> None:
    """For header tables the header names the columns; votes are still computed for confidence scores."""
    values: dict[str, list[str]] = {"mfr": [], "finish": []}
    for r in rows:
        for chunk in chunk_words(r):
            role = model.role_at(chunk[0].x0)
            if role in values:
                values[role].append(" ".join(w.text for w in chunk))
    for role, vals in values.items():
        if model.has(role):
            model.votes[role] = column_votes(vals, book)
    margins = [abs(v["mfr"] - v["finish"]) for v in model.votes.values() if v.get("n")]
    model.label_margin = min(margins) if margins else 0.5
