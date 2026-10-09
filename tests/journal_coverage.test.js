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
assert(/查看全部/.test(src)&&/尚未同步到服务器/.test(src));
console.log('PASS journal coverage');
