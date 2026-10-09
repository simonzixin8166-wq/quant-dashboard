// P0-3: held positions vs research watchlist — differentiated regression cases.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
function load(opt){
  const win={addEventListener(){},dispatchEvent(){},CustomEvent:function(){},setTimeout(){},isAdmin:false};
  const doc={readyState:'loading',addEventListener(){},getElementById(){return null},visibilityState:'hidden'};
  if(opt)win.OptionV2=opt;
  const ctx={window:win,document:doc,setTimeout(){},setInterval(){},clearInterval(){},fetch:async()=>({ok:false}),CustomEvent:function(){},console};
  vm.createContext(ctx);
  for(const f of ['signal-policy','autonomous-agent','product-intelligence'])vm.runInContext(fs.readFileSync(`${__dirname}/../docs/assets/${f}.js`,'utf8'),ctx);
  return win;
}
const optApi=(open,hist=[],loaded=true)=>({positionsLoaded:()=>loaded,getPositions:()=>open,getHistory:()=>hist,getCachedQuote:()=>null,quoteFreshness:()=>({usable:false})});
const auth={decision_eligible:true};
let n=0;const ok=(c,m)=>{assert(c,m);n++};

// 1 not logged in → unknown, never claims held
let W=load(null),PI=W.MAVProductIntelligence;
let s=PI.explicitSignal({symbol:'AMD',stage:'趋势启动',score:40},auth);
ok(s.action==='WATCH'&&s.position_context.kind==='unknown'&&s.research_only,'1 unknown exposure');
// 2 loaded, no options → 未持仓 + research-only disclaimer in text
W=load(optApi([]));PI=W.MAVProductIntelligence;
s=PI.explicitSignal({symbol:'ORCL',stage:'修复中',score:10},auth);
ok(s.position_context.kind==='none'&&/WATCH 是研究态，不是持仓建议/.test(PI.stockActionText(s)),'2 none + disclaimer');
// 3 non-held trend deterioration never yields REDUCE/EXIT/HOLD
s=PI.explicitSignal({symbol:'DRAM',stage:'趋势恶化',score:-80},auth);
ok(!['HOLD','NO_ADD','REDUCE','EXIT'].includes(s.action),'3 non-held never sell/hold');
// 4 explicitly held deterioration may say REDUCE (formal path) and is not research-only
s=PI.explicitSignal({symbol:'DRAM',stage:'趋势恶化',score:-80,held:true},auth);
ok(s.action==='REDUCE'&&s.research_only===false,'4 held REDUCE path intact');
// 5 option exposure → context first and names the contract
W=load(optApi([{id:1,symbol:'IREN',side:'short',opt_type:'put',strike:30,expiry:'2026-11-20'}]));PI=W.MAVProductIntelligence;
s=PI.explicitSignal({symbol:'IREN',stage:'趋势启动',score:20},auth);
ok(s.position_context.kind==='option_exposure'&&/^你在 IREN 有 1 个期权仓位（卖出 30P 2026-11-20）/.test(PI.stockActionText(s)),'5 option exposure first');
// 6 option exposure does not turn the stock into a held-share HOLD
ok(s.action==='WATCH'&&s.position_context.held_shares===null,'6 option exposure ≠ share ownership');
// 7 assigned history → asks the user to confirm, does not infer shares
W=load(optApi([],[{symbol:'SOFI',status:'assigned'}]));PI=W.MAVProductIntelligence;
s=PI.explicitSignal({symbol:'SOFI',stage:'趋势延续',score:60},auth);
ok(s.position_context.kind==='assigned_history'&&/需你确认/.test(s.position_context.label)&&s.position_context.held_shares===null,'7 assigned history');
// 8 protected core ETF: technical signal can't produce entry or sell
s=PI.explicitSignal({symbol:'QQQM',stage:'趋势恶化',score:-90},auth);
ok(s.action==='WATCH'&&/正式策略/.test(s.reason),'8 protected core ETF');
// 9 data trust blocked → NO_SIGNAL regardless of exposure
s=PI.explicitSignal({symbol:'IREN',stage:'趋势启动',score:20},{decision_eligible:false});
ok(s.action==='NO_SIGNAL','9 data block');
// 10 draft thesis never unlocks entry for non-held
s=PI.explicitSignal({symbol:'MSFT',stage:'趋势启动',score:40,hasThesis:false,autoCovered:true,readiness:{have:['官方披露 8-K'],missing:['失效条件']}},auth);
ok(s.action==='WATCH'&&/仍缺少：失效条件/.test(s.reason),'10 draft ≠ verified');
// 11 six symbols → six distinct stock action texts
W=load(optApi([{id:2,symbol:'NBIS',side:'short',opt_type:'call',strike:120,expiry:'2026-10-16'}]));PI=W.MAVProductIntelligence;
const texts=['AMD','ORCL','DRAM','MSFT','IREN','NBIS'].map((sym,i)=>PI.stockActionText(PI.explicitSignal({symbol:sym,stage:['趋势启动','修复中','趋势延续','二次启动','趋势启动','趋势延续'][i],score:10*i},auth)));
ok(new Set(texts).size===6,'11 distinct texts');
// 12 public watchlist labels are research states, not position instructions
const agent=fs.readFileSync(__dirname+'/../docs/assets/autonomous-agent.js','utf8');
ok(/研究复查（非持仓建议）/.test(agent)&&/item.kind==='option'\?levelLabel\(item.level\):watchLevelLabel/.test(agent),'12 public watch labels');
console.log(`PASS held vs watch (${n} cases)`);
