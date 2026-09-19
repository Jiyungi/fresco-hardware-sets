"""Command line: python -m hardware_sets <pdf or folder> [--out output]"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .extract import extract_pdf
from .output import write_csv, write_json


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Extract door hardware sets from spec book PDFs.")
    ap.add_argument("inputs", nargs="+", help="PDF files or folders containing PDFs")
    ap.add_argument("--out", default="output", help="folder for the JSON and CSV results (default: output)")
    args = ap.parse_args(argv)

    pdfs: list[Path] = []
    for item in map(Path, args.inputs):
        pdfs.extend(sorted(item.rglob("*.pdf")) if item.is_dir() else [item])
    if not pdfs:
        print("no PDF files found", file=sys.stderr)
        return 1

    out_root = Path(args.out)
    for pdf in pdfs:
        t0 = time.time()
        result = extract_pdf(pdf)
        folder = out_root / pdf.parent.name
        write_json(result, folder / f"{pdf.stem}.json")   # not with_suffix(): names like "2.02 Specs" contain dots
        write_csv(result, folder / f"{pdf.stem}.csv")
        parts = sum(len(s.components) for s in result.sets)
        print(f"{len(result.sets):4d} sets {parts:5d} components  {time.time() - t0:5.1f}s  {pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
