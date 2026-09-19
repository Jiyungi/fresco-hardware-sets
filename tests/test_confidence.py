"""The value checks behind the confidence score (hardware_sets/confidence.py)."""
from hardware_sets.codes import CodeBook
from hardware_sets.confidence import NEEDS_CHECK, finish_type, mfr_type

BOOK = CodeBook.load()


def test_a_maker_run_into_the_finish_scores_low():
    assert finish_type("622 IV", BOOK) < NEEDS_CHECK          # Commons Lane set 101 before the fix


def test_unknown_but_plausible_finish_codes_are_not_punished():
    assert finish_type("EN", BOOK) >= NEEDS_CHECK and finish_type("BBLK", BOOK) >= NEEDS_CHECK


def test_known_codes_in_the_right_column_score_high():
    assert finish_type("626", BOOK) == 1.0 and mfr_type("IVE", BOOK) == 1.0
    assert mfr_type("PE", BOOK) >= 0.9 and finish_type("PE", BOOK) >= 0.9   # ambiguous: the column decides


def test_a_finish_in_the_maker_column_scores_low():
    assert mfr_type("626", BOOK) < NEEDS_CHECK
