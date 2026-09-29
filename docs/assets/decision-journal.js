(function(global){
'use strict';
const KEY='mavDecisionJournalV52', OLD='mavDecisionJournalV51';
const endpoint='https://rhielbkvhgqbthcgztci.supabase.co/functions/v1/stock-market';
const H=[20,60,120];
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=v=>Number.isFinite(Number(v))?Number(v):null;
const pct=v=>num(v)===null?'—':`${Number(v)>=0?'+':''}${(Number(v)*100).toFixed(1)}%`;
const dateOnly=s=>String(s||'').slice(0,10);
function read(){
  try{
    let rows=JSON.parse(localStorage.getItem(KEY)||'null');
    if(!Array.isArray(rows)){
      const old=JSON.parse(localStorage.getItem(OLD)||'[]');
      rows=Array.isArray(old)?old.map(x=>({...x,version:'5.1-migrated'})):[];
      localStorage.setItem(KEY,JSON.stringify(rows));
    }
    return rows;
  }catch{return []}
}
function write(rows){try{localStorage.setItem(KEY,JSON.stringify(rows.slice(-240)))}catch{}}
function candidateDecision(c,classification){
  const stage=String(c.stage||'');
  if(/退潮|恶化/.test(stage))return '等待修复';
  if(/二次启动|启动|重新|修复中/.test(stage))return '修复候选';
  if(classification.mode==='fear')return '大跌机会候选';
  if(/钝化|高位/.test(stage))return '高位观察';
  return '继续观察';
}
function recordAssistantEvent({snapshot,classification,candidates=[],optionIdeas=[]}){
  const day=new Date().toISOString().slice(0,10);
  const signature=(candidates||[]).slice(0,6).map(x=>`${x.symbol}:${x.stage||''}`).join(',');
  const key=`${day}|${classification.level}|${signature}`;
  const rows=read();if(rows.some(x=>x.key===key))return;
  const items=(candidates||[]).slice(0,6).map(c=>({symbol:c.symbol,name:c.name||c.symbol,price:num(c.price),score:num(c.score),stage:c.stage||'',zone:c.zone||'',hasThesis:Boolean(c.hasThesis),decision:candidateDecision(c,classification),outcomes:{}}));
  rows.push({key,at:new Date().toISOString(),date:day,level:classification.level,mode:classification.mode,title:classification.title||'常态监测',spx:num(snapshot.spx),ixic:num(snapshot.ixic),vix:num(snapshot.vix),candidates:items,optionIdeas:(optionIdeas||[]).slice(0,8),source:'automatic-scan-v5.2',version:'5.2'});
  write(rows);render();
}
async function authHeaders(){
  if(!global.supabaseClient||!global.SUPABASE_ANON_KEY)throw new Error('登录组件尚未就绪');
  const {data:{session}}=await global.supabaseClient.auth.getSession();
  if(!session)throw new Error('登录后才能补齐个股历史验证');
  return {Authorization:`Bearer ${session.access_token}`,apikey:global.SUPABASE_ANON_KEY};
}
async function fetchHistory(symbols){
  if(!symbols.length)return {};
  const headers=await authHeaders(),out={};
  for(let i=0;i<symbols.length;i+=25){
    const chunk=symbols.slice(i,i+25);
    const r=await fetch(`${endpoint}?symbols=${encodeURIComponent(chunk.join(','))}&scope=history&t=${Date.now()}`,{headers,cache:'no-store',signal:AbortSignal.timeout(20000)});
    const b=await r.json();if(!r.ok||b.s!=='ok')throw new Error(b.error||`HTTP ${r.status}`);
    Object.assign(out,b.rows||{});
  }
  return out;
}
function outcomeFor(bars,eventDate,entryPrice){
  if(!Array.isArray(bars)||!bars.length||num(entryPrice)===null)return {};
  const start=bars.findIndex(x=>String(x.d)>=eventDate);if(start<0)return {};
  const res={};
  for(const h of H){const row=bars[start+h];if(row&&num(row.c)!==null)res[h]={date:row.d,price:num(row.c),return:num(row.c)/Number(entryPrice)-1};}
  const first20=bars.slice(start+1,start+21).map(x=>num(x.c)).filter(x=>x!==null);
  if(first20.length)res.mae20=Math.min(...first20)/Number(entryPrice)-1;
  return res;
}
async function refreshOutcomes({silent=false}={}){
  const rows=read();const pending=[];
  for(const e of rows)for(const c of (e.candidates||[]))if(num(c.price)!==null&&(!c.outcomes||!c.outcomes[120]))pending.push(c.symbol);
  const symbols=[...new Set(pending)];if(!symbols.length){if(!silent)global.MAV?.toast?.('当前没有等待补齐的个股结果','good');render();return}
  try{
    const history=await fetchHistory(symbols);
    for(const e of rows){for(const c of (e.candidates||[])){const bars=history[c.symbol]?.bars;if(!bars)continue;c.outcomes={...(c.outcomes||{}),...outcomeFor(bars,e.date,c.price)};c.lastValidatedAt=new Date().toISOString();}}
    write(rows);render();if(!silent)global.MAV?.toast?.('Decision Journal 已补齐可成熟的20/60/120日结果','good');
  }catch(err){if(!silent)global.MAV?.toast?.(`历史验证暂不可用：${err.message}`,'warn');render(String(err.message||err))}
}
function matureStats(rows,h=20){
  const vals=[];for(const e of rows)for(const c of (e.candidates||[])){const r=c.outcomes?.[h]?.return;if(num(r)!==null)vals.push(num(r));}
  if(!vals.length)return {n:0,avg:null,positive:null};return {n:vals.length,avg:vals.reduce((a,b)=>a+b,0)/vals.length,positive:vals.filter(x=>x>0).length/vals.length};
}
function marketLabel(e){return e.level==='panic'?'极端':e.level==='fear'?'大跌':e.level==='watch'?'观察':e.mode==='greed'?'强势高位':'正常'}
function candidateRows(rows){
  const out=[];for(const e of [...rows].reverse())for(const c of (e.candidates||[]))out.push({e,c});return out.slice(0,30);
}
async function loadBacktest(){
  try{const r=await fetch(`research/assistant_rule_validation.json?v=${Date.now()}`,{cache:'no-store'});if(!r.ok)return null;return await r.json()}catch{return null}
}
function validationHtml(data){
  if(!data)return `<div class="journal-empty"><b>历史规则验证等待生成</b><p>Daily Dashboard Update 会尝试运行市场提醒规则的5年事件研究。期权 Delta/DTE 的真实历史收益不在此伪造，需可靠历史期权链或未来 Journal 样本。</p></div>`;
  const groups=data.groups||[];
  return `<div class="journal-validation-grid">${groups.map(g=>`<article><div><b>${esc(g.label)}</b><span>${g.events}次事件</span></div><p>QQQ 20日平均 ${pct(g.forward?.['20']?.avg)} · 正收益 ${g.forward?.['20']?.positive_rate==null?'—':(g.forward['20'].positive_rate*100).toFixed(0)+'%'}</p><small>60日 ${pct(g.forward?.['60']?.avg)} · 20日最大不利波动均值 ${pct(g.mae20_avg)}</small></article>`).join('')}</div><p class="journal-method-note">历史验证对象是“市场触发后的标的表现”，不是历史期权权利金回测；Sell Put / LEAPS 的参数仍标记为经验候选，不能把标的上涨直接等同于期权策略盈利。</p>`;
}
let backtestCache=null;
async function render(error=''){
  const root=document.getElementById('decisionJournalRoot');if(!root)return;
  const rows=read(),s20=matureStats(rows,20),s60=matureStats(rows,60),recent=candidateRows(rows);
  if(backtestCache===null)backtestCache=await loadBacktest();
  root.innerHTML=`<section class="hero compact-hero"><div><h1>Decision Journal · 决策复盘</h1><p>自动记录重要市场状态和研究候选；20 / 60 / 120个交易日后再看结果。AI可以学习排序，但不能自行改核心规则。</p></div><div class="journal-actions"><button type="button" onclick="MAVDecisionJournal.refreshOutcomes()">↻ 补齐成熟结果</button></div></section>
  <section class="journal-summary"><article><span>自动记录</span><b>${rows.length}</b><small>本浏览器私有</small></article><article><span>20日成熟样本</span><b>${s20.n}</b><small>平均 ${pct(s20.avg)}</small></article><article><span>20日正收益率</span><b>${s20.positive==null?'—':(s20.positive*100).toFixed(0)+'%'}</b><small>${s20.n<20?'样本仍少，不下结论':'仅作经验统计'}</small></article><article><span>60日成熟样本</span><b>${s60.n}</b><small>平均 ${pct(s60.avg)}</small></article></section>
  ${error?`<div class="journal-warning">${esc(error)}</div>`:''}
  <section class="journal-panel"><div class="journal-head"><div><h2>自动决策记录</h2><p>记录的是“当时看到了什么、为何列为候选”，不是事后改写判断。</p></div></div>${recent.length?`<div class="journal-table-wrap"><table class="journal-table"><thead><tr><th>日期</th><th>环境</th><th>标的 / 当时判断</th><th>入档价格</th><th>20日</th><th>60日</th><th>120日</th></tr></thead><tbody>${recent.map(({e,c})=>`<tr><td>${esc(e.date)}</td><td>${esc(marketLabel(e))}<small>VIX ${e.vix==null?'—':Number(e.vix).toFixed(1)}</small></td><td><b>${esc(c.symbol)}</b><small>${esc(c.decision)} · ${esc(c.stage||c.zone||'')}</small></td><td>${c.price==null?'—':'$'+Number(c.price).toFixed(2)}</td>${H.map(h=>`<td class="${num(c.outcomes?.[h]?.return)>0?'pos-text':num(c.outcomes?.[h]?.return)<0?'neg-text':''}">${pct(c.outcomes?.[h]?.return)}${c.outcomes?.[h]?.date?`<small>${esc(c.outcomes[h].date)}</small>`:''}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:`<div class="journal-empty"><b>还没有自动记录</b><p>市场状态或候选发生有意义变化后，系统会自动留下快照，不需要手工记录。</p></div>`}</section>
  <section class="journal-panel"><div class="journal-head"><div><h2>历史规则验证</h2><p>用历史市场数据检查“观察 / 大跌 / 极端”触发后发生了什么，避免只凭印象优化规则。</p></div></div>${validationHtml(backtestCache)}</section>
  <section class="journal-panel journal-boundary"><h2>自我学习边界</h2><div><b>AI 可以自动做</b><p>记录、统计、比较、候选排序、识别哪些环境表现更稳定。</p></div><div><b>AI 不能自动做</b><p>修改核心ETF回撤阈值、把博主观点直接变成交易规则、自动下单。</p></div></section>`;
}
function init(){render();setTimeout(()=>refreshOutcomes({silent:true}),2500)}
global.MAVDecisionJournal={recordAssistantEvent,refreshOutcomes,render,getJournal:read};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})(window);
