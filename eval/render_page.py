"""Render a PDF page (or part of it) to PNG so it can be looked at, e.g. to see struck-out text.

Usage: python eval/render_page.py <pdf> <page number> <out.png> [top bottom]   (top/bottom in points, optional)
"""
import sys

import pymupdf

pdf, page_no, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
page = pymupdf.open(pdf)[page_no - 1]
clip = None
if len(sys.argv) > 5:
    clip = pymupdf.Rect(0, float(sys.argv[4]), page.rect.width, float(sys.argv[5]))
page.get_pixmap(dpi=110, clip=clip).save(out)
print("saved", out)
