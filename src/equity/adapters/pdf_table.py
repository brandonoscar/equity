"""Text and simple tables from machine-generated PDFs, with the standard library only.

Enough of PDF for a report printed straight to PDF (a state agency's list): the page content
streams are decoded (ASCII85Decode, as Oracle Reports writes them) and inflated (FlateDecode),
text-showing operators (Tj, TJ, ', ") are placed with the text matrix (Tm, Td, TD, T*, TL),
and glyph codes are mapped through each font's ToUnicode
CMap when it has one (Latin-1 otherwise). Text is then grouped into lines by baseline and into
columns by the x positions of a header line. No OCR, no layout inference beyond that: a
scanned or unusual PDF yields nothing, and the caller treats it as an empty list.

Downloaded PDFs are untrusted: nothing is executed, streams are inflated with a size cap, and
only literal parsing is done.
"""

from __future__ import annotations

import base64
import re
import zlib
from dataclasses import dataclass

MAX_STREAM = 50_000_000  # bytes after inflating one stream
OBJ = re.compile(rb"(?<![0-9])(\d+)\s+(\d+)\s+obj\b(.*?)\bendobj", re.S)
STREAM = re.compile(rb"^(.*?)stream\r?\n(.*)$", re.S)
REF = re.compile(rb"(\d+)\s+(\d+)\s+R\b")
TOKEN = re.compile(
    rb"\s*(?:(?P<str>\()|(?P<hex><[0-9A-Fa-f\s]*>)|(?P<arr>\[)|(?P<end>\])"
    rb"|(?P<dict><<)|(?P<dend>>>)|(?P<name>/[^\s/\[\]()<>{}%]*)"
    rb"|(?P<num>[+-]?(?:\d+\.?\d*|\.\d+))|(?P<op>[A-Za-z'\"*][A-Za-z0-9'\"*]*)|(?P<other>.))",
    re.S,
)


@dataclass(frozen=True)
class Text:
    x: float
    y: float
    text: str
    page: int


def _inflate(data: bytes) -> bytes:
    d = zlib.decompressobj()
    out = d.decompress(data, MAX_STREAM)
    if d.unconsumed_tail:
        raise ValueError("PDF stream too large")
    return out


def _objects(pdf: bytes) -> dict[int, bytes]:
    """Every 'n 0 obj ... endobj', including those packed in object streams (/ObjStm)."""
    objs: dict[int, bytes] = {}
    for m in OBJ.finditer(pdf):
        objs[int(m[1])] = m[3]
    for body in list(objs.values()):
        if b"/ObjStm" not in body:
            continue
        dic, data = _split_stream(body)
        if data is None:
            continue
        first = re.search(rb"/First\s+(\d+)", dic)
        n = re.search(rb"/N\s+(\d+)", dic)
        if not (first and n):
            continue
        head = data[: int(first[1])].split()
        offs = [
            (int(head[i]), int(head[i + 1])) for i in range(0, min(len(head), 2 * int(n[1])) - 1, 2)
        ]
        for i, (num, off) in enumerate(offs):
            end = offs[i + 1][1] if i + 1 < len(offs) else len(data) - int(first[1])
            objs.setdefault(num, data[int(first[1]) + off : int(first[1]) + end])
    return objs


def _ascii85(raw: bytes) -> bytes:
    """ASCII85Decode: whitespace ignored, an optional '<~' and the '~>' end marker dropped."""
    s = re.sub(rb"\s+", b"", raw)
    s = s[2:] if s.startswith(b"<~") else s
    s = s[: s.find(b"~>")] if b"~>" in s else s
    if len(s) > 2 * MAX_STREAM:
        raise ValueError("PDF stream too large")
    return base64.a85decode(s)


def _split_stream(body: bytes) -> tuple[bytes, bytes | None]:
    """(dictionary text, inflated stream data or None)."""
    m = STREAM.match(body)
    if m is None:
        return body, None
    dic, raw = m[1], m[2]
    raw = raw[: raw.rfind(b"endstream")] if b"endstream" in raw else raw
    if b"/ASCII85Decode" in dic or b"/A85" in dic:  # applied before Flate (Oracle Reports)
        try:
            raw = _ascii85(raw)
        except ValueError:
            return dic, None
    if b"/FlateDecode" in dic:
        try:
            return dic, _inflate(raw)
        except (zlib.error, ValueError):
            return dic, None
    return dic, raw


def _ref(dic: bytes, key: bytes) -> int | None:
    m = re.search(re.escape(key) + rb"\s+(\d+)\s+\d+\s+R", dic)
    return int(m[1]) if m else None


def _cmap(data: bytes) -> dict[int, str]:
    """A ToUnicode CMap's bfchar and bfrange entries (code -> text)."""
    out: dict[int, str] = {}

    def uni(h: bytes) -> str:
        h = re.sub(rb"\s", b"", h)
        try:
            return bytes.fromhex(h.decode()).decode("utf-16-be", errors="replace")
        except ValueError:
            return ""

    for block in re.findall(rb"beginbfchar(.*?)endbfchar", data, re.S):
        for src, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            out[int(src, 16)] = uni(dst)
    for block in re.findall(rb"beginbfrange(.*?)endbfrange", data, re.S):
        for lo, hi, dst in re.findall(
            rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block
        ):
            start = int(dst, 16)
            for i, code in enumerate(range(int(lo, 16), min(int(hi, 16), int(lo, 16) + 65535) + 1)):
                out[code] = chr(start + i) if start + i < 0x110000 else ""
    return out


def _literal(data: bytes, i: int) -> tuple[bytes, int]:
    """A (literal string) starting after the '(' at i: (bytes, index after ')')."""
    out, depth = bytearray(), 1
    esc = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}
    while i < len(data):
        c = data[i]
        if c == 0x5C and i + 1 < len(data):  # backslash
            nxt = data[i + 1]
            oct_ = re.match(rb"[0-7]{1,3}", data[i + 1 : i + 4])
            if oct_:
                out.append(int(oct_[0], 8) & 0xFF)
                i += 1 + len(oct_[0])
                continue
            if nxt in (10, 13):
                i += 2 + (nxt == 13 and data[i + 2 : i + 3] == b"\n")
                continue
            out.append(esc.get(nxt, nxt))
            i += 2
            continue
        if c == 0x28:
            depth += 1
        elif c == 0x29:
            depth -= 1
            if depth == 0:
                return bytes(out), i + 1
        out.append(c)
        i += 1
    return bytes(out), i


def _tokens(data: bytes) -> list[tuple[str, object]]:
    toks: list[tuple[str, object]] = []
    i = 0
    while i < len(data):
        m = TOKEN.match(data, i)
        if m is None or m.end() == i:
            break
        kind = m.lastgroup or "other"
        if kind == "str":
            s, i = _literal(data, m.end())
            toks.append(("str", s))
            continue
        i = m.end()
        if kind == "hex":
            h = re.sub(rb"\s", b"", m["hex"][1:-1])
            try:
                toks.append(("str", bytes.fromhex((h + b"0" * (len(h) % 2)).decode())))
            except ValueError:
                toks.append(("str", b""))
        elif kind == "num":
            toks.append(("num", float(m["num"])))
        elif kind in ("arr", "end", "name", "op", "dict", "dend"):
            toks.append((kind, m[kind].decode("latin-1")))
    return toks


def _decode(s: bytes, cmap: dict[int, str] | None, two_byte: bool) -> str:
    if two_byte:
        codes = [int.from_bytes(s[i : i + 2], "big") for i in range(0, len(s) - 1, 2)]
    else:
        codes = list(s)
    if cmap:
        return "".join(cmap.get(c, chr(c) if c < 256 else "") for c in codes)
    return bytes(c & 0xFF for c in codes).decode("latin-1")


def page_texts(pdf: bytes) -> list[Text]:
    """Every text run on every page, with its starting position in user space."""
    objs = _objects(pdf)
    out: list[Text] = []
    pages = [n for n, b in sorted(objs.items()) if re.search(rb"/Type\s*/Page(?![a-z])", b)]
    for page_no, n in enumerate(pages):
        body = objs[n]
        fonts: dict[str, tuple[dict[int, str] | None, bool]] = {}
        res = body
        rref = _ref(body, b"/Resources")
        if rref is not None and rref in objs:
            res = objs[rref]
        fm = re.search(rb"/Font\s*(<<.*?>>|\d+\s+\d+\s+R)", res, re.S)
        if fm:
            fdict = fm[1]
            if fdict.endswith(b"R"):
                fdict = objs.get(int(fdict.split()[0]), b"")
            for name, num, _ in re.findall(rb"/([^\s/<>]+)\s+(\d+)\s+(\d+)\s+R", fdict):
                fobj = objs.get(int(num), b"")
                two = b"/Type0" in fobj or b"Identity-H" in fobj
                tref = _ref(fobj, b"/ToUnicode")
                cmap = None
                if tref is not None and tref in objs:
                    _, data = _split_stream(objs[tref])
                    cmap = _cmap(data) if data else None
                fonts[name.decode("latin-1")] = (cmap, two)
        contents: list[int] = []
        cm = re.search(rb"/Contents\s*(\[[^\]]*\]|\d+\s+\d+\s+R)", body)
        if cm:
            contents = [int(r[0]) for r in REF.findall(cm[1])]
        data = b"\n".join(_split_stream(objs.get(c, b""))[1] or b"" for c in contents)
        out += _run(_tokens(data), fonts, page_no)
    return out


def _run(toks: list[tuple[str, object]], fonts: dict[str, tuple[dict[int, str] | None, bool]],
         page: int) -> list[Text]:  # fmt: skip
    out: list[Text] = []
    stack: list[object] = []
    tm = lm = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    leading = 0.0
    font: tuple[dict[int, str] | None, bool] = (None, False)
    arr: list[object] | None = None

    def move(tx: float, ty: float) -> None:
        nonlocal tm, lm
        a, b, c, d, e, f = lm
        lm = (a, b, c, d, e + tx * a + ty * c, f + tx * b + ty * d)
        tm = lm

    def show(parts: list[object]) -> None:
        text = "".join(_decode(p, *font) for p in parts if isinstance(p, bytes))
        if text.strip():
            out.append(Text(round(tm[4], 2), round(tm[5], 2), text, page))

    for kind, val in toks:
        if arr is not None:
            if kind == "end":
                stack.append(arr)
                arr = None
            elif kind in ("str", "num"):
                arr.append(val)
            continue
        if kind == "arr":
            arr = []
            continue
        if kind != "op":
            stack.append(val)
            continue
        op = str(val)
        nums = [v for v in stack if isinstance(v, float)]
        if op == "BT":
            tm = lm = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        elif op == "Tm" and len(nums) >= 6:
            tm = lm = tuple(nums[-6:])  # type: ignore[assignment]
        elif op in ("Td", "TD") and len(nums) >= 2:
            if op == "TD":
                leading = -nums[-1]
            move(nums[-2], nums[-1])
        elif op == "TL" and nums:
            leading = nums[-1]
        elif op == "T*":
            move(0, -leading)
        elif op == "Tf" and len(stack) >= 2 and isinstance(stack[-2], str):
            font = fonts.get(str(stack[-2]).lstrip("/"), (None, False))
        elif op == "Tj" and stack and isinstance(stack[-1], bytes):
            show([stack[-1]])
        elif op == "TJ" and stack and isinstance(stack[-1], list):
            show(stack[-1])
        elif op in ("'", '"') and stack and isinstance(stack[-1], bytes):
            move(0, -leading)
            show([stack[-1]])
        stack = []
    return out


def pdf_table(pdf: bytes, header: str, tolerance: float = 2.0) -> list[list[str]]:
    """Rows of cell text for a table whose header line starts with the text `header`: the
    header row first, then each later line (same page order, top to bottom) split into the
    header's columns by x position. Lines on later pages are read with the same columns; a
    line repeating the header is dropped."""
    texts = page_texts(pdf)
    lines: dict[tuple[int, float], list[Text]] = {}
    for t in texts:
        key = next((k for k in lines if k[0] == t.page and abs(k[1] - t.y) <= tolerance), None)
        lines.setdefault(key or (t.page, t.y), []).append(t)
    ordered = [
        sorted(v, key=lambda t: t.x)
        for _, v in sorted(lines.items(), key=lambda kv: (kv[0][0], -kv[0][1]))
    ]
    head_at = next(
        (i for i, ln in enumerate(ordered) if ln[0].text.strip().startswith(header)), None
    )
    if head_at is None:
        return []
    head = ordered[head_at]
    starts = [t.x for t in head]
    names = [t.text.strip() for t in head]
    rows = [names]
    for ln in ordered[head_at + 1 :]:
        if [t.text.strip() for t in ln] == names:
            continue
        cells = [""] * len(starts)
        for t in ln:
            col = max((i for i, s in enumerate(starts) if s <= t.x + tolerance), default=0)
            cells[col] = (cells[col] + " " + t.text.strip()).strip()
        rows.append(cells)
    return rows


def pdf_text(pdf: bytes) -> str:
    """All text runs of the PDF in page order, top to bottom, joined by spaces."""
    texts = sorted(page_texts(pdf), key=lambda t: (t.page, -t.y, t.x))
    return " ".join(" ".join(t.text for t in texts).split())
