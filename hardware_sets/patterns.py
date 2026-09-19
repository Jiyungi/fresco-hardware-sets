"""Text patterns seen across the spec books (set titles, quantities, door lines, ...).

Every pattern here comes from a real layout; the comment next to it names an example.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

DASHES = chr(0x2013) + chr(0x2014) + r"\-"  # en dash, em dash, hyphen; for use inside [...]

# A set identifier as printed: 1, 01, 001, 3A, 101AC, 005.1, 1.0, EX-1.0, AL 01, A1, 01.1, U-01,
# C200S1, CR38CLHO, K201ACTW.1, 211.3080, C00.EXT, NOFP1. Letters must be upper case.
SET_ID = r"(?P<id>(?:[A-Z]{1,4}[ \-]?)?\d{1,4}[A-Z0-9]{0,6}(?:[.\-][A-Z0-9]{1,6})?)"

# Broken Word numbering glued to titles: "PART 6 - HARDWARE GROUP NO. 103"
_JUNK_PREFIX = r"(?:PART\s+\d+\s*[" + DASHES + r"]\s*)?"
_LABELS = [
    # Hardware Group No. 01 / HARDWARE GROUP NO. 103 / Hardware Group/Set #A1 / Hardware Group/Sets 102.1 / HW Set #2
    r"(?:door\s+)?(?:hardware|hdwe?\.?|hw\.?)\s*(?:group|set|heading)s?(?:\s*/\s*(?:sets?|groups?))?"
    r"\s*(?:no\.?|number|#)?\s*[:#.]?\s*",
    r"set\s*(?:#|no\.?|number|:)\s*[:#]?\s*",          # Set #01, Set: 1.0, Set #AL 01
    r"heading\s*(?:#|no\.?|number)\s*[:#]?\s*",         # Heading #1
    r"group\s*(?:#|no\.?|number)\s*[:#]?\s*",           # Group No. 4
]
# The labels are case-insensitive; the identifier is not (so "Sets 102.1" is not read as set "s 102.1").
HEADING = re.compile(
    r"^\s*(?i:" + _JUNK_PREFIX + r")"
    + r"(?P<label>(?i:" + "|".join(f"(?:{p})" for p in _LABELS) + r")|HW\s+(?=[A-Z]?\d))"  # HW 01, HW E18 (SJC)
    + SET_ID + r"(?![\w/])"
)

# "Not used" markers, alone or as the whole description: "NOT USED", "N/A", "set not utilized at this time".
NOT_USED = re.compile(
    r"\b(?:not\s+used|not\s+utili[sz]ed|n/a|omitted|deleted|void|intentionally\s+(?:left\s+blank|omitted)"
    r"|not\s+in\s+contract)\b",
    re.I,
)
# A set that now lives under another number: "Moved to Exterior Set HW E18" (SJC).
MOVED = re.compile(
    r"(?:^(?:see|refer\s+to|combined\s+with)|\b(?:moved|relocated)\s+to)\b.*\b(?:set|hw|group|heading)\b", re.I
)

# Quantities: 3, 1.0, and the placeholders printed when the quantity is missing
# ("__" in Commons Lane, "--" in Roselle, "*" = "as required" in Livelle).
QTY = re.compile(r"^(?:\d{1,3}(?:\.\d{1,2})?|_{1,4}|-{2,3}|\*)$")
QTY_PLACEHOLDER = re.compile(r"^(?:_{1,4}|-{2,3}|\*)$")
AS_REQUIRED = re.compile(r"^as\s+req(?:'d|uired|\.)?$", re.I)  # "As Req." in the quantity column (SJC)

# Door lines that start with a number and would otherwise look like a component.
DOOR_LINE = re.compile(
    r"^(?:item\s*#\s*\d+\s+)?\d+\s+(?:single|pair|pr\.?|double|other)\s+(?:of\s+)?doors?\b", re.I
)
DOOR_LIST_LABEL = re.compile(r"^(?:for\s+use\s+on\s+)?doors?\s*(?:#\s*\(s\)|\(s\)|#)?\s*:\s*", re.I)
# Door numbers: D101A, 01-2211, C119-A, 140A-1
DOOR_TOKEN = re.compile(r"^[A-Za-z]{0,4}-?\d{1,4}[A-Za-z]{0,3}(?:[-.][A-Za-z0-9]{1,4})*$")

# Instructions that show a made-up example set ("Vertical schedule format sample:", Commons Lane p.31).
SAMPLE = re.compile(r"\b(?:sample|example)\b", re.I)

DESCRIPTION_LABEL = re.compile(r"^description\s*:\s*", re.I)
PART_NOTE_LABEL = re.compile(r"^(?:note|notes|properties)\s*:", re.I)
SET_NOTE_LABEL = re.compile(
    r"^(?:notes?|operation(?:al)?(?:\s+description)?|hardware\s+notes|door\s+notes|remarks|comments?|"
    r"description\s+of\s+operation)\s*:",
    re.I,
)
OPENING_PHRASE = re.compile(
    r"^(?:provide\s+each|each\s+to\s+have|each\s+opening\s+to\s+receive|each\s+(?:single|pair|door)"
    r"|furnish\s+each)",
    re.I,
)
# A cell that starts "By ..." (capital B: the start of a cell, not "... by Schlage" continuing a sentence).
BY_OTHERS = re.compile(r"^(?:By|BY|Furnished by|FURNISHED BY|Provided by|PROVIDED BY)\s")
# Door numbers used as a set's name: "(Door 114)", "(Doors U11 & U12 - Mechanical Closet Swing Doors)",
# "(Gates 139 & 140)".
DOOR_PREFIX = re.compile(
    r"^(?:doors?|gates?)\s+(?P<doors>[\w\-]+(?:[\s,&]+(?:and\s+)?[\w\-]+)*?)[\s,]*"
    r"(?:[" + DASHES + r"]\s+(?P<rest>.+))?$", re.I
)

# Where the hardware sets stop: end of a spec section, the start of another one, or an outline paragraph.
SECTION_END = re.compile(r"^\s*(?:end\s+of\s+(?:section|schedule)|section\s+\d{2}\s?\d{2}\s?\d{2})", re.I)
# Every spec section opens with "PART 1 - GENERAL"; seeing it means the hardware sets are over, even when the
# new section's title is hidden in the running page header (Gerrard: 08 71 00 is followed by 08 80 00 Glazing).
NEW_SECTION = re.compile(r"\bPART\s+1\s*[" + DASHES + r"]\s*GENERAL\b", re.I)
# Numbered spec paragraphs ("2.06 MILLWORK EQUIPMENT", "3.07 HARDWARE SCHEDULE", "PART 3 - EXECUTION").
# The heading word is ALL CAPS, which is how "3.0 Hinge" (a quantity and an item, Forest Park) differs.
OUTLINE_PARAGRAPH = re.compile(
    r"^(?:\d{1,2}\.\d{1,2}\s+[A-Z]{3,}\b(?![a-z])|PART\s+\d\s*[" + DASHES + r"]\s*[A-Z]{3,})"
)

# Column header words -> role. Checked word by word on a candidate header line.
HEADER_WORDS = {
    "QTY": "qty", "QTY.": "qty", "QUANTITY": "qty", "QT": "qty", "QTY:": "qty",
    "DESCRIPTION": "description", "DESC": "description", "DESC.": "description", "ITEM": "description",
    "TYPE": "description",
    "CATALOG": "catalog", "CAT.": "catalog", "CAT": "catalog", "MODEL": "catalog", "PRODUCT": "catalog",
    "PART": "catalog", "CATALOG#": "catalog",
    "FINISH": "finish", "FIN": "finish", "FIN.": "finish", "FINISHES": "finish",
    "MFR": "mfr", "MFR.": "mfr", "MANF": "mfr", "MANF.": "mfr", "MFG": "mfr", "MFG.": "mfr", "MFGR": "mfr",
    "MANUFACTURER": "mfr", "MAN.": "mfr",
    "NOTES": "notes", "NOTE": "notes", "REMARKS": "notes", "COMMENTS": "notes",
    "SET": "set", "HEADING": "set",
    "UNIT": "unit", "UOM": "unit",
}


@dataclass
class HeadingMatch:
    set_number: str
    rest: str                  # text after the identifier (description or "Not Used")
    also: list[str]            # further set numbers sharing this title: "#B1 and #B2"


_PROSE_AFTER_ID = re.compile(r"^(?:shall|is|are|was|of|for|and|or|to|in|on|with|as|at|by|the|a|an)\b", re.I)
_MORE_IDS = re.compile(r"^\s*(?:and|&|,)\s*#?\s*" + SET_ID.replace("?P<id>", "?P<more>") + r"(?![\w/])")
# Separators and icons between the set number and its description: "- ", ": ", an emoji.
_LEADING_SYMBOLS = re.compile(r"^[^\w(\[]+")
# A set named by a word rather than a number, alone on its line: "Set: MISC" (Livelle).
WORD_ID_HEADING = re.compile(r"^\s*(?:hardware\s+)?set\s*[:#]\s*(?P<id>[A-Z]{2,8})\s*$", re.I)


# Titles written as an instruction (Commons Lane): "For doors assigned Hardware Group/Set #103 on door
# schedule, provide the following:" and "For doors assigned hardware sets #28, #29 and #30 on ...".
FOR_DOORS_ASSIGNED = re.compile(
    r"^\s*for\s+doors\s+assigned\s+(?:hardware\s+)?(?:group|set)s?(?:\s*/\s*(?:sets?|groups?))?\s*#\s*"
    + SET_ID + r"(?P<more>(?:\s*(?:,|and|&)\s*#\s*[A-Z0-9.\-]+)*)", re.I
)


def match_heading(text: str) -> HeadingMatch | None:
    """Recognise a set title line and split it into the set number(s) and the rest."""
    f = FOR_DOORS_ASSIGNED.match(text)
    if f:
        also = re.findall(r"#\s*([A-Z0-9.\-]+)", f.group("more"))
        return HeadingMatch(set_number=f.group("id"), rest="", also=also)
    m = HEADING.match(text)
    if not m:
        w = WORD_ID_HEADING.match(text)
        if w and w.group("id").isupper():
            return HeadingMatch(set_number=w.group("id"), rest="", also=[])
        return None
    rest = text[m.end():]
    also = []
    while True:
        more = _MORE_IDS.match(rest)
        if not more:
            break
        also.append(re.sub(r"\s+", " ", more.group("more")))
        rest = rest[more.end():]
    rest = rest.strip()
    stripped = _LEADING_SYMBOLS.sub("", rest)
    if rest and (rest[0].islower() or _PROSE_AFTER_ID.match(rest)) and not is_not_used(stripped):
        return None  # "Set 1 of keys shall ..." is a sentence, not a title
    set_id = re.sub(r"\s+", " ", m.group("id")).strip()
    return HeadingMatch(set_number=set_id, rest=stripped, also=also)


def is_not_used(text: str) -> bool:
    """True when the text is (essentially) just a not-used marker, e.g. "NOT USED", "set not utilized at this time"."""
    text = text.strip()
    return bool(text) and len(text.split()) <= 8 and bool(NOT_USED.search(text))
