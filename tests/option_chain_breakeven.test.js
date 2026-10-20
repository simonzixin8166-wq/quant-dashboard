// Option card roll-chain line: break-even must include earlier legs' buy-back cost (ledger premium_chain_per_share).
const fs=require('fs'),vm=require('vm'),assert=require('assert');
vm.runInThisContext(fs.readFileSync('docs/assets/options-v2.js','utf8'));
const {chainSummary}=globalThis.OptionV2;
// sold 41P for 2.90, bought back 12.90, sold 40P for 13.70 -> chain 3.70, break-even 36.30 (card's single-leg view: 26.30)
const rolledPut={rolled_from_id:7,premium_chain_per_share:3.7,strike:40,opt_type:'Put',cost:13.7};
const p=chainSummary(rolledPut);
assert(p&&Math.abs(p.chain-3.7)<1e-9&&Math.abs(p.price-36.3)<1e-9&&p.label==='链平衡','rolled put: strike - chain premium');
const c=chainSummary({rolled_from_id:3,premium_chain_per_share:'2.5',strike:45,opt_type:'Call'});
assert(c&&Math.abs(c.price-47.5)<1e-9&&c.label==='链有效卖出价','rolled call: strike + chain premium');
// never invent a chain: unrolled, missing or non-numeric ledger values show nothing (null must not become 0)
assert.strictEqual(chainSummary({premium_chain_per_share:3.7,strike:40,opt_type:'Put'}),null,'not rolled -> no chain line');
assert.strictEqual(chainSummary({rolled_from_id:7,premium_chain_per_share:null,strike:40,opt_type:'Put'}),null,'null chain stays unavailable');
assert.strictEqual(chainSummary({rolled_from_id:7,premium_chain_per_share:'',strike:40,opt_type:'Put'}),null,'empty chain stays unavailable');
assert.strictEqual(chainSummary({rolled_from_id:7,premium_chain_per_share:'x',strike:40,opt_type:'Put'}),null,'non-numeric chain stays unavailable');
// negative chain (rolls cost more than collected) is real and must be shown, not hidden
const neg=chainSummary({rolled_from_id:7,premium_chain_per_share:-1.2,strike:40,opt_type:'Put'});
assert(neg&&Math.abs(neg.price-41.2)<1e-9,'negative chain raises the put break-even');
// the card markup carries the line next to the single-leg break-even
const src=fs.readFileSync('docs/assets/options-v2.js','utf8');
assert(src.includes('</span>${chainLine(x)}</div><div><small>风险状态</small>'),'chain line must render in the 资金 / 有效价 cell');
console.log('PASS option chain break-even: uses ledger chain premium; unrolled/missing stays empty');
