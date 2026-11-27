export const meta = {
  name: 'verify-leads',
  description: 'Shortlist debtors who own property from the search index, verify each lead with an independent agent, try to refute the strong ones, and write a ranked, cited report',
  whenToUse: 'Many leads at once: "find and verify leads in OH with debts over $25k". args: {state, min_debt, min_value, max_parcels, limit, label} or {leads: [...]} from a lead-scan.',
  phases: [
    { title: 'Shortlist', detail: 'query debtor_owner_candidates with the criteria, drop obvious rejects' },
    { title: 'Verify', detail: 'one lead-verifier agent per lead' },
    { title: 'Refute', detail: 'a skeptic tries to break each A/B identity' },
    { title: 'Report', detail: 'ranked report under data/derived/leads/' },
  ],
}

const a = args || {}
const STATE = (a.state || 'OH').toUpperCase()
const LIMIT = Math.min(a.limit || 20, 100)
const LABEL = a.label || `${STATE.toLowerCase()}-leads`

const LEADS = {
  type: 'object',
  properties: {
    leads: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string' },
          name_key: { type: 'string' },
          state: { type: 'string' },
          debts: { type: 'number' },
          debt_amount: { type: ['number', 'null'] },
          parcels: { type: 'number' },
          parcel_value: { type: ['number', 'null'] },
          debtor_refs: { type: 'array', items: { type: 'string' } },
          owner_refs: { type: 'array', items: { type: 'string' } },
          parcel_uids: { type: 'array', items: { type: 'string' } },
        },
        required: ['name', 'name_key', 'state', 'debtor_refs', 'owner_refs'],
      },
    },
    dropped: { type: 'array', items: { type: 'string' } },
    query: { type: 'string' },
  },
  required: ['leads', 'dropped', 'query'],
}

const VERDICT = {
  type: 'object',
  properties: {
    name: { type: 'string' },
    state: { type: 'string' },
    grade: { type: 'string', enum: ['A', 'B', 'C', 'reject'] },
    rule: { type: 'string' },
    debt_total: { type: ['number', 'null'] },
    gross_value: { type: ['number', 'null'] },
    value_basis: { type: 'string' },
    homestead: { type: ['boolean', 'null'] },
    senior_debt: { type: 'string' },
    red_flags: { type: 'array', items: { type: 'string' } },
    evidence: { type: 'array', items: { type: 'string' } },
    gaps: { type: 'array', items: { type: 'string' } },
  },
  required: ['name', 'state', 'grade', 'rule', 'red_flags', 'evidence', 'gaps'],
}

const REFUTE = {
  type: 'object',
  properties: {
    refuted: { type: 'boolean' },
    reason: { type: 'string' },
    evidence: { type: 'array', items: { type: 'string' } },
  },
  required: ['refuted', 'reason', 'evidence'],
}

phase('Shortlist')
let shortlist
if (Array.isArray(a.leads) && a.leads.length) {
  shortlist = { leads: a.leads.slice(0, LIMIT), dropped: [], query: 'leads passed in args' }
} else {
  shortlist = await agent(
    `Use the lead-scan skill's query on the stored table debtor_owner_candidates (equity-search ` +
    `MCP server, or the read-only DuckDB file data/search_index.duckdb) for state '${STATE}' with ` +
    `debt_amount >= ${a.min_debt || 10000}, parcel_value >= ${a.min_value || 50000}, ` +
    `parcels <= ${a.max_parcels || 5}, ordered by debt_amount DESC, LIMIT ${LIMIT * 2}. Drop the ` +
    `rejects the skill lists (governments and agencies, placeholders, withheld names, one-word ` +
    `names, names held by more than 25 records) and return at most ${LIMIT} leads, plus the names ` +
    `you dropped with the reason, and the SQL you ran.`,
    { label: 'shortlist', schema: LEADS },
  )
}
if (!shortlist || !shortlist.leads.length) {
  log('No leads matched the criteria.')
  return { state: STATE, leads: [], dropped: shortlist ? shortlist.dropped : [] }
}
log(`${shortlist.leads.length} leads; ${shortlist.dropped.length} dropped before verification`)

const results = await pipeline(
  shortlist.leads,
  (lead) =>
    agent(
      `Verify this lead and return the verdict. Lead: ${JSON.stringify(lead)}`,
      { label: `verify:${lead.name}`, phase: 'Verify', agentType: 'lead-verifier', schema: VERDICT },
    ),
  async (verdict, lead) => {
    if (!verdict) return null
    if (verdict.grade !== 'A' && verdict.grade !== 'B') return { lead, verdict, refute: null }
    const refute = await agent(
      `You are a skeptic. Try to show that the debtor and the property owner below are NOT the ` +
      `same person or business, using only the equity search tools (uv run python -m ` +
      `equity.search --show/--parcel/--network, keyed SQL on the equity-search MCP server). ` +
      `Look for: different addresses or ZIPs, a JR/SR or middle-name conflict, a very common ` +
      `name, a creditor or agency name, a parcel that belongs to another record, a debt ` +
      `recorded against a different parcel. Default to refuted=false only when the identity ` +
      `evidence holds up. Verdict to test: ${JSON.stringify(verdict)} Lead refs: ` +
      `${JSON.stringify({ debtor_refs: lead.debtor_refs, owner_refs: lead.owner_refs })}`,
      { label: `refute:${lead.name}`, phase: 'Refute', schema: REFUTE },
    )
    if (refute && refute.refuted) {
      verdict = { ...verdict, grade: 'C', red_flags: [...verdict.red_flags, `skeptic: ${refute.reason}`] }
    }
    return { lead, verdict, refute }
  },
)

const done = results.filter(Boolean)
const order = { A: 0, B: 1, C: 2, reject: 3 }
done.sort((x, y) =>
  (order[x.verdict.grade] - order[y.verdict.grade]) ||
  ((y.verdict.debt_total || 0) - (x.verdict.debt_total || 0)))
const skipped = shortlist.leads.length - done.length
if (skipped) log(`${skipped} leads returned no verdict (agent skipped or failed)`)

phase('Report')
const report = await agent(
  `Write a ranked lead report as Markdown to data/derived/leads/${LABEL}.md (create the folder; ` +
  `it is git-ignored because it names people; never write it anywhere else). One section per ` +
  `lead in this order, grade first: name, grade and rule, debt total, gross value with basis and ` +
  `year, homestead, senior debt, red flags (include any skeptic finding), and the evidence ` +
  `lines with their refs, then gaps. Open with the criteria (${JSON.stringify(shortlist.query)}), ` +
  `the counts per grade, and the names dropped before verification with reasons. Then reply ` +
  `with the file path only. Data: ${JSON.stringify({ dropped: shortlist.dropped, results: done })}`,
  { label: 'report' },
)

return {
  state: STATE,
  report,
  grades: done.reduce((m, r) => ({ ...m, [r.verdict.grade]: (m[r.verdict.grade] || 0) + 1 }), {}),
  leads: done.map((r) => ({ name: r.verdict.name, grade: r.verdict.grade, rule: r.verdict.rule,
                            debt_total: r.verdict.debt_total, gross_value: r.verdict.gross_value })),
}
