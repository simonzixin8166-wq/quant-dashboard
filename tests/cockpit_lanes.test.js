// P1-4 compact cockpit: priority lanes from real rows; urgent never hidden; research never shown as holding.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const win={addEventListener(){},dispatchEvent(){},CustomEvent:function(){}};
const ctx={window:win,document:{readyState:'loading',addEventListener(){},getElementById(){return null}},setTimeout(){},setInterval(){},clearInterval(){},fetch:async()=>({ok:false}),CustomEvent:function(){},console};
vm.createContext(ctx);
for(const f of ['signal-policy','product-intelligence'])vm.runInContext(fs.readFileSync(`${__dirname}/../docs/assets/${f}.js`,'utf8'),ctx);
const PI=win.MAVProductIntelligence;
const rows=[
 {title:'IREN 30P 2026-11-20 · 紧急处理',tone:'bad',target:'tab-options',when:'今日',text:'x'},
 {title:'NBIS 120C · 考虑展期',tone:'warn',target:'tab-options',when:'今日 / 次日',text:'y'},
 {title:'QQQM · HOLD',tone:'neutral',target:'tab-engine',when:'HOLD',text:'Tier 未触发'},
 {title:'VGT · HOLD',tone:'neutral',target:'tab-engine',when:'HOLD',text:'Tier 未触发'},
 {title:'AMD · WATCH（研究态）',tone:'neutral',target:'tab-stocks',when:'观察',text:'z'},
 {title:'SOFI · REDUCE',tone:'bad',target:'tab-stocks',when:'今日',text:'held'},
];
assert.deepStrictEqual(rows.map(PI.laneOf),['urgent','holdings','core','core','research','urgent']);
const c=PI.laneCounts(rows,{decision_eligible:true});
assert.strictEqual(c.urgent,2);assert.strictEqual(c.holdings,1);assert.strictEqual(c.core,2);assert.strictEqual(c.research,1);assert.strictEqual(c.blocked,0);
assert.strictEqual(PI.laneCounts(rows,{decision_eligible:false}).blocked,1);
const src=fs.readFileSync(__dirname+'/../docs/assets/product-intelligence.js','utf8');
assert(/key==='urgent'\?6/.test(src),'urgent lane shows up to 6 before folding');
assert(/查看全部（另/.test(src)&&/details class="pi-more"/.test(src),'folded rows stay reachable');
assert(/class="pi-link" data-pi-target/.test(src),'evidence is a small text link, not a big button');
// production QA contract (scripts/autonomous_site_qa.mjs): ≥5 summary jumps incl. tab:tab-options
assert((src.match(/chip\('(?:group|tab):/g)||[]).length>=5,'at least 5 summary jumps');
assert(/chip\('tab:tab-options'/.test(src),'options jump present');
console.log('PASS cockpit lanes');
