export const meta = {
  name: 'asset-trace',
  description: 'Forensic asset trace for one debtor: gather the deterministic forensic evidence (timeline, lien priority, transfer badges, entity ring, household), an investigator writes cited findings, a skeptic tries to break each one, and a dossier goes to data/derived/forensic/',
  whenToUse: 'Investigate one debtor in depth: "trace the assets of <ref>" or "forensic dossier on lead 123". args: {ref} (source_id:party_id) or {lead_id}, optional {label}.',
  phases: [
    { title: 'Gather', detail: 'equity.forensic outputs saved as JSON' },
    { title: 'Investigate', detail: 'forensic-trace skill: cited findings' },
    { title: 'Challenge', detail: 'one skeptic per finding' },
    { title: 'Dossier', detail: 'data/derived/forensic/<label>.md' },
  ],
}

const a = args || {}
if (!a.ref && !a.lead_id) {
  log('Give args.ref (source_id:party_id) or args.lead_id.')
  return { error: 'missing ref or lead_id' }
}
const LABEL = a.label || (a.ref ? a.ref.replace(/[^A-Za-z0-9._-]+/g, '_') : `lead-${a.lead_id}`)
const DIR = `data/derived/forensic/${LABEL}`

const GATHERED = {
  type: 'object',
  properties: {
    debtor_ref: { type: 'string' },
    files: { type: 'array', items: { type: 'string' } },
    commands: { type: 'array', items: { type: 'string' } },
  },
  required: ['debtor_ref', 'files', 'commands'],
}

const FINDINGS = {
  type: 'object',
  properties: {
    summary: { type: 'string' },
    findings: { type: 'array', items: { type: 'object', properties: {
      id: { type: 'string' },
      kind: { type: 'string', enum: ['lien_position', 'transfer', 'entity', 'household',
                                     'cross_state', 'timeline', 'identity', 'other'] },
      claim: { type: 'string' },
      refs: { type: 'array', items: { type: 'string' } },
      strength: { type: 'string', enum: ['strong', 'moderate', 'weak'] },
      why: { type: 'string' },
      confirm_by: { type: 'string' },
    }, required: ['id', 'kind', 'claim', 'refs', 'strength', 'why', 'confirm_by'] } },
    open_questions: { type: 'array', items: { type: 'string' } },
  },
  required: ['summary', 'findings', 'open_questions'],
}

const CHALLENGE = {
  type: 'object',
  properties: {
    holds: { type: 'boolean' },
    strength: { type: 'string', enum: ['strong', 'moderate', 'weak', 'broken'] },
    reason: { type: 'string' },
    refs: { type: 'array', items: { type: 'string' } },
  },
  required: ['holds', 'strength', 'reason', 'refs'],
}

phase('Gather')
const who = a.ref
  ? `the debtor record ${a.ref}`
  : `lead ${a.lead_id} (run uv run python -m equity.facts ${a.lead_id} first and use its best ` +
    `A or B identity pair's debtor_ref; save the sheet too)`
const gathered = await agent(
  `Gather forensic evidence for ${who}. Create ${DIR}/ (git-ignored; it names people) and save ` +
  `each command's JSON output there: uv run python -m equity.forensic --timeline REF, --badges ` +
  `REF, --ring REF, --household REF, and for every owned parcel that one of the debtor's open ` +
  `debt documents is recorded against (from the timeline or the facts sheet), --stack ` +
  `<parcel_uid> --lien <instrument_uid>. Return the debtor ref, the files and the commands.`,
  { label: 'gather', schema: GATHERED })
if (!gathered || !gathered.files.length) {
  log('Nothing gathered.')
  return { label: LABEL, error: 'no evidence gathered' }
}

phase('Investigate')
const inv = await agent(
  `You are the investigator. Follow the forensic-trace skill (.claude/skills/forensic-trace/` +
  `SKILL.md). Read every file in ${DIR}/ (${gathered.files.join(', ')}) and, where it helps, ` +
  `run equity.search --grade/--show/--parcel. Return findings, each a single claim with its ` +
  `refs, a strength and why, and what document would confirm or break it. Facts, leads and ` +
  `open questions only: no legal conclusions. Do not write files.`,
  { label: 'investigate', phase: 'Investigate', schema: FINDINGS })
if (!inv || !inv.findings.length) {
  log('No findings.')
  return { label: LABEL, findings: 0 }
}

const checked = await parallel(inv.findings.map((f) => () =>
  agent(
    `You are a skeptic. Try to break this finding about ${gathered.debtor_ref} using only the ` +
    `files in ${DIR}/ and the equity search and forensic tools: a namesake (check --grade and ` +
    `addresses), a genuine arm's-length sale, a release the finding missed, a senior lien it ` +
    `ignored, a value basis that is stale or assessed rather than market, a business that is ` +
    `a different entity with a similar name. Say whether it holds and at what strength. ` +
    `Finding: ${JSON.stringify(f)}`,
    { label: `challenge:${f.id}`, phase: 'Challenge', schema: CHALLENGE },
  ).then((c) => ({ ...f, challenge: c }))))

const findings = checked.filter(Boolean)
const broken = findings.filter((f) => f.challenge && (!f.challenge.holds || f.challenge.strength === 'broken'))
log(`${findings.length} findings; ${broken.length} broken by the skeptic`)

phase('Dossier')
const report = await agent(
  `Write the forensic dossier to data/derived/forensic/${LABEL}.md (never elsewhere). Open ` +
  `with: who (name and ref), the identity basis, a five-line summary, and the purpose line ` +
  `"Evidence for counsel's review in recovering a debt the business holds or may buy; not a ` +
  `legal conclusion and not a consumer report." Then sections: Lien position and equity behind ` +
  `the lien, Transfers out (badges per deed), Entities, Household and other states, Timeline ` +
  `(dated, cited), Findings that held (strongest first, with the skeptic's view), Findings the ` +
  `skeptic broke (and why), Open questions and the documents to pull. Cite every fact by ref. ` +
  `Reply with the path only. Data: ${JSON.stringify({ summary: inv.summary, findings, open: inv.open_questions, files: gathered.files })}`,
  { label: 'dossier' })

return { label: LABEL, report, findings: findings.length, broken: broken.length }
