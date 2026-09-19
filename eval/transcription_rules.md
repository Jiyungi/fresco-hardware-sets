TRANSCRIPTION RULES (follow exactly):
1. Copy values exactly as printed (spelling, case, punctuation); collapse runs of spaces to one. Text that wraps onto the next line inside the same cell continues the value (join with one space). A finish split like "630-"/"316" or "643"/"e" joins with no space. Some tables centre a cell vertically, so part of a description can sit half a line above or below the row's other values: it still belongs to that row.
2. set_number: identifier only, without label words ("Hardware Group No.", "Set:", "Set #", "HW", "Heading #", "Hardware Group/Set #"). Keep leading zeros and letters exactly ("001", "AL 01", "EX-1.0", "E01"). Ignore junk numbering glued in front such as "PART 6 - ".
3. description: the set's own name, if printed on the title line after the number (drop a leading dash/colon and surrounding parentheses) or on a "Description:" line, or stacked in a SET column of a grid (join the stacked words with single spaces). null if none. Never include door numbers, "For use on Door #(s)", "Doors: ...", "Provide each ... with the following:", "Each to have:", "Each Opening to Receive: ...", "Not Used", or bracketed revision notes like "[BULLETIN 023, 251218]".
4. not_used: true when marked NOT USED / N/A / not utilized / moved to another set; else false.
5. components: one entry per row of the set's hardware list, in printed order, continuing across page breaks. Include rows with no quantity. EXCLUDE: struck-out (deleted) rows (a line drawn through the middle of the text: check the page IMAGE), column header rows, door lines ("1 Pair Doors #101", "Item #1 1 Single door 101"), size lines, and set-level notes ("OPERATIONAL DESCRIPTION: ...", "Notes:"/"Operation:" blocks, a "NOTE:" table row about the whole set, numbered notes after the last row, a grid row that holds only a NOTES entry).
6. qty: the number as printed (integer unless printed as a non-zero decimal: "3.0" -> 3); null if blank, "--", "__", "*", "As Req." etc. unit: the unit printed next to the quantity, uppercase without trailing period ("EA", "SET", "PR", "EA-R"); null if none.
7. description = the item/description/hardware-type column; catalog_number = the catalog/model/product column (with wrapped lines). If a combined "MANUFACTURER - PRODUCT" column is used, the part before the first " - " is mfr and the rest is catalog_number.
8. finish and mfr = exactly what is printed in those columns; null if blank, only dashes, or if the book has no such column. Small icons printed between columns are not text: ignore them.
9. notes: text printed specifically for that row that is not in the other columns: a NOTES column value, "Note:"/"Properties:" lines under the row (drop the label and a leading "- "), door handing like "RH"/"LH" in its own narrow column, or a separate parenthesised remark line under a short catalog number. null otherwise.
10. Leave out struck-out words.

OUTPUT shape (one JSON file per book):
{"source_pdf": "<path relative to project root>", "all_set_numbers": [], "labeler_notes": "anything ambiguous you decided",
 "sets": [{"set_number": "01", "pages": [20, 21], "description": null, "not_used": false,
           "components": [{"qty": 3, "unit": "EA", "description": "HINGE", "catalog_number": "5BB1 4.5 X 4.5", "finish": "652", "mfr": "IVE", "notes": null}]}]}
If one set number appears twice as two separate live sets, add both entries with the same set_number, in page order.
Validate each file with `./.venv/bin/python -c "import json,sys; json.load(open(sys.argv[1]))" <file>`.
