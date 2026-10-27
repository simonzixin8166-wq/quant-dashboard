// Decision journal: maturity only counts COMPLETED NYSE sessions (Alpaca 1Day history includes today's forming bar
// while the market is open), early closes respected; header shows real counts instead of the word "部分".
// Fixed clocks only; synthetic bars are FIXTURES.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const store={};const ls={getItem:k=>store[k]??null,setItem:(k,v)=>{store[k]=String(v)},removeItem:k=>{delete store[k]}};
const win={addEventListener(){},dispatchEvent(){},localStorage:ls};
const ctx={window:win,localStorage:ls,document:{readyState:'loading',addEventListener(){},getElementById(){return null}},setTimeout(){},fetch:async()=>({ok:false}),console,Intl};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(__dirname+'/../docs/assets/trading-calendar.js','utf8'),ctx);
vm.runInContext(fs.readFileSync(__dirname+'/../docs/assets/decision-journal.js','utf8'),ctx);
const T=win.MAVDecisionJournal._test;
const bars=(last)=>{const out=[];const d=new Date('2026-09-01T12:00:00Z');while(true){const s=d.toISOString().slice(0,10);if(d.getUTCDay()%6)out.push({d:s,c:100+out.length});if(s===last)break;d.setUTCDate(d.getUTCDate()+1)}return out};
const at=s=>new Date(s);
// 10/26 10:50 EDT: the 10/26 bar is still forming -> dropped; 16:01 EDT -> kept
const b=bars('2026-10-26');
assert.strictEqual(T.completedBars(b,at('2026-10-26T14:50:00Z')).slice(-1)[0].d,'2026-10-23');
assert.strictEqual(T.completedBars(b,at('2026-10-26T20:01:00Z')).slice(-1)[0].d,'2026-10-26');
// history already ending yesterday is untouched
assert.strictEqual(T.completedBars(bars('2026-10-23'),at('2026-10-26T14:50:00Z')).slice(-1)[0].d,'2026-10-23');
// early close 2026-11-27 (13:00 ET, EST): 12:30 dropped, 13:05 kept
const bf=bars('2026-11-27');
assert.strictEqual(T.completedBars(bf,at('2026-11-27T17:30:00Z')).slice(-1)[0].d,'2026-11-26');
assert.strictEqual(T.completedBars(bf,at('2026-11-27T18:05:00Z')).slice(-1)[0].d,'2026-11-27');
// 已计至 and maturity close use completed sessions only: 10/22 entry is 1 session in, not 2, during 10/26 trading
const live=T.completedBars(b,at('2026-10-26T14:50:00Z'));
assert.deepStrictEqual(JSON.parse(JSON.stringify(T.tradingProgress(live,'2026-10-22'))),{elapsed:1,lastMarketDate:'2026-10-23'});
const e929=T.outcomeFor(T.completedBars(bars('2026-10-27'),at('2026-10-27T15:00:00Z')),'2026-09-29',100);
assert(!e929[20],'9/29 + 20 sessions = 10/27: no 20-day result from an intraday bar');
const e929c=T.outcomeFor(T.completedBars(bars('2026-10-27'),at('2026-10-27T20:30:00Z')),'2026-09-29',100);
assert.strictEqual(e929c[20].date,'2026-10-27');
// header counts: ready = matured horizon without a stored result
const rows=[{date:'2026-09-29',candidates:[{symbol:'A',price:1,maturityProgress:{elapsed:20},outcomes:{}},
  {symbol:'B',price:1,maturityProgress:{elapsed:20},outcomes:{20:{return:.1}}},{symbol:'C',price:1,maturityProgress:{elapsed:3}},{symbol:'D'}]}];
assert.strictEqual(T.readyCount(rows),1);
const src=fs.readFileSync(__dirname+'/../docs/assets/decision-journal.js','utf8');
assert(!src.includes("'部分'")&&src.includes('可补齐 ${readyCount(rows)} 条 · 等待成熟 ${pending} 条'));
assert(src.includes('const bars=completedBars(history[c.symbol]?.bars)'));
console.log('PASS journal maturity: completed sessions only (early close aware), real header counts');
