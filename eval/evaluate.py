"""Measure extraction accuracy against the answer keys (eval/answer_key/*.json, eval/holdout_key/*.json).

The keys were transcribed from the PDF pages by separate AI helper sessions that could not see this program.

Usage:
    python eval/evaluate.py [--output output] [--report eval/report.md]

What is measured, per book and overall:
  - Set finding: of the set titles listed in the key ("all_set_numbers"), how many the program found,
    and how many sets it reported that are not in the key.
  - For the sets transcribed in detail:
      * set fully correct: found, same "not used" flag, same number of components, and every component
        has qty, description, catalog_number, mfr and finish right;
      * component fully correct: those five fields right;
      * accuracy of each field on its own (maker and finish reported separately).
    Notes are free text and scored on their own (not part of "fully correct").
"Right" means equal after ignoring case, extra spaces and quote styles.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE_FIELDS = ["qty", "description", "catalog_number", "mfr", "finish"]
ALL_FIELDS = CORE_FIELDS + ["unit", "notes"]


def norm(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return str(int(value)) if float(value).is_integer() else str(value)
    v = str(value)
    quotes = {0x201C: '"', 0x201D: '"', 0x2019: "'", 0x2018: "'", 0x2013: "-", 0x2014: "-"}
    v = v.translate(quotes)
    v = re.sub(r"\s+", " ", v).strip().upper()
    v = re.sub(r"\s*([(\[])\s*", r" \1", v)      # spacing next to brackets and commas is not content
    v = re.sub(r"\s*([)\],])", r"\1", v).strip()
    return v or None


def same(a, b) -> bool:
    return norm(a) == norm(b)


def _key(c: dict) -> str:
    return f"{norm(c.get('description')) or ''} | {norm(c.get('catalog_number')) or ''}"


def align(key_comps: list[dict], got_comps: list[dict]) -> list[tuple[dict | None, dict | None]]:
    """Pair key components with output components in order (edit-distance style alignment)."""
    n, m = len(key_comps), len(got_comps)
    sim = [[SequenceMatcher(None, _key(a), _key(b)).ratio() for b in got_comps] for a in key_comps]
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            take = best[i + 1][j + 1] + (sim[i][j] if sim[i][j] >= 0.5 else -1.0)
            best[i][j] = max(take, best[i + 1][j], best[i][j + 1])
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        take = best[i + 1][j + 1] + (sim[i][j] if sim[i][j] >= 0.5 else -1.0)
        if sim[i][j] >= 0.5 and best[i][j] == take:
            pairs.append((key_comps[i], got_comps[j]))
            i, j = i + 1, j + 1
        elif best[i][j] == best[i + 1][j]:
            pairs.append((key_comps[i], None))
            i += 1
        else:
            pairs.append((None, got_comps[j]))
            j += 1
    pairs += [(k, None) for k in key_comps[i:]] + [(None, g) for g in got_comps[j:]]
    return pairs


def match_sets(key_sets: list[dict], got_sets: list[dict]) -> list[tuple[dict, dict | None]]:
    """Match by set number; when a number repeats, use page overlap then order."""
    used: set[int] = set()
    out = []
    for ks in key_sets:
        candidates = [i for i, g in enumerate(got_sets) if i not in used and same(g["set_number"], ks["set_number"])]
        if not candidates:
            out.append((ks, None))
            continue
        pages = set(ks.get("pages", []))

        def overlap(i: int) -> int:
            got_pages = {b["page"] for b in got_sets[i].get("location", [])} or set(got_sets[i].get("pages", []))
            return len(pages & got_pages)
        best = max(candidates, key=lambda i: (overlap(i), -i))
        used.add(best)
        out.append((ks, got_sets[best]))
    return out


def evaluate_book(key: dict, got: dict) -> dict:
    stats: Counter = Counter()
    problems: list[str] = []

    # Set finding (only when the key lists every set title of the book)
    if key.get("all_set_numbers"):
        key_numbers = Counter(norm(n) for n in key["all_set_numbers"])
        got_numbers = Counter(norm(s["set_number"]) for s in got["sets"])
        stats["titles_in_key"] = sum(key_numbers.values())
        stats["titles_found"] = sum((key_numbers & got_numbers).values())
        stats["extra_sets"] = sum((got_numbers - key_numbers).values())
        missing = sorted((key_numbers - got_numbers).elements())
        extra = sorted((got_numbers - key_numbers).elements())
        if missing:
            problems.append(f"sets not found: {missing}")
        if extra:
            problems.append(f"sets reported but not in key: {extra}")

    # Detailed sets
    for ks, gs in match_sets(key["sets"], got["sets"]):
        stats["sets"] += 1
        if gs is None:
            problems.append(f"set {ks['set_number']}: not found")
            stats["components"] += len(ks["components"])
            continue
        stats["sets_found"] += 1
        set_ok = same(ks.get("not_used"), gs.get("not_used")) and len(ks["components"]) == len(gs["components"])
        stats["set_description_correct"] += same(ks.get("description"), gs.get("description"))
        if not same(ks.get("description"), gs.get("description")):
            problems.append(
                f"set {ks['set_number']}: description {gs.get('description')!r} (key {ks.get('description')!r})"
            )
        if not same(ks.get("not_used"), gs.get("not_used")):
            problems.append(f"set {ks['set_number']}: not_used {gs.get('not_used')} (key {ks.get('not_used')})")
        for kc, gc in align(ks["components"], gs["components"]):
            if kc is None:
                stats["extra_components"] += 1
                problems.append(f"set {ks['set_number']}: extra component {_key(gc)!r}")
                set_ok = False
                continue
            stats["components"] += 1
            if gc is None:
                problems.append(f"set {ks['set_number']}: missing component {_key(kc)!r}")
                set_ok = False
                continue
            stats["components_found"] += 1
            comp_ok = True
            for f in ALL_FIELDS:
                ok = same(kc.get(f), gc.get(f))
                stats[f"{f}_correct"] += ok
                if not ok:
                    where = _key(kc)[:40]
                    problems.append(f"set {ks['set_number']}: {f} {gc.get(f)!r} (key {kc.get(f)!r}) in {where!r}")
                    if f in CORE_FIELDS:
                        comp_ok = False
            stats["components_correct"] += comp_ok
            set_ok = set_ok and comp_ok
        stats["sets_correct"] += set_ok
    return {"stats": stats, "problems": problems}


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:5.1f}%" if b else "   n/a"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=str(ROOT / "output"), help="folder with the program's JSON results")
    ap.add_argument("--keys", default=str(ROOT / "eval" / "answer_key"))
    ap.add_argument("--report", default=str(ROOT / "eval" / "report.md"))
    args = ap.parse_args()

    total: Counter = Counter()
    rows, details = [], []
    for key_file in sorted(Path(args.keys).glob("*.json")):
        key = json.loads(key_file.read_text())
        pdf = Path(key["source_pdf"])
        out_file = Path(args.output) / pdf.parent.name / f"{pdf.stem}.json"
        if not out_file.exists():
            print(f"missing output for {pdf} (run: python -m hardware_sets \"{pdf}\")")
            continue
        res = evaluate_book(key, json.loads(out_file.read_text()))
        s = res["stats"]
        total.update(s)
        rows.append((key_file.stem, s))
        details.append((key_file.stem, res["problems"]))

    header = ("| book | sets found (all titles) | extra sets | sets fully correct | components fully correct "
              "| qty | description | catalog # | mfr | finish | notes |")
    lines = [header, "|" + "---|" * 11]
    for name, s in rows + [("**overall**", total)]:
        lines.append(
            f"| {name} | {s['titles_found']}/{s['titles_in_key']} ({pct(s['titles_found'], s['titles_in_key'])}) "
            f"| {s['extra_sets']} | {s['sets_correct']}/{s['sets']} ({pct(s['sets_correct'], s['sets'])}) "
            f"| {s['components_correct']}/{s['components']} ({pct(s['components_correct'], s['components'])}) "
            + " ".join(f"| {pct(s[f + '_correct'], s['components'])}" for f in
                       ["qty", "description", "catalog_number", "mfr", "finish", "notes"]) + " |"
        )
    table = "\n".join(lines)
    print(table)
    report = ["# Accuracy against the transcribed answer key", "", table, "", "## Differences found", ""]
    for name, problems in details:
        report.append(f"### {name}")
        report.extend(f"- {p}" for p in problems[:60])
        if len(problems) > 60:
            report.append(f"- ... and {len(problems) - 60} more")
        if not problems:
            report.append("- none")
        report.append("")
    Path(args.report).write_text("\n".join(report))
    print(f"\ndetails written to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
