// P0-1: WATCH reasons must be per-symbol and explain have/missing; auto drafts never count as a verified Thesis.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const ctx={window:{}};vm.createContext(ctx);
vm.runInContext(fs.readFileSync(__dirname+'/../docs/assets/signal-policy.js','utf8'),ctx);
const P=ctx.window.MAVSignalPolicy;
const msft={verified:false,status:'draft_only',have:['官方披露 8-K 2026-09-02','本季/年度业务数据（10-K 2026-07-29）','直接相关新闻 1 条'],missing:['具体风险条目（需从原文提炼）','失效条件（何种情况证明上涨理由错误，需你确认）'],last_evidence_date:'2026-09-30',excluded_tagged_only_news:4,next_trigger:'新的 10-Q/10-K/8-K'};
const iren={verified:false,status:'draft_only',have:['官方披露 10-K 2026-08-20'],missing:['直接相关的近期催化剂','失效条件（何种情况证明上涨理由错误，需你确认）'],last_evidence_date:'2026-08-20',excluded_tagged_only_news:0,next_trigger:'新的官方披露或直接相关新闻'};
const cases=[
 {symbol:'AMD',stage:'趋势启动',score:40,autoCovered:false},
 {symbol:'ORCL',stage:'修复中',score:10,autoCovered:false},
 {symbol:'DRAM',stage:'趋势延续',score:80,autoCovered:false},
 {symbol:'MSFT',stage:'二次启动',score:45,autoCovered:true,readiness:msft},
 {symbol:'IREN',stage:'趋势启动',score:20,autoCovered:true,readiness:iren},
 {symbol:'NBIS',stage:'趋势延续',score:60,autoCovered:true,readiness:null},
];
const out=cases.map(c=>P.classify({...c,held:false,hasThesis:false}));
out.forEach((r,i)=>{
  assert.strictEqual(r.action,'WATCH',cases[i].symbol+' must stay WATCH without a verified thesis');
  assert(!/缺少可验证 Thesis/.test(r.reason),'generic text removed');
  assert(r.reason.includes(cases[i].symbol),'reason names the symbol');
  assert(r.next_confirmation&&r.next_confirmation.length>4);
});
assert.strictEqual(new Set(out.map(r=>r.reason)).size,cases.length,'no identical reasons across symbols');
assert(/未进入自动研究覆盖/.test(out[0].reason));
assert(/已具备：官方披露 8-K/.test(out[3].reason)&&/仍缺少：具体风险条目/.test(out[3].reason)&&/已排除 4 条/.test(out[3].reason));
assert(/系统证据草稿（未经你核实）/.test(out[5].reason));
assert.strictEqual(out[3].thesis_status,'draft_only');
// a draft marked verified:true by mistake still can't unlock entry when hasThesis is false
assert.strictEqual(P.classify({symbol:'MSFT',stage:'趋势启动',score:40,held:false,hasThesis:false,autoCovered:true,readiness:{...msft,verified:true}}).action,'WATCH');
// manual thesis path unchanged
assert.strictEqual(P.classify({symbol:'MSFT',stage:'趋势启动',score:40,held:false,hasThesis:true}).action,'EARLY_ENTRY');
// held path unchanged (gap text only for non-held)
assert.strictEqual(P.classify({symbol:'MSFT',stage:'趋势延续',score:40,held:true,hasThesis:false}).action,'HOLD');
console.log('PASS thesis explainability (6 symbols distinct, drafts never verified)');
