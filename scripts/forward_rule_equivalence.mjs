// Behavioral equivalence of the browser rule actually deployed on each needs_evidence session
// (git blobs recorded in forensics-2) versus the reconstruction rule (forward_observation_engine fo-1.0).
// Read-only. Extracts candidateDecision / classify / eligibility from the historical blobs, runs them on a
// deterministic input grid and compares with the reconstruction mapping. Output: JSON lines on stdout.
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import vm from 'node:vm';

const git = (...a) => execFileSync('git', a, { encoding: 'utf8', maxBuffer: 64 << 20 });
const blob = (sha) => git('cat-file', '-p', sha);

function extractFunction(src, name) {
  const i = src.indexOf(`function ${name}(`);
  if (i < 0) return null;
  let j = src.indexOf('{', i), depth = 0;
  for (let k = j; k < src.length; k++) {
    if (src[k] === '{') depth++;
    else if (src[k] === '}') { depth--; if (depth === 0) return src.slice(i, k + 1); }
  }
  return null;
}
function eligibilityExprs(src) {
  const f = extractFunction(src, 'assistantCandidates') || '';
  const fear = (f.match(/if\(mode==='fear'\)\{eligible=([^;]+);/) || [])[1] || null;
  const other = (f.match(/\}else\{eligible=([^;]+);/) || [])[1] || null;
  const cap = (f.match(/\.slice\(0,(\d+)\)\s*}?\s*$/) || f.match(/\.slice\(0,(\d+)\)/) || [])[1] || null;
  return { fear, other, cap: cap && Number(cap) };
}
// Reconstruction rule (mirror of scripts/forward_observation_engine.py, fo-1.0)
const R = {
  mode(spx, ixic, vix) {
    if ((ixic !== null && ixic <= -0.04) || (spx !== null && spx <= -0.035) || (vix !== null && vix >= 35)) return 'fear';
    if ((ixic !== null && ixic <= -0.025) || (spx !== null && spx <= -0.02) || (vix !== null && vix >= 28)) return 'fear';
    if ((ixic !== null && ixic <= -0.015) || (spx !== null && spx <= -0.0125) || (vix !== null && vix >= 25)) return 'fear';
    if (((ixic !== null && ixic >= 0.025) || (spx !== null && spx >= 0.02)) && (vix === null || vix < 20)) return 'greed';
    return 'normal';
  },
  eligible(mode, stage, score) { return mode === 'fear' ? !['趋势恶化', '趋势退潮'].includes(stage) && (score === null || score > -20) : score !== null && score >= 75; },
  decision(stage, mode) {
    if (/退潮|恶化/.test(stage)) return '等待修复'; if (/二次启动|启动|重新|修复中/.test(stage)) return '修复候选';
    if (mode === 'fear') return '大跌机会候选'; if (/钝化|高位/.test(stage)) return '高位观察'; return '继续观察';
  },
};
const STAGES = ['趋势启动', '二次启动', '趋势延续', '修复中', '高位钝化', '趋势退潮', '趋势恶化', '震荡观察', ''];
const SCORES = [null, -90, -21, -20, -19, 0, 50, 74, 75, 76, 95];
const CHG = [null, -0.05, -0.04, -0.03, -0.025, -0.02, -0.015, -0.0125, -0.01, 0, 0.02, 0.025, 0.03];
const VIX = [null, 15, 19.9, 20, 25, 28, 35];

function compare(blobs) {
  const dj = blob(blobs['docs/assets/decision-journal.js']), ia = blob(blobs['docs/assets/investment-assistant.js']), sw = blob(blobs['docs/assets/stock-watchlist.js']);
  const ctx = { n: (v) => (Number.isFinite(Number(v)) && v !== null && v !== '' ? Number(v) : null) };
  vm.createContext(ctx);
  const cd = extractFunction(dj, 'candidateDecision'), cl = extractFunction(ia, 'classify'), el = eligibilityExprs(sw);
  const out = { functions_found: { candidateDecision: !!cd, classify: !!cl, eligibility_fear: !!el.fear, eligibility_other: !!el.other }, candidate_cap: el.cap, diffs: [] };
  if (cd) vm.runInContext(cd, ctx);
  if (cl) vm.runInContext(cl, ctx);
  if (el.fear) vm.runInContext(`function eligFear(stage,score){return ${el.fear}}`, ctx);
  if (el.other) vm.runInContext(`function eligOther(stage,score){return ${el.other}}`, ctx);
  let n = 0;
  if (cl) for (const s of CHG) for (const i of CHG) for (const v of VIX) {
    n++; const h = ctx.classify(s, i, v)?.mode, r = R.mode(s, i, v);
    if (h !== r) out.diffs.push({ fn: 'classify', input: [s, i, v], historical: h, reconstruction: r });
  }
  if (cd) for (const st of STAGES) for (const m of ['fear', 'normal', 'greed']) {
    n++; const h = ctx.candidateDecision({ stage: st }, { mode: m }), r = R.decision(st, m);
    if (h !== r) out.diffs.push({ fn: 'candidateDecision', input: [st, m], historical: h, reconstruction: r });
  }
  for (const st of STAGES) for (const sc of SCORES) {
    if (el.fear) { n++; const h = !!ctx.eligFear(st, sc), r = R.eligible('fear', st, sc); if (h !== r) out.diffs.push({ fn: 'eligible_fear', input: [st, sc], historical: h, reconstruction: r }); }
    if (el.other) { n++; const h = !!ctx.eligOther(st, sc), r = R.eligible('normal', st, sc); if (h !== r) out.diffs.push({ fn: 'eligible_other', input: [st, sc], historical: h, reconstruction: r }); }
  }
  out.grid_cases = n;
  out.equivalent_on_grid = Object.values(out.functions_found).every(Boolean) && out.diffs.length === 0;
  return out;
}

const audit = fs.readFileSync('research/archive/forward_evidence_audit.jsonl', 'utf8').split('\n').filter(Boolean).map(JSON.parse);
const latest = {};
for (const e of audit) if (e.proposal_version === 'forensics-2') latest[e.session] = e;
import crypto from 'node:crypto';
const UNCERTAIN = [
  'market mode: the browser classified from live intraday SPX/IXIC/VIX quotes at page time; the reconstruction uses the published daily close change, so the mode can differ on volatile days',
  'candidate set: the browser kept at most `candidate_cap` eligible symbols ranked by research basis / private thesis / learning adjustment; the reconstruction keeps every eligible symbol, so browser candidates are a subset',
  'stage/score: both come from the same build (index.html embeds the data.json trend_pulse of that commit), but the page the owner had open may have been an earlier intraday build',
  'entry price: the browser used the stock-quote daily close feed (dailyClose/dailyAsOf), the reconstruction uses data.json close',
];
const rows = [];
for (const [s, e] of Object.entries(latest).sort()) {
  if (e.review_class !== 'needs_evidence') continue;
  const r = compare(e.evidence.rule_file_blobs);
  rows.push({ session: s, rule_file_blobs: e.evidence.rule_file_blobs, ...r, diffs: r.diffs.slice(0, 12), diff_count: r.diffs.length });
}
for (const r of rows) console.log(JSON.stringify({ ...r, rule_file_blobs: undefined }));
if (process.argv.includes('--append')) {
  const have = new Set(audit.map((e) => e.audit_id));
  const now = new Date().toISOString().replace(/\.\d+Z$/, 'Z');
  const lines = [];
  for (const r of rows) {
    const id = crypto.createHash('sha256').update(`${r.session}|rule-equivalence-1|${JSON.stringify(r.rule_file_blobs)}`).digest('hex').slice(0, 20);
    if (have.has(id)) continue;
    lines.push(JSON.stringify({ audit_id: id, session: r.session, proposal_version: 'rule-equivalence-1', kind: 'rule_equivalence_check',
      reviewer: 'claude-tool', created_at: now, rule_file_blobs: r.rule_file_blobs, reconstruction_rule: 'forward_observation_engine fo-1.0 (rule_hash ff28762ad7a5ed6f)',
      functions_found: r.functions_found, grid_cases: r.grid_cases, diff_count: r.diff_count, diffs: r.diffs,
      equivalent_on_grid: r.equivalent_on_grid, candidate_cap: r.candidate_cap, uncertainties: UNCERTAIN,
      review_class: r.equivalent_on_grid ? 'ready_for_independent_review' : 'needs_evidence',
      note: 'Evidence only. Promotion requires an independent reviewer entry; browser rows stay grade C / late_upload.' }));
  }
  if (lines.length) fs.appendFileSync('research/archive/forward_evidence_audit.jsonl', lines.join('\n') + '\n');
  console.log(JSON.stringify({ appended: lines.length }));
}
