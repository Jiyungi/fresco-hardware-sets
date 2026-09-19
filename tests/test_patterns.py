"""Set titles, 'not used' markers, quantities and codes, using lines copied from the spec books."""
import pytest

from hardware_sets.codes import CodeBook
from hardware_sets.patterns import QTY, match_heading

EN_DASH = chr(0x2013)


@pytest.mark.parametrize("line, number, rest", [
    ("Hardware Group No. 01", "01", ""),                                   # hospital, AMI, SAT
    ("HARDWARE GROUP NO. 02", "02", ""),                                   # Oswego
    ("Set #AL 01", "AL 01", ""),                                           # Gerrard
    ("Set: EX-1.0", "EX-1.0", ""),                                         # JC Ryan
    ("Heading #1", "1", ""),                                               # Bridgeport
    ("HW 02A     Interior Single - Office", "02A", "Interior Single - Office"),  # SJC
    ("HW E01     NOT USED", "E01", "NOT USED"),                            # SJC exterior sets
    ("PART 6 - HARDWARE GROUP NO. 103", "103", ""),                        # Door Company (junk numbering)
    ("Set #CR38CLHO", "CR38CLHO", ""),                                     # Morris
    ("Hardware Group No. K201ACTW.1", "K201ACTW.1", ""),                   # SAT
    ("Hardware Group/Sets 102.1", "102.1", ""),                            # Commons Lane
    (f"Hardware Group/Set #A1 {EN_DASH} Entry Unit Doors", "A1", "Entry Unit Doors"),
    ("Hardware Group No. 04: (Doors U7 & U9 - Closets)", "04", "(Doors U7 & U9 - Closets)"),  # Valor
    ("Set: MISC", "MISC", ""),                                             # Livelle
])
def test_titles(line, number, rest):
    m = match_heading(line)
    assert m is not None and m.set_number == number and m.rest == rest


@pytest.mark.parametrize("line", [
    "Set blocks in thin course of sealant",         # prose
    "Group 1 (A1) stainless steel bolts",           # prose
    "Set 1 of keys shall be delivered",             # prose
    "hw 1 thing",                                   # lower-case HW is not a title
    "Hardware Sets",                                # no number
])
def test_not_titles(line):
    assert match_heading(line) is None


def test_two_sets_sharing_a_title():
    m = match_heading(f"Hardware Group/Set #B1 and #B2 {EN_DASH} Bedroom and Bathrooms")
    assert (m.set_number, m.also, m.rest) == ("B1", ["B2"], "Bedroom and Bathrooms")


def test_not_used_markers():
    from hardware_sets.patterns import is_not_used
    assert is_not_used("Not Used") and is_not_used("NOT USED") and is_not_used("set not utilized at this time")
    assert not is_not_used("Type AL-NA x N/A x HMF Type HM-NA-F1 with a long door description here")


@pytest.mark.parametrize("token, ok", [("3", True), ("1.0", True), ("__", True), ("--", True), ("*", True),
                                       ("24VDC", False), ("1.", False)])
def test_quantity_tokens(token, ok):
    assert bool(QTY.match(token)) == ok


def test_units():
    book = CodeBook.load()
    assert book.unit("EA") == "EA" and book.unit("Ea.") == "EA" and book.unit("Pair") == "PR"
    assert book.unit("EA-R") == "EA-R"          # Shubie prints unit variants
    assert book.unit("HINGE") is None


def test_ambiguous_codes_are_in_both_lists():
    """PE is Pemko or Painted Enamel; only the column can decide."""
    book = CodeBook.load()
    assert book.is_known_mfr("PE") and book.is_known_finish("PE")
