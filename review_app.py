"""Review screen: see each extracted set on its PDF page and correct mistakes.

Run:  streamlit run review_app.py

- Left: the PDF page with a red box around the set and a box around each component
  (orange = at least one field has low confidence).
- Right: the set's fields and an editable table of its components.
- "Save corrections" writes corrections/<book>.json in the same format as the answer key
  (eval/answer_key), so corrected sets can be used to measure accuracy too.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pymupdf
import streamlit as st
from PIL import Image, ImageDraw

from hardware_sets.confidence import NEEDS_CHECK
from hardware_sets.extract import extract_pdf
from hardware_sets.output import write_csv, write_json

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
CORRECTIONS = ROOT / "corrections"
UPLOADS = ROOT / "uploads"
LOW = NEEDS_CHECK   # a value scoring below this is marked for checking (see hardware_sets/confidence.py)
DPI = 110
FIELDS = ["qty", "unit", "description", "catalog_number", "mfr", "finish", "notes"]

st.set_page_config(page_title="Hardware set review", layout="wide")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def result_files() -> list[Path]:
    return sorted(p for p in OUTPUT.glob("*/*.json"))


def load_result(path: Path) -> dict:
    return json.loads(path.read_text())


def corrections_path(result_path: Path) -> Path:
    return CORRECTIONS / result_path.parent.name / result_path.name


def load_corrections(result_path: Path) -> dict:
    p = corrections_path(result_path)
    if p.exists():
        return json.loads(p.read_text())
    return {"source_pdf": None, "sets": []}


def set_key(s: dict) -> str:
    first_page = s["location"][0]["page"] if s.get("location") else s.get("pages", [0])[0]
    return f"{s['set_number']}@{first_page}"


def pdf_path(result: dict) -> Path:
    p = Path(result["source_file"])
    return p if p.is_absolute() else ROOT / p


@st.cache_data(show_spinner=False)
def page_image(pdf: str, page_no: int) -> Image.Image:
    page = pymupdf.open(pdf)[page_no - 1]
    pix = page.get_pixmap(dpi=DPI)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def draw_boxes(img: Image.Image, page_no: int, s: dict, all_sets: list[dict]) -> Image.Image:
    img = img.copy()
    draw = ImageDraw.Draw(img)
    k = DPI / 72.0
    # Other sets found on this page: grey box + their set number, so it is clear they were found too.
    for other in all_sets:
        if other is s:
            continue
        for b in other["location"]:
            if b["page"] == page_no:
                x0, y0, x1, y1 = (v * k for v in b["bbox"])
                draw.rectangle([x0 - 6, y0 - 5, x1 + 6, y1 + 5], outline=(150, 150, 150), width=2)
                label = f"Set {other['set_number']}"
                tx0, ty0, tx1, ty1 = draw.textbbox((0, 0), label, font_size=14)
                draw.rectangle([x1 + 6 - (tx1 - tx0) - 8, y0 - 5, x1 + 6, y0 - 5 + (ty1 - ty0) + 6],
                               fill=(150, 150, 150))
                draw.text((x1 + 6 - (tx1 - tx0) - 4, y0 - 3), label, fill=(255, 255, 255), font_size=14)
    for c in s["components"]:
        low = any(v < LOW for v in c.get("confidence", {}).values())
        for b in c["location"]:
            if b["page"] == page_no:
                x0, y0, x1, y1 = (v * k for v in b["bbox"])
                draw.rectangle([x0 - 2, y0 - 1, x1 + 2, y1 + 1], outline=(230, 140, 0) if low else (40, 110, 220),
                               width=2)
    for b in s["location"]:
        if b["page"] == page_no:
            x0, y0, x1, y1 = (v * k for v in b["bbox"])
            draw.rectangle([x0 - 6, y0 - 5, x1 + 6, y1 + 5], outline=(210, 30, 30), width=3)
    return img


def components_frame(s: dict) -> pd.DataFrame:
    rows = []
    for c in s["components"]:
        low = [f for f, v in c.get("confidence", {}).items() if v < LOW]
        rows.append({**{f: c.get(f) for f in FIELDS}, "check": ", ".join(low)})
    df = pd.DataFrame(rows, columns=FIELDS + ["check"])
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce")
    return df


def frame_to_components(df: pd.DataFrame) -> list[dict]:
    out = []
    for _, row in df.iterrows():
        comp = {}
        for f in FIELDS:
            v = row.get(f)
            if v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and not v.strip()):
                comp[f] = None
            elif f == "qty":
                comp[f] = int(v) if float(v).is_integer() else float(v)
            else:
                comp[f] = str(v).strip()
        if any(comp[f] is not None for f in FIELDS):
            out.append(comp)
    return out


# ---------------------------------------------------------------------------
# Sidebar: pick a book (or upload one) and a set
# ---------------------------------------------------------------------------
st.sidebar.title("Hardware set review")
uploaded = st.sidebar.file_uploader("Extract a new PDF", type=["pdf"])
if uploaded is not None and st.sidebar.button("Run extraction"):
    UPLOADS.mkdir(exist_ok=True)
    target = UPLOADS / uploaded.name
    target.write_bytes(uploaded.getvalue())
    with st.spinner("Reading the PDF..."):
        res = extract_pdf(target)
    write_json(res, OUTPUT / "uploads" / f"{target.stem}.json")
    write_csv(res, OUTPUT / "uploads" / f"{target.stem}.csv")
    st.sidebar.success(f"{len(res.sets)} sets found")

files = [f for f in result_files() if load_result(f)["sets"]]
if not files:
    st.info("No results yet. Run `python -m hardware_sets <pdf or folder>` first, or upload a PDF.")
    st.stop()
choice = st.sidebar.selectbox("Spec book", files, format_func=lambda p: f"{p.parent.name} / {p.stem}")
result = load_result(choice)
corrections = load_corrections(choice)
corrected = {set_key(s): s for s in corrections["sets"]}

only_low = st.sidebar.checkbox("Only sets that need checking", value=False)
sets = result["sets"]
if only_low:
    sets = [s for s in sets if s["warnings"] or any(v < LOW for c in s["components"] for v in c["confidence"].values())]
if not sets:
    st.sidebar.write("Nothing to check in this book.")
    st.stop()


def label(s: dict) -> str:
    mark = "  [corrected]" if set_key(s) in corrected else ""
    desc = f" - {s['description'][:40]}" if s.get("description") else ""
    return f"{s['set_number']}{desc}  ({s['confidence']:.2f}){mark}"


idx = st.sidebar.selectbox("Set", range(len(sets)), format_func=lambda i: label(sets[i]))
s = sets[idx]
st.sidebar.caption(f"{len(result['sets'])} sets in this book, {len(corrected)} corrected so far.")
with st.sidebar.expander("How the columns were read"):
    for note in result.get("layout_notes", []):
        st.write("-", note)

# ---------------------------------------------------------------------------
# Main: page image + editable set
# ---------------------------------------------------------------------------
left, right = st.columns([1, 1.25])
with left:
    for b in s["location"]:
        st.caption(f"Page {b['page']}  (red: this set, blue: its components, orange: needs checking, "
                   "grey: other sets found on this page - pick them in the Set list)")
        st.image(draw_boxes(page_image(str(pdf_path(result)), b["page"]), b["page"], s, result["sets"]),
                 width="stretch")

with right:
    base = corrected.get(set_key(s))
    st.subheader(f"Set {s['set_number']}")
    if s["warnings"]:
        st.warning("; ".join(s["warnings"]))
    c1, c2, c3 = st.columns([1, 2.5, 1])
    number = c1.text_input("Set number", value=(base or s)["set_number"])
    description = c2.text_input("Description", value=(base or s).get("description") or "")
    not_used = c3.checkbox("Not used", value=bool((base or s).get("not_used")))
    if s.get("doors"):
        st.caption("Doors: " + ", ".join(s["doors"]))
    if s.get("set_notes"):
        with st.expander("Set notes"):
            st.write(s["set_notes"])

    if base is None:
        df = components_frame(s)
    else:  # show the saved corrections instead of the program's output
        df = pd.DataFrame([{**c, "check": ""} for c in base["components"]], columns=FIELDS + ["check"])
    edited = st.data_editor(
        df, num_rows="dynamic", width="stretch", hide_index=True, key=f"editor-{choice}-{set_key(s)}",
        column_config={"check": st.column_config.TextColumn("needs checking", disabled=True),
                       "qty": st.column_config.NumberColumn("qty", step=1)},
    )
    b1, b2 = st.columns(2)
    if b1.button("Save corrections", type="primary"):
        entry = {
            "set_number": number.strip(),
            "pages": [b["page"] for b in s["location"]],
            "description": description.strip() or None,
            "not_used": not_used,
            "components": frame_to_components(edited),
        }
        corrected[set_key(s)] = entry
        corrections["source_pdf"] = result["source_file"]
        corrections["sets"] = list(corrected.values())
        path = corrections_path(choice)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(corrections, indent=2, ensure_ascii=False))
        st.success(f"Saved to {path.relative_to(ROOT)}")
    if base is not None and b2.button("Undo my corrections for this set"):
        corrected.pop(set_key(s))
        corrections["sets"] = list(corrected.values())
        corrections_path(choice).write_text(json.dumps(corrections, indent=2, ensure_ascii=False))
        st.rerun()

    with st.expander("Confidence scores for each component"):
        st.dataframe(pd.DataFrame([c["confidence"] for c in s["components"]]), width="stretch")
