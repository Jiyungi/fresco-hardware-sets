"""Evidence for 'is this value a manufacturer or a finish?'.

A single value is never decided on its own: these scores are averaged over a
whole column (see columns.label_code_columns). The scores only say how much a
value *looks like* each kind.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "codes.json"

# 626, 630-316, 643E, US26D, 26D, C32D, SP28, 10BE, 313AN ...
FINISH_SHAPE = re.compile(r"^(?:US|C|SP)?\d{1,3}[A-Z]{0,2}(?:[-/](?:US|C)?\d{1,3}[A-Z]{0,2})*$")
COLOR_WORDS = re.compile(
    r"\b(black|bronze|chrome|nickel|brass|aluminum|stainless|white|gray|grey|anodized|primed|painted|clear)\b", re.I
)
SHORT_CODE = re.compile(r"^[A-Z][A-Z/&\-]{1,4}\d?$")


def code_key(value: str) -> str:
    """Normalise a printed value for lookups: '613 (OIL RUBBED BRONZE)' -> '613', 'Ea.' -> 'EA'."""
    v = value.strip().upper()
    v = re.split(r"\s*\(", v, maxsplit=1)[0]
    return v.rstrip(".:,;").strip()


@dataclass
class CodeBook:
    manufacturers: dict[str, str]
    manufacturer_names: list[str]
    finishes: dict[str, str]
    empty_values: set[str]
    units: dict[str, str]
    # Codes printed in the PDF's own lookup tables (strongest evidence).
    doc_manufacturers: dict[str, str] = field(default_factory=dict)
    doc_finishes: dict[str, str] = field(default_factory=dict)
    doc_options: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path = DATA_FILE) -> "CodeBook":
        raw = json.loads(path.read_text())
        return cls(
            manufacturers={k.upper(): v for k, v in raw["manufacturers"].items()},
            manufacturer_names=[n.lower() for n in raw["manufacturer_names"]],
            finishes={k.upper(): v for k, v in raw["finishes"].items()},
            empty_values={v.upper() for v in raw["empty_values"]},
            units={k.upper(): v for k, v in raw["units"].items()},
        )

    def add_document_tables(self, tables: dict[str, dict[str, str]]) -> None:
        self.doc_manufacturers.update({k.upper(): v for k, v in tables.get("manufacturers", {}).items()})
        self.doc_finishes.update({k.upper(): v for k, v in tables.get("finishes", {}).items()})
        self.doc_options.update({k.upper(): v for k, v in tables.get("options", {}).items()})

    # --- simple lookups -------------------------------------------------
    def is_empty(self, value: str | None) -> bool:
        return value is None or not value.strip() or value.strip().upper() in self.empty_values

    def unit(self, token: str) -> str | None:
        """'EA', 'Ea.', 'SET', 'Pr' -> normalised unit. Variants with a suffix ('EA-R') are kept as printed."""
        k = code_key(token)
        if k in self.units:
            return self.units[k]
        base, sep, suffix = k.partition("-")
        if sep and base in self.units and re.fullmatch(r"[A-Z]{1,3}", suffix):
            return k
        return None

    def mfr_name(self, value: str | None) -> str | None:
        if not value:
            return None
        k = code_key(value)
        return self.doc_manufacturers.get(k) or self.manufacturers.get(k) or None

    def finish_name(self, value: str | None) -> str | None:
        if not value:
            return None
        k = code_key(value)
        return self.doc_finishes.get(k) or self.finishes.get(k) or None

    def option_names(self, catalog_number: str | None) -> dict[str, str]:
        """Option codes in a catalog number that the PDF's own option list explains ("NRP": Non-Removable Pins)."""
        if not catalog_number or not self.doc_options:
            return {}
        tokens = re.findall(r"[A-Z0-9][A-Z0-9/\-]*", catalog_number.upper())
        return {t: self.doc_options[t] for t in tokens if t in self.doc_options}

    def is_known_mfr(self, value: str) -> bool:
        k = code_key(value)
        return k in self.doc_manufacturers or k in self.manufacturers or self._is_mfr_name(value)

    def is_known_finish(self, value: str) -> bool:
        k = code_key(value)
        return k in self.doc_finishes or k in self.finishes

    def _is_mfr_name(self, value: str) -> bool:
        v = value.strip().lower()
        return any(v == n or v.startswith(n + " ") or v.startswith(n + ",") for n in self.manufacturer_names)

    # --- evidence scores (0..1) ------------------------------------------
    def mfr_score(self, value: str) -> float:
        k = code_key(value)
        if k in self.doc_manufacturers:
            return 1.0
        if k in self.manufacturers or self._is_mfr_name(value):
            return 0.9
        if SHORT_CODE.match(k) and not self.is_known_finish(value) and not FINISH_SHAPE.match(k):
            return 0.4
        return 0.0

    def finish_score(self, value: str) -> float:
        k = code_key(value)
        if k in self.doc_finishes:
            return 1.0
        if k in self.finishes:
            return 0.9
        if FINISH_SHAPE.match(k) and len(k) >= 2:   # a lone digit ("Page 1") is not a finish
            return 0.7
        if COLOR_WORDS.search(value):
            return 0.6
        return 0.0
