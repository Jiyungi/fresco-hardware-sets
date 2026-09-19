"""End-to-end checks on real spec books. Each test names the difficulty it covers.

Skipped when the PDFs are not present (they are not part of the repository).
"""
from pathlib import Path

import pytest

from hardware_sets.extract import extract_pdf

ROOT = Path(__file__).resolve().parent.parent


def book(rel: str, pages=None):
    path = ROOT / rel
    if not path.exists():
        pytest.skip(f"{rel} not available")
    result = extract_pdf(path, pages)
    return {s.set_number: s for s in result.sets}, result


def test_maker_vs_finish_codes_resolved_by_column():
    sets, _ = book("Livelle Mulholland - Life Plan Community/2025-12-12_Livelle_Bid_Set_Project_Manual_Vol1_rev1.pdf",
                   (640, 701))
    comps = {c.description: c for c in sets["1.0"].components}
    assert comps["Surface Closer Cush Stop"].mfr == "NO"             # Norton, not the word "No."
    assert comps["Sound Gasketing"].mfr == "PE" and comps["Sound Gasketing"].finish is None   # Pemko
    assert comps["Viewer"].catalog_number == "626" and comps["Viewer"].finish == "DCRM"      # 626 is a model here


def test_struck_out_rows_are_dropped():
    # Page 43: set 035's GASKETING SET and MEETING STILE rows are struck out by a bulletin.
    sets, _ = book("HFH DG - HOSPITAL/08 71 00 - DOOR HARDWARE.pdf", (40, 45))
    struck_set = [c.description for c in sets["035"].components]
    assert "GASKETING SET" not in struck_set and "MEETING STILE" not in struck_set
    assert "GASKETING SET" in [c.description for c in sets["034"].components]   # live row on page 42 stays


def test_missing_quantities_are_null_not_guessed():
    sets, _ = book("HFH DG - HOSPITAL/08 71 00 - DOOR HARDWARE.pdf", (20, 22))
    auto = [c for c in sets["001"].components if c.description == "AUTOMATIC OPERATOR"][0]
    assert auto.qty is None and auto.unit == "EA"


def test_sets_split_across_pages_are_joined():
    sets, _ = book("HFH DG - HOSPITAL/08 71 00 - DOOR HARDWARE.pdf", (20, 22))
    s = sets["001"]
    assert [b.page for b in s.location] == [20, 21]
    assert not any("08 71 00" in (c.catalog_number or "") for c in s.components)   # page footer removed


def test_not_used_sets_are_kept():
    sets, _ = book("Lyons Township HS/Project Manual (1).pdf", (283, 295))
    assert sets["05"].not_used and sets["05"].components == []


def test_table_format_with_set_column():
    sets, _ = book("Roselle Public Library/087100_FL_-_Door_Hardware_IFB_REVISED.pdf")
    s = sets["1.2"]
    assert s.description == "CURTAINWALL EXTR ENTR SINGLE DOOR CARD READER"   # all words stacked in the SET column
    hinge = s.components[0]
    assert (hinge.qty, hinge.mfr, hinge.catalog_number) == (3, "IVES", '5BB1 4.5" x 4.5"')
    gasket = [c for c in s.components if c.description == "GASKETING / SWEEP"][0]
    assert gasket.qty is None                                           # printed as "--"


def test_rows_without_quantity_and_centred_cells():
    sets, _ = book("JC Ryan 2/087100 - Door Hardware-6.pdf", (20, 30))
    comps = sets["EX-1.0"].components
    assert [c.qty for c in comps] == [None, None, None, 1]
    assert comps[1].description == "Panic Hardware Device (Blumcraft Style)"


def test_files_without_sets_return_nothing():
    _, result = book("Valor Acres Building E/088000-GLAZING_Rev_1.pdf")
    assert result.sets == []


def test_two_sets_sharing_one_title():
    sets, _ = book("StarHardware/9839d1a1-Division_8_Specs_-_Commons_Lane.pdf")
    assert "B1" in sets and "B2" in sets
    assert len(sets["B1"].components) == len(sets["B2"].components) > 0


def test_bare_door_numbers_under_the_title_are_doors():
    # National p.409: "Hardware Group No. 07" is followed by a line of door numbers "2  5  25  33".
    sets, _ = book("National Doors and Hardware/15e2b8ac-FS17_Specs_V1.pdf", (405, 412))
    s = sets["07"]
    assert s.doors == ["2", "5", "25", "33"]
    assert all(c.description != "25" for c in s.components)


def test_row_without_quantity_but_with_its_own_maker_is_its_own_item():
    # Oswego p.434: "DIAGRAMS  PROVIDE FACTORY POINT TO POINT WIRING DIAGRAMS  B/O" under a row that has a quantity.
    sets, _ = book("Village of Oswego New Public Works Facility  _Copy_/SPECIFICATIONS VOLUME 1.pdf", (430, 436))
    diagrams = [c for c in sets["39"].components if c.description == "DIAGRAMS"]
    assert len(diagrams) == 1 and diagrams[0].qty is None and diagrams[0].mfr == "B/O"


def test_long_catalog_paragraph_stays_with_its_row():
    # Commons Lane p.84: the threshold's catalog text runs over four lines and across the finish column.
    sets, _ = book("StarHardware/9839d1a1-Division_8_Specs_-_Commons_Lane.pdf", (80, 86))
    threshold = [c for c in sets["13"].components if c.description == "Threshold"][0]
    assert threshold.catalog_number.endswith("by Pemko approved equal") and threshold.finish is None


def test_same_sets_printed_in_two_files_come_out_identical():
    # Gerrard's hardware sets appear in the hardware file and again in the full architectural book.
    small, _ = book("2353 Gerrard Street Shelter/Hdw Spec & Sch-IFT_5.pdf")
    full, _ = book("2353 Gerrard Street Shelter/"
                   "2.02 2535 Gerrard Shelter-Issued for Tender_5-Architectural Specifications.pdf")

    def rows(sets):
        return {n: [(c.qty, c.description, c.catalog_number, c.finish, c.mfr) for c in s.components]
                for n, s in sets.items()}
    assert rows(small) == rows(full)


# --- cases found by the fresh answer key and by the scan of all sets (eval/audit.py) -------------------------

def test_centred_row_with_quantity_between_its_text_lines():
    # JC Ryan p.30: "1 ... Sargent" sits between "Fail Safe Rim Exit Device with" and "integrated request to exit
    # switch"; the Door Closer's "1" sits alone between its two text lines.
    sets, _ = book("JC Ryan 2/087100 - Door Hardware-6.pdf", (28, 32))
    comps = {c.description: c for c in sets["3.0"].components}
    exit_device = comps["Fail Safe Rim Exit Device with integrated request to exit switch"]
    assert (exit_device.qty, exit_device.mfr) == (1, "Sargent")
    assert comps["Door Closer x Regular Arm mounted on pull side of door"].qty == 1


def test_door_lines_and_door_lists_are_not_components():
    sets, _ = book("Morris Bank/030f2d1d-Morris_Bank_Macon_-Spec_Manual_Issued_for_Const._1-26-26_FULL_SPECS.pdf",
                   (260, 264))
    assert [c.description for c in sets["MISC"].components][0] == "Key Cabinet"     # not "Other Door #MISC"
    sets, _ = book("National Doors and Hardware/15e2b8ac-FS17_Specs_V1.pdf", (405, 412))
    assert "38" in sets["13"].doors and all(c.description != "37 38" for c in sets["13"].components)
    sets, _ = book("Lyons Township HS/Project Manual (1).pdf", (283, 295))
    assert all((c.qty or 0) < 100 for c in sets["01"].components + sets["18"].components)


def test_set_with_its_own_column_positions():
    # Commons Lane p.103: set 101 puts the maker column at x=499, the rest of the book at x=512.
    sets, _ = book("StarHardware/9839d1a1-Division_8_Specs_-_Commons_Lane.pdf", (100, 105))
    hinges = sets["101"].components[0]
    assert (hinges.finish, hinges.mfr) == ("622", "IV")


def test_code_inside_wrapped_text_stays_in_the_text():
    # Commons Lane p.56: "... locking device) in 625 / polished chrome finish" - 625 is part of the sentence.
    sets, _ = book("StarHardware/9839d1a1-Division_8_Specs_-_Commons_Lane.pdf", (53, 57))
    cylinder = [c for c in sets["D1"].components if c.description == "Cylinder"][0]
    assert cylinder.mfr is None and "625 polished chrome" in cylinder.catalog_number


def test_door_numbers_are_not_the_set_description():
    sets, _ = book("Valor Acres Building E/087100-DOOR-HARDWARE_Rev_2.pdf")
    assert sets["05"].description == "Mechanical Closet Swing Doors" and sets["05"].doors == ["U11", "U12"]
    assert sets["12"].description is None


def test_quantity_found_when_product_text_runs_into_its_column():
    # Roselle p.16: "SCHLAGE - L9092EU, ... A 1" - the quantity 1 sits right behind the product text.
    sets, _ = book("Roselle Public Library/087100_FL_-_Door_Hardware_IFB_REVISED.pdf")
    lock = [c for c in sets["4.4"].components if c.description.startswith("MORTISE LOCKSET")][0]
    assert lock.qty == 1


def test_revision_tag_of_a_deleted_row_is_not_glued_to_the_row_above():
    sets, _ = book("HFH DG - HOSPITAL/08 71 00 - DOOR HARDWARE.pdf", (30, 32))
    assert not any("BULLETIN" in (c.catalog_number or "") for c in sets["016"].components
                   if c.description == "WIRE HARNESS - IN DOOR")


def test_row_after_the_sets_note_rows():
    # Hospital p.137: "DIAGRAMS | PROVIDE FACTORY POINT TO POINT WIRING DIAGRAMS" comes after the NOTE rows.
    sets, _ = book("HFH DG - HOSPITAL/08 71 00 - DOOR HARDWARE.pdf", (135, 138))
    diagrams = sets["143"].components[-1]
    assert diagrams.description == "DIAGRAMS" and diagrams.qty is None


def test_bracketed_remark_under_a_model_number_is_a_note():
    # Door Company p.397: "(FAIL SECURE)" starts its own line though it would have fitted after "VDC".
    sets, _ = book("The Door Company _Copy_/Vantage TX-22 Div 01, 08.pdf", (395, 398))
    lock = [c for c in sets["C200CZ"].components if c.description == "EU MORTISE LOCK"][0]
    assert lock.catalog_number == "L9092TEU 17L RX CON 12/24 VDC" and lock.notes == "(FAIL SECURE)"


def test_caption_at_the_end_of_a_paragraph_stays_in_the_text():
    # Commons Lane p.112: "(picture example of Stefano lever ...)" ends a long paragraph; it is not a separate note.
    sets, _ = book("StarHardware/9839d1a1-Division_8_Specs_-_Commons_Lane.pdf", (110, 113))
    latch = [c for c in sets["110"].components if (c.description or "").startswith("Privacy Latch")][0]
    assert "picture example" in latch.catalog_number and latch.notes is None
