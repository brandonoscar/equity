"""The people inside an owner-name string, so a debtor's own name can meet it.

Owner rolls print several owners and trusts in one string. A name key is the set of a
name's words, so "SMITH JOHN A & JANE B" (words A B JANE JOHN SMITH) never equals the debtor
"JOHN A SMITH" (A JOHN SMITH). owner_name_variants splits such strings deterministically:

  joint   "SMITH JOHN A & JANE B"   -> "SMITH JOHN A", "SMITH JANE B"
          "JOHN A & JANE B SMITH"   -> "JOHN A SMITH", "JANE B SMITH"
          "SMITH JOHN & DOE JANE"   -> "SMITH JOHN", "DOE JANE"
          The shared surname is carried over only when one part is a bare first name (one
          or two words, the second a single letter: 'JANE', 'JANE B'). Rolls print either
          LAST FIRST ("SMITH JOHN A & JANE B": the surname is the first word) or FIRST LAST
          ("JOHN A & JANE B SMITH": the last word); which is told from which part is bare.
  trust   "JOHN A SMITH REVOCABLE TRUST", "SMITH JOHN A TR", "SMITH JOHN A TRUSTEE",
          "JOHN SMITH LIVING TRUST DTD 01/02/2003" -> "JOHN A SMITH" / "SMITH JOHN A" ...
          the settlor's (or trustee's) own name; "SMITH FAMILY TRUST" names no person.

Tenancy and marital tags (ET UX, ET VIR, ET AL, JTWROS, JT TEN, TEN COM, H/W, L/E, LIFE
ESTATE, C/O) are dropped first. A part keeps only if it has at least two words. Names that
split into nothing new give no variants. A business name (one that ends in an entity form
such as LLC or INC, or carries an organization word other than a trust's) is never split:
"SMITH & JONES LLC" names no person. Pure string rules, no lookup tables of people.

Debtor names (debtor_name_variants) also print aliases, each the same debtor:

  alias   "JOHN SMITH DBA SMITH PLUMBING"  -> "JOHN SMITH", "SMITH PLUMBING"
          "JOHN SMITH AKA JACK SMITH", "ACME INC FKA ACME LLC", "T/A", "D/B/A", "N/K/A"
          A sole proprietor's trade name is the person's own debt; each part is then split
          like an owner string ("JOHN & JANE SMITH DBA ..." -> both people, kind 'joint').
"""

from __future__ import annotations

import re

from equity.matching.orgs import _ORG_WORDS, classify

TAGS = re.compile(
    r"\b(ET\s*UX|ETUX|ET\s*VIR|ETVIR|ET\s*AL|ETAL|JTWROS|JT\s*TEN|JTRS|TEN\s*COM|TEN\s*ENT|"
    r"H/W|W/H|L/E|LIFE\s+ESTATE|LIFE\s+EST|C/O|ATTN|DECD|DEC'D|DECEASED|HEIRS)\b"
)
# Words that make a string a trust and are not part of the person's name.
TRUST_WORDS = {
    "TRUST", "TR", "TRS", "TRST", "TRUSTEE", "TRUSTEES", "TTEE", "TTEES", "TRSTE",
    "REVOCABLE", "IRREVOCABLE", "REV", "IRREV", "LIVING", "LIV", "FAMILY", "FAM",
    "DECLARATION", "DECL", "AGREEMENT", "AGMT", "DTD", "DATED", "UA", "UAD", "UTD", "UDT",
    "THE", "OF", "FBO", "SURVIVORS", "SURVIVOR", "SEPARATE", "PROPERTY", "JOINT",
    "MARITAL", "BYPASS", "EXEMPT", "QTIP", "GST", "ESTATE", "EST", "NO", "NUMBER", "1", "2",
}  # fmt: skip
# An estate (a deceased owner or debtor): "ESTATE OF JOHN SMITH", "SMITH JOHN EST", "JOHN SMITH
# DECEASED", "HEIRS OF JOHN SMITH". A life estate is a tenancy and REAL ESTATE a business word,
# neither an estate.
ESTATE_MARK = re.compile(r"\b(ESTATE|EST|DECEASED|DECD|DEC'D|HEIRS)\b")
ESTATE_WORDS = {"ESTATE", "EST", "OF", "THE", "HEIRS", "UNKNOWN", "DECEASED", "DECD"}
TRUST_MARK = re.compile(r"\b(TRUST|TR|TRS|TRUSTEE|TRUSTEES|TTEE|TTEES|TRST)\b")
SPLIT = re.compile(r"\s*(?:&|\bAND\b|/|;|\+)\s*")
SUFFIX = {"JR", "SR", "II", "III", "IV", "V", "2ND", "3RD"}
# Organization words that make a name a business; a trust's or an estate's words do not
# (they name the settlor or the deceased).
BUSINESS_WORDS = _ORG_WORDS - {"TRUST", "TRUSTEE", "TRUSTEES", "ESTATE", "ESTATES"}
# Alias markers between two names of one debtor (D.B.A. is read as DBA).
ALIAS = re.compile(
    r"\s*\b(?:D\s*/\s*B\s*/\s*A|DBA|A\s*/\s*K\s*/\s*A|AKA|F\s*/\s*K\s*/\s*A|FKA|"
    r"N\s*/\s*K\s*/\s*A|NKA|T\s*/\s*A|DOING\s+BUSINESS\s+AS|ALSO\s+KNOWN\s+AS|"
    r"FORMERLY\s+KNOWN\s+AS|NOW\s+KNOWN\s+AS|TRADING\s+AS)\b\s*"
)


def _clean(raw: str) -> str:
    s = TAGS.sub(" ", raw.upper())
    s = re.sub(r"\bU\s*/\s*[AD](\s*/\s*[AT])?\b", " ", s)  # U/A, U/D, U/D/T (under agreement)
    s = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", " ", s)  # trust dates
    s = re.sub(r"[^A-Z0-9&/;+ ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _bare(words: list[str]) -> bool:
    """A first name alone: 'JANE' or 'JANE B'."""
    core = [w for w in words if w not in SUFFIX]
    return len(core) == 1 or (len(core) == 2 and len(core[1]) == 1)


def _joint(name: str) -> list[str]:
    parts = [p.split() for p in SPLIT.split(name) if p.strip()]
    if len(parts) < 2:
        return []
    out: list[list[str]] = []
    first, last = parts[0], parts[-1]
    if not _bare(first) and all(_bare(p) for p in parts[1:]):
        # LAST FIRST: 'SMITH JOHN A & JANE B' -> the surname is the first part's first word.
        out = [first] + [[first[0], *p] for p in parts[1:]]
    elif not _bare(last) and all(_bare(p) for p in parts[:-1]):
        # FIRST LAST: 'JOHN A & JANE B SMITH' -> the surname is the last part's last word.
        sur = [w for w in last if w not in SUFFIX][-1]
        out = [[*p, sur] for p in parts[:-1]] + [last]
    elif all(not _bare(p) for p in parts):
        out = parts  # every part a full name already
    names = [" ".join(p) for p in out if len([w for w in p if w not in SUFFIX]) >= 2]
    return names


def _estate(raw: str) -> list[str] | None:
    """The deceased named by an estate's string, or None when it is not an estate."""
    text = re.sub(r"\bLIFE\s+EST(ATE)?\b|\bREAL\s+ESTATE\b", " ", raw.upper())
    if not ESTATE_MARK.search(text):
        return None
    name = " ".join(w for w in _clean(text).split() if w not in ESTATE_WORDS)
    joint = _joint(name)
    if joint:
        return joint
    one = SPLIT.sub(" ", name).split()
    return [" ".join(one)] if len([w for w in one if w not in SUFFIX]) >= 2 else []


def _trust(name: str) -> list[str] | None:
    """The person names inside a trust's name, or None when the string is not a trust."""
    if not TRUST_MARK.search(name):
        return None
    kept = " ".join(w for w in name.split() if w not in TRUST_WORDS and not w.isdigit())
    joint = _joint(kept)
    if joint:
        return joint
    one = SPLIT.sub(" ", kept).split()
    return [" ".join(one)] if len([w for w in one if w not in SUFFIX]) >= 2 else []


def owner_name_variants(raw: str | None) -> list[tuple[str, str]]:
    """(name, kind) for each person inside an owner string: kind 'joint' (one of several
    owners printed together), 'trust' (the settlor or trustee of a trust) or 'estate' (the
    deceased of an estate). Empty when the string is one plain name or names no person."""
    if not raw:
        return []
    name = _clean(raw)
    if not name or _business(name):
        return []
    found: list[tuple[str, str]] = []
    deceased = _estate(raw)
    settlors = _trust(name)
    if deceased is not None:  # an estate: the deceased ('ESTATE OF JOHN SMITH')
        found += [(n, "estate") for n in deceased]
    elif settlors is not None:  # a trust: its settlors (both, for 'JOHN & JANE SMITH TRUST')
        found += [(n, "trust") for n in settlors]
    else:
        found += [(n, "joint") for n in _joint(name)]
    plain = re.sub(r"\s+", " ", name).strip()
    seen: set[str] = set()
    out = []
    for n, kind in found:
        key = " ".join(sorted(set(n.split())))
        # An estate's deceased is kept even when the cleaned string is the bare name
        # ("JOHN SMITH DECEASED"): the printed string's own key carries the marker.
        if n and (n != plain or kind == "estate") and key not in seen:
            seen.add(key)
            out.append((n, kind))
    return out


def _business(name: str) -> bool:
    """An entity-form name (LLC, INC, ...) or one with an organization word, unless that word
    is a trust's: a trust names its settlor."""
    c = classify(name)
    return c.org_form is not None or bool(set(name.split()) & BUSINESS_WORDS)


def debtor_name_variants(raw: str | None) -> list[tuple[str, str]]:
    """(name, kind) for each name inside a debtor string: kind 'alias' (a DBA, AKA or FKA
    name of the same debtor, a person or a business) or, as for owners, 'joint' and 'trust'.
    Empty when the string is one plain name."""
    if not raw:
        return []
    # D.B.A. / A.K.A. -> DBA / AKA; any other period separates words ("J.SMITH").
    text = re.sub(r"\b([A-Z])\.\s?([A-Z])\.\s?([A-Z])\b\.?", r"\1\2\3", raw.upper())
    text = text.replace(".", " ")
    parts = [p for p in (_clean(x) for x in ALIAS.split(text)) if p]
    if len(parts) < 2:
        return owner_name_variants(raw)
    found: list[tuple[str, str]] = []
    for part in parts:
        split = owner_name_variants(part)
        if split:
            found += split
        elif not SPLIT.search(part):
            found.append((part, "alias"))
    whole = _clean(text)
    seen: set[str] = set()
    out = []
    for n, kind in found:
        key = " ".join(sorted(set(n.split())))
        if n != whole and key not in seen:
            seen.add(key)
            out.append((n, kind))
    return out
