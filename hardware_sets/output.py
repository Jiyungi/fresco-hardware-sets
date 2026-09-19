"""Write results as JSON (full detail) and CSV (one row per component, opens in Excel)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .confidence import NEEDS_CHECK
from .models import ExtractionResult

CSV_COLUMNS = [
    "set_number", "set_description", "not_used", "doors", "set_pages", "set_confidence",
    "qty", "unit", "description", "catalog_number", "mfr", "finish", "notes",
    "mfr_name", "finish_name", "electrified", "component_page", "component_bbox", "low_confidence_fields",
]


def write_json(result: ExtractionResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))


def write_csv(result: ExtractionResult, path: Path, low: float = NEEDS_CHECK) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = result.to_dict()
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for s in data["sets"]:
            base = {
                "set_number": s["set_number"],
                "set_description": s["description"],
                "not_used": s["not_used"],
                "doors": ", ".join(s["doors"]),
                "set_pages": ", ".join(str(b["page"]) for b in s["location"]),
                "set_confidence": s["confidence"],
            }
            if not s["components"]:
                w.writerow(base)
                continue
            for c in s["components"]:
                loc = c["location"][0] if c["location"] else {"page": "", "bbox": ""}
                w.writerow({
                    **base,
                    **{k: c[k] for k in ("qty", "unit", "description", "catalog_number", "mfr", "finish", "notes",
                                         "mfr_name", "finish_name", "electrified")},
                    "component_page": loc["page"],
                    "component_bbox": loc["bbox"],
                    "low_confidence_fields": ", ".join(k for k, v in c["confidence"].items() if v < low),
                })
