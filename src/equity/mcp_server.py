"""The search tools as an MCP server (stdio), so a Claude session calls search, show, parcel,
grade, network, leads and facts as tools instead of running the CLI or writing SQL.

    uv run python -m equity.mcp_server        # .mcp.json starts it as "equity-tools"

It speaks the Model Context Protocol's JSON-RPC over stdin/stdout directly (initialize,
tools/list, tools/call, ping), so it needs no MCP library and no new dependency. Every call
opens the index read-only and closes it after, so it holds no lock between calls. It runs
only the deterministic search functions: no model, no writes.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any, TextIO

from equity import facts as facts_mod
from equity import search as s
from equity.search_index import DEFAULT_DB, connect

PROTOCOL = "2025-06-18"
MAX_CHARS = 200_000  # a tool result longer than this is cut, and says so

_STR = {"type": "string"}
_INT = {"type": "integer"}
TOOLS: list[dict[str, Any]] = [
    {"name": "search", "description": "Name search over parties and businesses: every hit "
     "scored by a named rule, with its links (parcels, debts, cases). Returns refs for show.",
     "inputSchema": {"type": "object", "required": ["name"], "properties": {
         "name": _STR, "state": _STR, "kind": {"enum": ["person", "org", "unknown", "business"]},
         "limit": _INT}}},
    {"name": "show", "description": "Everything on one record (source_id:party_id, or "
     "<source_id>:business:<id>): address, parcels with equity, documents, cases, business "
     "roles, matcher verdicts, same-name records elsewhere.",
     "inputSchema": {"type": "object", "required": ["ref"], "properties": {"ref": _STR}}},
    {"name": "parcel", "description": "A parcel by parcel_uid or county id: each source's "
     "record, value history, owners, recorded documents, net equity, tax delinquency, "
     "house-price estimate; with as_of (YYYY-MM-DD) who owned it then.",
     "inputSchema": {"type": "object", "required": ["parcel"], "properties": {
         "parcel": _STR, "as_of": _STR}}},
    {"name": "grade", "description": "Identity grade (A/B/C/reject) of a debtor record and an "
     "owner record by the matcher's rules, with the evidence.",
     "inputSchema": {"type": "object", "required": ["debtor_ref", "owner_ref"],
                     "properties": {"debtor_ref": _STR, "owner_ref": _STR}}},
    {"name": "network", "description": "Walk a record's links outward (parcels, documents, "
     "cases, businesses, same address, same name). same_address and same_name are leads.",
     "inputSchema": {"type": "object", "required": ["ref"], "properties": {
         "ref": _STR, "hops": _INT}}},
    {"name": "leads", "description": "The ranked leads table for a state: grade, net equity, "
     "homestead, bankruptcy, transfers, debt age. Filters are optional.",
     "inputSchema": {"type": "object", "required": ["state"], "properties": {
         "state": _STR, "grades": {"type": "array", "items": _STR}, "min_debt": {"type": "number"},
         "min_value": {"type": "number"}, "max_parcels": _INT, "exclude_homestead": {
             "type": "boolean"}, "limit": _INT}}},
    {"name": "facts", "description": "The deterministic fact sheet for one lead (lead_id from "
     "leads), for scoring with the score-rubric skill.",
     "inputSchema": {"type": "object", "required": ["lead_id"], "properties": {"lead_id": _INT}}},
    {"name": "address", "description": "Parcels at a street address and parties whose address "
     "it is (USPS-standardized street).",
     "inputSchema": {"type": "object", "required": ["address"], "properties": {
         "address": _STR, "zip": _STR, "city": _STR, "limit": _INT}}},
]  # fmt: skip


def leads(con: Any, a: dict[str, Any]) -> list[dict[str, Any]]:
    conds, params = ["state = ?"], [str(a["state"]).upper()]
    if a.get("grades"):
        conds.append(f"grade IN {s._in(str(g) for g in a['grades'])}")
    for key, sql in (("min_debt", "debt_amount >= ?"), ("min_value", "parcel_value >= ?"),
                     ("max_parcels", "owned_parcels <= ?")):  # fmt: skip
        if a.get(key) is not None:
            conds.append(sql)
            params.append(a[key])
    if a.get("exclude_homestead"):
        conds.append("NOT homestead_any")
    limit = min(int(a.get("limit") or 50), 500)
    return s._rows(con, f"SELECT * FROM leads WHERE {' AND '.join(conds)} "  # noqa: S608
                        "ORDER BY grade, net_equity_known DESC NULLS LAST, "
                        f"debt_amount DESC NULLS LAST LIMIT {limit}", params)  # fmt: skip


def call(name: str, a: dict[str, Any], db: Path = DEFAULT_DB) -> Any:
    """Run one tool against a read-only connection; returns plain data."""
    con = connect(db, read_only=True)
    try:
        if name == "search":
            hits = s.search(con, str(a["name"]), a.get("state"), a.get("kind"),
                            int(a.get("limit") or 25))  # fmt: skip
            return [asdict(h) | {"ref": h.ref} for h in hits]
        if name == "show":
            ref = str(a["ref"])
            if ":business:" in ref:
                return s.show_business(con, ref)
            e = s.show(con, ref)
            return None if e is None else asdict(e)
        if name == "parcel":
            as_of = date.fromisoformat(a["as_of"]) if a.get("as_of") else None
            return s.show_parcel(con, str(a["parcel"]), as_of)
        if name == "grade":
            return s.grade_pair(con, str(a["debtor_ref"]), str(a["owner_ref"]))
        if name == "network":
            return s.network(con, str(a["ref"]), int(a.get("hops") or 2))
        if name == "leads":
            return leads(con, a)
        if name == "facts":
            return facts_mod.fact_sheet(con, int(a["lead_id"]))
        if name == "address":
            return s.address_search(con, str(a["address"]), a.get("zip"), a.get("city"),
                                    int(a.get("limit") or 25))  # fmt: skip
        raise ValueError(f"unknown tool {name!r}")
    finally:
        con.close()


def handle(msg: dict[str, Any], db: Path = DEFAULT_DB) -> dict[str, Any] | None:
    """One JSON-RPC message in, its response out (None for a notification)."""
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:
        return None  # notifications (notifications/initialized, cancelled): no reply
    if method == "initialize":
        version = (msg.get("params") or {}).get("protocolVersion") or PROTOCOL
        result: Any = {"protocolVersion": version, "capabilities": {"tools": {}},
                       "serverInfo": {"name": "equity-tools", "version": "1"}}  # fmt: skip
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        p = msg.get("params") or {}
        try:
            text = json.dumps(call(str(p.get("name")), p.get("arguments") or {}, db),
                              indent=1, default=str)  # fmt: skip
            if len(text) > MAX_CHARS:
                text = text[:MAX_CHARS] + f"\n... cut at {MAX_CHARS:,} characters; narrow it"
            result = {"content": [{"type": "text", "text": text}], "isError": False}
        except Exception as exc:  # a tool error is a result the caller reads, not a crash
            result = {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}],
                      "isError": True}  # fmt: skip
    else:
        return {"jsonrpc": "2.0", "id": mid,
                "error": {"code": -32601, "message": f"method not found: {method}"}}  # fmt: skip
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve(inp: TextIO = sys.stdin, out: TextIO = sys.stdout, db: Path = DEFAULT_DB) -> None:
    """Newline-delimited JSON-RPC over stdio until stdin closes."""
    for line in inp:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            reply: dict[str, Any] | None = {
                "jsonrpc": "2.0", "id": None,
                "error": {"code": -32700, "message": "parse error"}}  # fmt: skip
        else:
            reply = handle(msg, db)
        if reply is not None:
            out.write(json.dumps(reply, default=str) + "\n")
            out.flush()


if __name__ == "__main__":  # pragma: no cover
    serve()
