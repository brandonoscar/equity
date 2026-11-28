---
name: golden-session
description: Run a golden-case session with a human verifier - sample stratified real leads into a private checklist, walk the verifier through each case's documents, record verdicts in cases.yaml, promote verified cases to pseudonymized CI scenarios, and fix any rule the verdicts disagree with. Use when asked to build, verify or add golden cases, or to run a verification session.
---

# Golden-case session

Read `docs/golden-cases.md` first. The verifier decides; you prepare, look things up and
record. Never fill in a verdict yourself, and never promote a case nobody verified.

1. **Before the session:** the index must be current (`uv run python -m equity.search_index
   status`; `leads` exists). Run `uv run python -m equity.golden candidates --per-rule 3
   --label <date>` (add `--states OH FL ...` to focus). Tell the verifier how many cases and
   which strata.
2. **Per case, with the verifier:** show the checklist entry, then the evidence on request:
   `uv run python -m equity.search --grade <debtor_ref> <owner_ref>`, `--show <ref>`,
   `--parcel <uid>`, `uv run python -m equity.forensic --timeline <ref>`. Say what each
   document shows; the verifier reads the recorded document itself where it matters. Record
   their answer in `cases.yaml` (`same_person`, `grade`, the pair, `documents`, `verified_by`,
   `note`) exactly as they say it.
3. **After:** `uv run python -m equity.golden promote <cases.yaml>`. Read every written
   `tests/e2e/scenarios/golden_*.yaml`: no real name, street, ZIP or id may appear (the tool
   replaces them; check anyway). Run `uv run pytest tests/e2e`. A failing golden case means
   the pipeline disagrees with the verifier: find the rule and fix it, never edit the case to
   pass. Commit the scenarios and the fix together.

Cases name real people: `config/private/` is git-ignored; never paste case details into a
commit message, a PR or a chat channel others read.
