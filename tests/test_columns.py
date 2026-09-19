"""Maker vs finish is decided per column by voting, never per value."""
from hardware_sets.codes import CodeBook
from hardware_sets.columns import Column, ColumnModel, label_code_columns, parse_header
from hardware_sets.pdf_text import Line, Word


def _model():
    return ColumnModel([Column("description", 90), Column("catalog", 260), Column("catalog", 440),
                        Column("catalog", 490)], source="inferred")


def test_pe_in_a_maker_column_is_a_maker():
    book = CodeBook.load()
    model = _model()
    label_code_columns(model, {2: ["US15", "689", "US15", "DCRM"], 3: ["MK", "SA", "NO", "PE", "PE", "RO"]}, book)
    assert [c.role for c in model.columns] == ["description", "catalog", "finish", "mfr"]


def test_pe_in_a_finish_column_is_a_finish():
    book = CodeBook.load()
    model = _model()
    label_code_columns(model, {2: ["PE", "626", "630", "US26D"], 3: ["IVE", "LCN", "SCH", "VON"]}, book)
    assert model.columns[2].role == "finish" and model.columns[3].role == "mfr"


def _line(*cells):
    return Line(1, [Word(x, 50, x + 8 * len(t), 60, t) for x, text in cells for t in [text]])


def test_header_row_is_recognised():
    line = _line((80, "QTY"), (142, "DESCRIPTION"), (271, "CATALOG"), (320, "NUMBER"), (471, "FINISH"), (512, "MFR"))
    model = parse_header(line)
    assert model is not None and [c.role for c in model.columns] == ["qty", "description", "catalog", "finish", "mfr"]


def test_a_note_mentioning_header_words_is_not_a_header():
    # Morris: "NOTE: - Product shall be US10B (or 10BE if available) finish per catalog selections"
    words = "NOTE: - Product shall be US10B (or 10BE if available) finish per catalog selections".split()
    line = Line(1, [Word(105 + 30 * i, 50, 130 + 30 * i, 60, w) for i, w in enumerate(words)])
    assert parse_header(line) is None
