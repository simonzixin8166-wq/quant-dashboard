// Verifies the QA verdict annotations without launching a browser.
const fs=require('fs'),path=require('path'),assert=require('assert');
const src=fs.readFileSync(path.join(__dirname,'..','scripts','autonomous_site_qa.mjs'),'utf8');
const start=src.indexOf('function qaVerdictLines');
const end=src.indexOf('report.overall=report.decision_readiness.status;');
assert(start>0&&end>start,'helpers must sit directly before the final verdict statement');
const lines=[];const log=console.log;console.log=x=>lines.push(String(x));
const {qaVerdictLines,emitQaAnnotations}=new Function(src.slice(start,end)+';return {qaVerdictLines,emitQaAnnotations};')();
const pass={overall:'PASS',decision_readiness:{status:'PASS'},engineering_qa:{status:'PASS'},interaction:{status:'PASS'},
  business_data:{status:'PASS',market_as_of:'2026-10-07',expected_market_date:'2026-10-07',business_freshness:'fresh',decision_eligible:true},
  server_action:{status:'PASS',server_status:'clear',judgment_basis:'evaluated',server_market_as_of:'2026-10-07',server_snapshot_current:true},
  investment_data_qa:{status:'PASS'},learning_guardrails:{status:'PASS'},fatal_console_errors:[],http_errors:[]};
emitQaAnnotations(pass);
assert.strictEqual(lines.length,1);
assert(lines[0].startsWith('::notice title=MyAlpha QA verdict::QA_VERDICT overall=PASS'));
for(const k of ['business_data=PASS','server_action=PASS','engineering_qa=PASS','investment_data_qa=PASS','market_as_of=2026-10-07','judgment_basis=evaluated','server_snapshot_current=true'])
  assert(lines[0].includes(k),k);
lines.length=0;
const fail=JSON.parse(JSON.stringify(pass));fail.overall='FAIL';fail.server_action.status='FAIL';fail.server_action.judgment_basis='market_data_stale\n100%';
emitQaAnnotations(fail);
assert.strictEqual(lines.length,2);
assert(lines[0].includes('market_data_stale%0A100%25'),'workflow-command escaping');
assert(lines[1].startsWith('::error title=MyAlpha QA failing sections::QA_FAILING server_action'));
assert(!/position|account|symbol/i.test(qaVerdictLines(pass).join(' ')),'sanitized fields only');
console.log=log;console.log('PASS QA verdict annotations');
