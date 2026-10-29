// 复盘与学习: the "实时20日/60日成熟" browser averages are replaced by the server FWD-01 scorecard (Owner-approved 10/27).
// 真实前瞻 and 历史补录 are shown separately (never pooled), no rate below n=20, missing data shows "—" not 0,
// browser journal outcomes are labelled reference-only. Scorecards below are FIXTURES except the committed file check.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const store={};const ls={getItem:k=>store[k]??null,setItem:(k,v)=>{store[k]=String(v)},removeItem:k=>{delete store[k]}};
const win={addEventListener(){},dispatchEvent(){},localStorage:ls};
const ctx={window:win,localStorage:ls,document:{readyState:'loading',addEventListener(){},getElementById(){return null}},setTimeout(){},fetch:async()=>({ok:false}),console,Intl};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(__dirname+'/../docs/assets/trading-calendar.js','utf8'),ctx);
const src=fs.readFileSync(__dirname+'/../docs/assets/decision-journal.js','utf8');
vm.runInContext(src,ctx);
const T=win.MAVDecisionJournal._test;
const cell=(o)=>({group:'promoted',h:20,decision:'等待修复',eligible:false,matured:0,unavailable:0,invalid:0,abstain:0,scored:0,hits:0,hit_rate:null,status:'INSUFFICIENT',...o});
const base={contract_id:'fsc-1.0',as_of_session:'2026-10-28',learning_state:'UNPROVEN',price_basis_zh:'价格收益：不含股息。',mae_basis_zh:'MAE 按收盘价。',
  pending:[{group:'genuine_forward',h:20,rows:386},{group:'promoted',h:20,rows:94},{group:'promoted',h:60,rows:130}]};

// 1) today's shape: promoted only, all INSUFFICIENT -> counts, no rate anywhere
const sc1={...base,cells:[cell({matured:15,scored:15,hits:6,hit_rate:null}),cell({decision:'继续观察',eligible:true,matured:4,abstain:4}),
  cell({decision:'高位观察',eligible:true,matured:17,scored:17,hits:14})]};
const g=T.scorecardGroup(sc1,'promoted',20);
assert.strictEqual(g.scored,32);assert.strictEqual(g.matured,36);assert.strictEqual(g.abstain,4);assert.strictEqual(g.pending,94);assert.strictEqual(g.reportable,0);
const gf=T.scorecardGroup(sc1,'genuine_forward',20);
assert.strictEqual(gf.scored,0);assert.strictEqual(gf.pending,386);
const cards=T.scorecardCards(sc1);
assert(cards.includes('真实前瞻 · 20日已打分</span><b>0</b>'),'genuine card shows its own count');
assert(cards.includes('历史补录 · 20日已打分</span><b>32</b>'),'promoted card shows its own count (not pooled with genuine)');
assert(cards.includes('待成熟 386')&&cards.includes('待成熟 94'));
assert(cards.includes('样本不足')&&!/\d%/.test(cards),'no rate below n=20');
assert(cards.includes('不计作真实前瞻'));
const note=T.scorecardNote(sc1);
assert(note.includes('截至 2026-10-28 收盘')&&note.includes('未证明（UNPROVEN）')&&note.includes('从不合并'));
assert(note.includes('价格收益：不含股息。')&&note.includes('MAE 按收盘价。'),'zh basis notes shown (#298)');
assert(note.includes('仅为参考值'),'browser outcomes labelled reference-only');
assert(!/\d+%/.test(note),'detail table shows no rate while INSUFFICIENT');
// 2) a scorecard that wrongly carries a rate on an INSUFFICIENT or n<20 cell still shows no rate (defensive)
const leak={...base,cells:[cell({scored:12,hits:9,hit_rate:.75}),cell({decision:'X',scored:25,hits:20,hit_rate:.8,status:'INSUFFICIENT'})]};
assert(!/\d+%/.test(T.scorecardNote(leak))&&T.scorecardGroup(leak,'promoted').reportable===0);
// 3) a reportable cell (n>=20, status set, rate present) shows its own rate only in the detail table; the card shows the group count
const ok={...base,cells:[cell({group:'genuine_forward',decision:'高位观察',eligible:true,matured:24,scored:22,hits:13,hit_rate:13/22,status:'REPORTED'})]};
assert(T.scorecardNote(ok).includes('59%'));
assert(T.scorecardCards(ok).includes('1 组达到报告门槛')&&!/\d+%/.test(T.scorecardCards(ok)),'cards never show a pooled rate');
// 4) missing / unreadable scorecard -> "—", never 0, explicit failure text
for(const bad of [null,{},{cells:'x'}]){const c=T.scorecardCards(bad);assert(c.includes('<b>—</b>')&&c.includes('读取失败')&&!c.includes('<b>0</b>'));assert(T.scorecardNote(bad).includes('无法读取'))}
// 5) escaping
const evil={...base,as_of_session:'<img src=x>',cells:[cell({decision:'<script>x</script>'})]};
assert(!T.scorecardNote(evil).includes('<script>')&&!T.scorecardNote(evil).includes('<img'));
// 6) wiring: old browser-average cards are gone, the server file is loaded, no new section was added
assert(!src.includes('实时20日成熟')&&!src.includes('实时60日成熟'));
assert(src.includes("loadJson('research/forward_scorecard.json')"));
assert.strictEqual((src.match(/<section class="journal-panel/g)||[]).length,7,'still 7 panels: no new section');
assert(src.includes('正式打分以页首服务器记分卡为准'));
// 7) the committed production scorecard renders
const real=JSON.parse(fs.readFileSync(__dirname+'/../docs/research/forward_scorecard.json','utf8'));
const rc=T.scorecardCards(real);assert(rc.includes('真实前瞻')&&rc.includes('历史补录')&&!rc.includes('读取失败'));
assert(T.scorecardNote(real).includes(real.as_of_session));
console.log('PASS journal scorecard: server fsc-1.0 cards, genuine/promoted separate, no rate below n=20, reference-only browser outcomes');
