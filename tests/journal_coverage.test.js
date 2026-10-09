// Forward journal: coverage header so a 40-row table is never read as missing history.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const store={};const ls={getItem:k=>store[k]??null,setItem:(k,v)=>{store[k]=String(v)},removeItem:k=>{delete store[k]}};
const win={addEventListener(){},dispatchEvent(){},localStorage:ls};
const ctx={window:win,localStorage:ls,document:{readyState:'loading',addEventListener(){},getElementById(){return null}},setTimeout(){},fetch:async()=>({ok:false}),console};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(__dirname+'/../docs/assets/decision-journal.js','utf8'),ctx);
const J=win.MAVDecisionJournal;
const rows=[];for(let d=28;d<=40;d++){const day=d<=30?`2026-09-${d}`:`2026-10-${String(d-30).padStart(2,'0')}`;rows.push({date:day,candidates:[{symbol:'A'},{symbol:'B'},{symbol:'C'},{symbol:'D'}]})}
const cov=J.journalCoverage(rows);
assert.strictEqual(cov.earliest,'2026-09-28');assert.strictEqual(cov.latest,'2026-10-10');
assert.strictEqual(cov.candidates,52);assert.strictEqual(cov.visible,40);assert.strictEqual(cov.storage,'browser_local_only');
assert.deepStrictEqual(J.journalCoverage([]).candidates,0);
const src=fs.readFileSync(__dirname+'/../docs/assets/decision-journal.js','utf8');
assert(/查看全部/.test(src)&&/服务器副本/.test(src)&&/后补不计入真实前瞻/.test(src));
// server sync rows: one per candidate, no outcomes / latestPrice / transitions leak into the immutable payload
const sample=[{date:'2026-09-28',at:'2026-09-28T20:10:00Z',level:'normal',vix:16.2,candidates:[{symbol:'lite',decision:'WATCH',price:1000,firstSeenAt:'2026-09-28T20:10:00Z',outcomes:{20:{return:.1}},latestPrice:1085,transitions:[{at:'x'}]},{symbol:'bad sym!',decision:'WATCH'}]}];
const er=J.journalEntryRows(sample);
assert.strictEqual(er.length,1);assert.strictEqual(er[0].symbol,'LITE');assert.strictEqual(er[0].journal_date,'2026-09-28');
assert.strictEqual(er[0].original_first_seen_at,'2026-09-28T20:10:00Z');
assert(!('outcomes' in er[0].payload)&&!('latestPrice' in er[0].payload)&&!('transitions' in er[0].payload));
assert(!('capture_mode' in er[0])&&!('forward_attested' in er[0])&&!('server_received_at' in er[0]),'client never sets provenance');
console.log('PASS journal coverage');
