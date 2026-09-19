"""Confidence scores: how likely each extracted value is to be right (0-1).

A score is the product of four simple checks, each one tied to a way values actually went wrong in testing
(see eval/report_confidence_*.txt):

  column fit   Does the value start where its column starts? A value sitting off its column edge is
               text overflowing from a neighbour or a table laid out differently (Commons Lane set 101).
  type fit     Does the value look like what belongs in that column? A maker code in the maker column,
               a finish code in the finish column, letters in a description ("37 38" is door numbers).
  row shape    Was the row one plain line, or pieced together (a quantity centred between two lines,
               text pulled from half a line above, a "By others" row without a quantity)?
  column vote  For maker and finish columns learned without a header row: how clearly the vote over
               the whole column separated makers from finishes.

A score below NEEDS_CHECK marks the value for review in the review screen and the CSV.
"""
from __future__ import annotations

import re

from .codes import CodeBook, FINISH_SHAPE, SHORT_CODE, code_key
from .columns import chunk_words

NEEDS_CHECK = 0.7


def column_fit(raw, role: str, parts) -> float:
    """1.0 when every piece of the value starts at its column edge, lower the further off it starts."""
    model = raw.model
    edges = [c.x for c in model.columns if c.role == role]
    if not edges:
        return 1.0
    worst = 0.0
    for rl in raw.lines:
        if rl.kind == "note":
            continue
        skip = {id(rl.qty), id(rl.unit)} | {id(w) for w in rl.qty_extra}
        for chunk in chunk_words([w for w in rl.line.words if id(w) not in skip]):
            if model.role_at(chunk[0].x0) == role and (not parts or rl.kind == "start"):
                worst = max(worst, min(abs(chunk[0].x0 - e) for e in edges))
    return 1.0 if worst <= 4 else 0.9 if worst <= 10 else 0.75


def row_shape(raw, start) -> float:
    lines = [rl for rl in raw.lines if rl.kind != "note"]
    pieced = (raw.lines[0].kind == "cont"                          # text pulled in from half a line above
              or any(rl.kind == "cont" and rl.qty is not None for rl in raw.lines)  # centred quantity
              or start.by_others)
    if pieced:
        return 0.8
    return 1.0 if len(lines) == 1 else 0.95


def mfr_type(value: str, book: CodeBook) -> float:
    k = code_key(value)
    if book.is_known_mfr(value):
        return 0.9 if book.is_known_finish(value) else 1.0
    if book.is_known_finish(value) or FINISH_SHAPE.match(k):
        return 0.45                                   # a finish in the maker column
    if len(value.split()) > 3:
        return 0.6                                    # a sentence, not a maker
    return 0.85 if SHORT_CODE.match(k) else 0.75


def finish_type(value: str, book: CodeBook) -> float:
    tokens = value.split()
    if book.is_known_finish(value):
        return 0.9 if book.is_known_mfr(value) else 1.0
    if len(tokens) >= 2 and any(book.is_known_mfr(t) for t in tokens[1:]):
        return 0.45                                   # "622 IV": the maker ran into the finish
    if FINISH_SHAPE.match(code_key(value)) or re.search(r"\(|black|bronze|chrome|gray|white", value, re.I):
        return 0.9
    if book.is_known_mfr(value):
        return 0.5                                    # a known maker code in the finish column
    return 0.6 if len(tokens) >= 2 else 0.8           # an unknown code ("EN", "BBLK"): fine, just not in the list


def score_component(c, raw, start, book: CodeBook) -> dict[str, float]:
    model = raw.model
    header = model.source == "header"
    shape = row_shape(raw, start)
    conf: dict[str, float] = {}

    if c.qty is not None:
        conf["qty"] = 0.97 if float(c.qty).is_integer() else 0.9
    elif start.qty is not None:
        conf["qty"] = 0.9                             # a printed placeholder: "--", "__", "*", "As Req."
    else:
        conf["qty"] = 0.8 if start.unit is not None else 0.75
    conf["qty"] *= 1.0 if shape == 1.0 else 0.95

    desc = c.description or ""
    if not desc:
        desc_type = 0.85 if c.catalog_number else 0.5
    elif not re.search(r"[A-Za-z]{2}", desc):
        desc_type = 0.4                               # only numbers: probably door numbers, not an item
    else:
        desc_type = 0.95
    conf["description"] = desc_type * column_fit(raw, "description", False) * shape
    conf["catalog_number"] = (0.95 if c.catalog_number else 0.85) * column_fit(raw, "catalog", False) * shape

    vote = 1.0 if header else 0.7 + 0.3 * min(1.0, model.label_margin if model.votes else 0.0)
    for role, value, typer in (("mfr", c.mfr, mfr_type), ("finish", c.finish, finish_type)):
        has_column = model.has(role) or (role == "mfr" and model.has("mfr_product"))
        if not has_column:
            conf[role] = 0.95 if value is None else 0.3   # the table has no such column: empty is expected
            continue
        if value is None:
            neighbour = c.finish if role == "mfr" else c.mfr
            swallowed = neighbour is not None and len(neighbour.split()) >= 2 and role == "mfr"
            conf[role] = (0.5 if swallowed else 0.9) * vote
            continue
        conf[role] = typer(value, book) * vote * column_fit(raw, role, True) * shape
    return {k: round(v, 2) for k, v in conf.items()}
