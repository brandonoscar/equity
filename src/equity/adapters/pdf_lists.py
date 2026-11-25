"""Rows of a name list printed to PDF (a treasurer's per-county notice of unclaimed-property
owners), for the person-list `pdf_table` access method.

The lists are reports printed straight to PDF: one owner per text line, the columns at fixed x
positions. `pdf_table.pdf_table` splits a line by the x of each header word, which fails when
the cells are centered under their header (a long address starts left of 'ADDRESS'), so here
the columns are cut at configured x positions instead (`cuts`: the x where each column after
the first begins). On each page, lines down to and including the header line (whose first
cell is `header`) are dropped, as are lines repeating the header. A line holding only the
`wrap` column continues the previous row's cell (a long holder name printed on two lines).
"""

from __future__ import annotations

import bisect
import re
from collections.abc import Mapping, Sequence

from equity.adapters.pdf_table import Text, page_texts

TOLERANCE = 2.0  # points: runs whose baselines differ by less are one line


def pdf_lines(pdf: bytes, tolerance: float = TOLERANCE) -> list[tuple[int, list[Text]]]:
    """(page, runs left to right) for each text line, pages in order, top to bottom."""
    out: list[tuple[int, list[Text]]] = []
    top: float | None = None  # baseline of the line being built
    for t in sorted(page_texts(pdf), key=lambda t: (t.page, -t.y)):
        if out and out[-1][0] == t.page and top is not None and top - t.y <= tolerance:
            out[-1][1].append(t)
        else:
            out.append((t.page, [t]))
            top = t.y
    return [(page, sorted(runs, key=lambda t: t.x)) for page, runs in out]


def pdf_rows(
    pdf: bytes,
    columns: Sequence[str],
    cuts: Sequence[float],
    header: str,
    wrap: str | None = None,
    require: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    """One dict per printed row, keyed by `columns` (len(cuts) + 1 names). A row is kept when
    every `require` column matches its regex (default: the first column is non-empty)."""
    if len(columns) != len(cuts) + 1:
        raise ValueError("pdf columns need one more name than cuts")
    want = {k: re.compile(v) for k, v in (require or {columns[0]: r"\S"}).items()}
    wrap_at = columns.index(wrap) if wrap else None
    lines = pdf_lines(pdf)
    header_pages = {p for p, runs in lines if runs[0].text.strip().upper() == header.upper()}
    out: list[dict[str, str]] = []
    page_seen_header: set[int] = set()
    last: tuple[int, dict[str, str]] | None = None
    for page, runs in lines:
        if page in header_pages and page not in page_seen_header:
            if runs[0].text.strip().upper() == header.upper():
                page_seen_header.add(page)
            continue  # above (or on) this page's header line
        cells = [""] * len(columns)
        for t in runs:
            i = bisect.bisect_right(cuts, t.x)
            cells[i] = " ".join(f"{cells[i]} {t.text}".split())
        if cells[0].upper() == header.upper():
            continue
        filled = [i for i, c in enumerate(cells) if c]
        if wrap_at is not None and filled == [wrap_at] and last is not None and last[0] == page:
            row = last[1]
            row[columns[wrap_at]] = f"{row[columns[wrap_at]]} {cells[wrap_at]}".strip()
            continue
        row = dict(zip(columns, cells, strict=True))
        if all(p.search(row.get(k, "")) for k, p in want.items()):
            out.append(row)
            last = (page, row)
        else:
            last = None
    return out
