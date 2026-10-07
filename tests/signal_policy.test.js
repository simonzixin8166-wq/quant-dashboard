const fs=require('fs'),vm=require('vm'),assert=require('assert');

const sandbox={window:{},console};
sandbox.window.window=sandbox.window;
sandbox.document={readyState:'loading',addEventListener:()=>{},getElementById:()=>null,querySelectorAll:()=>[]};
sandbox.window.document=sandbox.document;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync('docs/assets/signal-policy.js','utf8'),sandbox);
const policy=sandbox.window.MAVSignalPolicy;
const classify=(x)=>policy.classify({decisionEligible:true,...x});

assert.equal(classify({symbol:'IREN',hasThesis:true,stage:'趋势退潮',score:-10}).action,'WATCH');
assert.equal(classify({symbol:'AMD',hasThesis:false,stage:'趋势启动',score:20}).action,'WATCH');
assert.equal(classify({symbol:'AMD',hasThesis:false,stage:'二次启动',score:35}).action,'WATCH');
assert.equal(classify({symbol:'AMD',hasThesis:false,stage:'趋势延续',score:60}).action,'WATCH');
assert.equal(classify({symbol:'VGT',hasThesis:true,stage:'趋势启动',score:20}).action,'WATCH');
assert.equal(classify({symbol:'TQQQ',hasThesis:true,stage:'二次启动',score:45}).action,'WATCH');
assert.equal(classify({symbol:'IREN',hasThesis:true,held:true,stage:'趋势恶化',score:-20}).action,'NO_ADD');
assert.equal(classify({symbol:'IREN',hasThesis:true,held:true,invalidated:true,stage:'趋势恶化',score:-80}).action,'EXIT');
assert.equal(policy.classify({symbol:'IREN',hasThesis:true,stage:'趋势启动',score:80,decisionEligible:false}).action,'NO_SIGNAL');

sandbox.window.MAVSignalPolicy=policy;
vm.runInContext(fs.readFileSync('docs/assets/product-intelligence.js','utf8'),sandbox);
const formal=sandbox.window.MAVProductIntelligence.formalStrategyActions;
const rows=formal({
  core:{VGT:{level:0,strategy_drawdown:-0.05},QQQM:{level:1,strategy_drawdown:-0.13}},
  tqqq_x2:{available:true,changed:true,status_label:'X2状态变化',action:'一级降险',snapshot:{hard_exit:false}},
  leaps_radar:{assets:[{symbol:'QQQ',status:'normal',status_label:'未触发'}]}
});
assert(rows.some(x=>x.title==='VGT · HOLD'));
assert(rows.some(x=>x.title==='QQQM · CORE TIER 1'));
assert(rows.some(x=>x.title==='TQQQ X2 · ACTION'));
assert(rows.some(x=>x.title==='QQQ LEAPS · HOLD'));
console.log('PASS signal-policy scenarios and formal strategy adapter');
