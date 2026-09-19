"""The output format: hardware sets and their components.

Fields required by the brief: set_number, description, location, components
(qty, description, catalog_number, mfr, finish, notes). Everything else is an
agreed extra that helps accuracy or review (unit, not_used, doors, set_notes,
full maker/finish names from the PDF's own code tables, electrified flag,
confidence scores, warnings).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Box:
    """A rectangle on one page. bbox = [left, top, right, bottom] in PDF points, origin top-left."""

    page: int
    bbox: list[float]


@dataclass
class Component:
    qty: float | None = None
    unit: str | None = None
    description: str | None = None
    catalog_number: str | None = None
    mfr: str | None = None
    finish: str | None = None
    notes: str | None = None
    mfr_name: str | None = None       # full name, when the PDF (or the code list) defines the code
    finish_name: str | None = None
    electrified: bool | None = None   # from the PDF's "electrified opening" icon, when it uses one
    catalog_codes: dict[str, str] = field(default_factory=dict)  # option codes in the catalog number, from the PDF
    location: list[Box] = field(default_factory=list)
    confidence: dict[str, float] = field(default_factory=dict)


@dataclass
class HardwareSet:
    set_number: str
    description: str | None = None
    not_used: bool = False
    doors: list[str] = field(default_factory=list)
    set_notes: str | None = None
    location: list[Box] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)


@dataclass
class ExtractionResult:
    source_file: str
    page_count: int
    sets: list[HardwareSet] = field(default_factory=list)
    code_tables: dict[str, dict[str, str]] = field(default_factory=dict)
    layout_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for s in data["sets"]:
            for c in s["components"]:
                if isinstance(c["qty"], float) and c["qty"].is_integer():
                    c["qty"] = int(c["qty"])
        return data
