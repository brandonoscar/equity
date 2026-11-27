export const meta = {
  name: 'score-people',
  description: 'Score the best-ranked leads of a state for recoverability by hand against the owner rubric: deterministic fact sheets, one scorer agent per lead, a blind second scorer, disagreements flagged, results appended to a private ledger',
  whenToUse: 'Score many leads at once: "score the top 20 OH leads". args: {state, top, label} or {lead_ids: [...], label}.',
  phases: [
    { title: 'Facts', detail: 'equity.facts writes one fact sheet per lead' },
    { title: 'Score', detail: 'one scorer per lead, score-rubric skill' },
    { title: 'Check', detail: 'a blind second scorer per lead; disagreements flagged' },
    { title: 'Ledger', detail: 'append to data/derived/scores/ledger.jsonl and write the report' },
  ],
}

const a = args || {}
const STATE = (a.state || 'OH').toUpperCase()
const TOP = Math.min(a.top || 10, 50)
const LABEL = a.label || `${STATE.toLowerCase()}-${new Date().toISOString().slice(0, 10)}`
const DIR = `data/derived/scores/facts/${LABEL}`

const SHEETS = {
  type: 'object',
  properties: {
    sheets: { type: 'array', items: { type: 'object', properties: {
      lead_id: { type: 'number' }, path: { type: 'string' } }, required: ['lead_id', 'path'] } },
    command: { type: 'string' },
  },
  required: ['sheets', 'command'],
}

const SCORE = {
  type: 'object',
  properties: {
    lead_id: { type: 'number' },
    rubric_version: { type: 'string' },
    rubric_status: { type: 'string' },
    sheet_sha256: { type: 'string' },
    gate: { type: ['string', 'null'] },
    factors: { type: 'array', items: { type: 'object', properties: {
      id: { type: 'string' }, band: { type: 'string' }, points: { type: 'number' },
      max: { type: 'number' }, facts: { type: 'array', items: { type: 'string' } } },
      required: ['id', 'band', 'points', 'facts'] } },
    deductions: { type: 'array', items: { type: 'object', properties: {
      id: { type: 'string' }, points: { type: 'number' },
      facts: { type: 'array', items: { type: 'string' } } }, required: ['id', 'points', 'facts'] } },
    total: { type: ['number', 'null'] },
    tier: { type: ['string', 'null'] },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
    gaps_used: { type: 'array', items: { type: 'string' } },
    would_change: { type: 'array', items: { type: 'string' } },
  },
  required: ['lead_id', 'rubric_version', 'rubric_status', 'sheet_sha256', 'gate', 'factors',
             'deductions', 'total', 'tier', 'confidence', 'gaps_used'],
}

const scorePrompt = (lead, role) =>
  `${role} Use the score-rubric skill (.claude/skills/score-rubric/SKILL.md) to score lead ` +
  `${lead.lead_id} from its fact sheet at ${lead.path} against config/scoring_rubric.yaml. ` +
  `Score only from the sheet (cite refs); do not write any file; return the JSON.`

phase('Facts')
let sheets
if (Array.isArray(a.lead_ids) && a.lead_ids.length) {
  sheets = await agent(
    `Run: uv run python -m equity.facts ${a.lead_ids.slice(0, 50).join(' ')} --out ${DIR} ` +
    `and return each lead id with the file it wrote, and the command you ran.`,
    { label: 'facts', schema: SHEETS })
} else {
  sheets = await agent(
    `Run: uv run python -m equity.facts --state ${STATE} --top ${TOP} --out ${DIR} and return ` +
    `each lead id with the file it wrote (the file name is <lead_id>.json), and the command.`,
    { label: 'facts', schema: SHEETS })
}
if (!sheets || !sheets.sheets.length) {
  log('No fact sheets: is the leads table built (search_index compact)?')
  return { state: STATE, scored: [] }
}
log(`${sheets.sheets.length} fact sheets in ${DIR}`)

const results = await pipeline(
  sheets.sheets,
  (lead) => agent(scorePrompt(lead, 'You are the scorer.'),
                  { label: `score:${lead.lead_id}`, phase: 'Score', schema: SCORE }),
  async (first, lead) => {
    if (!first) return null
    // Blind: the second scorer never sees the first score, so it cannot anchor on it.
    const second = await agent(scorePrompt(lead, 'You are an independent second scorer; be strict about which band the facts support.'),
                               { label: `check:${lead.lead_id}`, phase: 'Check', schema: SCORE })
    const diff = second && first.total != null && second.total != null
      ? Math.abs(first.total - second.total) : null
    const agreed = !!second && first.gate === second.gate && first.tier === second.tier &&
      (diff === null || diff <= 10)
    return { lead, first, second, agreed, diff }
  },
)

const done = results.filter(Boolean)
const disputed = done.filter((r) => !r.agreed)
log(`${done.length} scored; ${disputed.length} disputed (tier, gate or >10 points apart)`)

phase('Ledger')
const report = await agent(
  `Append one JSON line per lead to data/derived/scores/ledger.jsonl (create the folder; it is ` +
  `git-ignored because it names people; never write elsewhere). Each line: {"scored_at": now ` +
  `ISO, "label": ${JSON.stringify(LABEL)}, "lead_id", "rubric_version", "rubric_status", ` +
  `"sheet_sha256", "score": the first scorer's JSON, "check": the second's, "agreed", "diff"}. ` +
  `Then write data/derived/scores/${LABEL}.md: open with the rubric version and status (say ` +
  `plainly if it is a DRAFT not approved by the owner), the counts per tier and the disputed ` +
  `leads; then one section per lead, best tier first: debtor name and state from the fact ` +
  `sheet, tier, total, confidence, the factors and deductions with their facts, both scorers' ` +
  `totals when they disagree, gaps and what would change the tier. Reply with the two paths. ` +
  `Data: ${JSON.stringify(done.map((r) => ({ path: r.lead.path, first: r.first, second: r.second, agreed: r.agreed, diff: r.diff })))}`,
  { label: 'ledger' },
)

return {
  state: STATE,
  label: LABEL,
  report,
  disputed: disputed.map((r) => r.lead.lead_id),
  tiers: done.reduce((m, r) => ({ ...m, [r.first.tier || r.first.gate || 'none']: (m[r.first.tier || r.first.gate || 'none'] || 0) + 1 }), {}),
}
