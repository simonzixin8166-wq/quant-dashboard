// Small DOM harness: checks content rendering without a browser or network.
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const path=require('node:path');
const base=path.join(__dirname,'../docs/assets');
const nodes=new Map();function node(key){if(!nodes.has(key))nodes.set(key,{innerHTML:'',disabled:false,querySelector:s=>node(s),querySelectorAll:()=>[]});return nodes.get(key)}
const context={window:{},document:{getElementById:()=>node('root')},URL,Map,Date,Number,String,JSON};
vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(base,'wenxuecity-curated.js'),'utf8'),context);
let source=fs.readFileSync(path.join(base,'wenxuecity.js'),'utf8');
assert(source.includes('render();load();'));
source=source.replace('render();load();','globalThis.renderTab=(value)=>{tab=value;render()};render();');
vm.runInContext(source,context);
assert(node('#wxcContent').innerHTML.includes('11篇博客'));
assert(node('#wxcContent').innerHTML.includes('2篇论坛主贴'));
context.renderTab('blogs');assert.equal((node('#wxcResults').innerHTML.match(/<article>/g)||[]).length,11);
assert(node('#wxcResults').innerHTML.includes('Gemini生成'));
assert(node('#wxcResults').innerHTML.includes('加仓价格档位'));
context.renderTab('forum');assert.equal((node('#wxcContent').innerHTML.match(/<article>/g)||[]).length,2);
assert(node('#wxcContent').innerHTML.includes('不冒充今日收盘日报'));
context.renderTab('methods');assert.equal((node('#wxcResults').innerHTML.match(/<article>/g)||[]).length,13);
context.renderTab('status');assert(!node('#wxcContent').innerHTML.includes('三篇'));
console.log('PASS: embedded content renders overview, 11 blogs, 2 forum posts, 13 method cards without API/network');
