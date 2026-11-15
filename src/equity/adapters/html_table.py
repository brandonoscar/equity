"""Minimal, deterministic HTML table extraction (stdlib html.parser, no third-party parser)."""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser


@dataclass
class Row:
    cells: list[str] = field(default_factory=list)
    hrefs: list[str] = field(default_factory=list)
    header: bool = False


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[Row]] = []
        self.captions: list[str] = []
        self._depth = 0
        self._row: Row | None = None
        self._cell: list[str] | None = None
        self._caption: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self.tables.append([])
                self.captions.append("")
        elif self._depth == 1 and tag == "caption":
            self._caption = []
        elif self._depth == 1 and tag == "tr":
            self._row = Row()
        elif self._depth == 1 and tag in ("td", "th") and self._row is not None:
            self._cell = []
            self._row.header = self._row.header or tag == "th"
        elif self._depth == 1 and tag == "a" and self._row is not None:
            href = dict(attrs).get("href")
            if href:
                self._row.hrefs.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "table":
            self._depth = max(0, self._depth - 1)
        elif tag == "caption" and self._caption is not None:
            self.captions[-1] = " ".join("".join(self._caption).split())
            self._caption = None
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.cells.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._depth != 1:
            return
        if self._cell is not None:
            self._cell.append(data)
        elif self._caption is not None:
            self._caption.append(data)


def tables(html: str) -> list[tuple[str, list[Row]]]:
    """Top-level tables as (caption, rows). Nested tables are ignored."""
    p = _TableParser()
    p.feed(html)
    p.close()
    return list(zip(p.captions, p.tables, strict=True))
