(function(global){
'use strict';
const KEY='mavDecisionJournalV53', OLD_KEYS=['mavDecisionJournalV52','mavDecisionJournalV51'];
const endpoint='https://rhielbkvhgqbthcgztci.supabase.co/functions/v1/stock-market';
const H=[20,60,120];
const state={history:null,historyLoaded:false,lastAuthError:'',refreshing:false};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=v=>Number.isFinite(Number(v))?Number(v):null;
const pct=v=>num(v)===null?'—':`${Number(v)>=0?'+':''}${(Number(v)*100).toFixed(1)}%`;
const dateOnly=s=>String(s||'').slice(0,10);
function read(){
  try{
    let rows=JSON.parse(localStorage.getItem(KEY)||'null');
    if(!Array.isArray(rows)){
      rows=[];
      for(const k of OLD_KEYS){const old=JSON.parse(localStorage.getItem(k)||'[]');if(Array.isArray(old)&&old.length){rows=old.map(x=>({...x,version:x.version||'migrated'}));break}}
      localStorage.setItem(KEY,JSON.stringify(rows));
    }
    return rows;
  }catch{return []}
}
function write(rows){try{localStorage.setItem(KEY,JSON.stringify(rows.slice(-300)))}catch{}}
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
  rows.push({key,at:new Date().toISOString(),date:day,level:classification.level,mode:classification.mode,title:classification.title||'常态监测',spx:num(snapshot.spx),ixic:num(snapshot.ixic),vix:num(snapshot.vix),candidates:items,optionIdeas:(optionIdeas||[]).slice(0,8),source:'automatic-scan-v5.3',version:'5.3'});
  write(rows);render();
}
function supabase(){return global.mavSupabase||global.supabaseClient||null}
async function waitForAuth(timeout=10000){
  const start=Date.now();let sb=null;
  while(Date.now()-start<timeout){
    sb=supabase();if(sb?.auth?.getSession)return sb;
    await new Promise(r=>setTimeout(r,350));
  }
  throw new Error('登录组件初始化超时');
}
async function authHeaders(){
  const sb=await waitForAuth();
  const {data:{session}}=await sb.auth.getSession();
  if(!session)throw new Error('登录后才能补齐实时日志的个股结果');
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
function pendingCount(rows){let n=0;for(const e of rows)for(const c of(e.candidates||[]))if(num(c.price)!==null&&(!c.outcomes||!c.outcomes[120]))n++;return n}
async function refreshOutcomes({silent=false}={}){
  if(state.refreshing)return;state.refreshing=true;
  const rows=read(),pending=[];
  for(const e of rows)for(const c of(e.candidates||[]))if(num(c.price)!==null&&(!c.outcomes||!c.outcomes[120]))pending.push(c.symbol);
  const symbols=[...new Set(pending)];
  if(!symbols.length){state.refreshing=false;if(!silent)global.MAV?.toast?.('当前没有等待补齐的实时结果','good');render();return}
  try{
    const history=await fetchHistory(symbols);state.lastAuthError='';
    for(const e of rows)for(const c of(e.candidates||[])){const bars=history[c.symbol]?.bars;if(!bars)continue;c.outcomes={...(c.outcomes||{}),...outcomeFor(bars,e.date,c.price)};c.lastValidatedAt=new Date().toISOString();}
    write(rows);if(!silent)global.MAV?.toast?.('实时 Journal 已补齐当前已成熟的结果','good');
  }catch(err){state.lastAuthError=String(err.message||err);if(!silent)global.MAV?.toast?.(`实时结果补齐暂不可用：${state.lastAuthError}`,'warn')}
  finally{state.refreshing=false;render()}
}
function matureStats(rows,h=20){
  const vals=[];for(const e of rows)for(const c of(e.candidates||[])){const r=c.outcomes?.[h]?.return;if(num(r)!==null)vals.push(num(r));}
  if(!vals.length)return {n:0,avg:null,positive:null};return {n:vals.length,avg:vals.reduce((a,b)=>a+b,0)/vals.length,positive:vals.filter(x=>x>0).length/vals.length};
}
function marketLabel(e){return e.level==='panic'?'极端':e.level==='fear'?'大跌':e.level==='watch'?'观察':e.mode==='greed'?'强势高位':'正常'}
function candidateRows(rows){const out=[];for(const e of[...rows].reverse())for(const c of(e.candidates||[]))out.push({e,c});return out.slice(0,40)}
async function loadJson(url){try{const r=await fetch(`${url}?v=${Date.now()}`,{cache:'no-store'});if(!r.ok)return null;return await r.json()}catch{return null}}
async function ensureHistory(){if(state.historyLoaded)return state.history;state.historyLoaded=true;state.history=await loadJson('research/historical_journal.json');setTimeout(()=>global.MAVInvestmentAssistant?.rescan?.(),0);return state.history}
function maturityHint(date,h){
  const d=Date.parse(date);if(!Number.isFinite(d))return `等待第${h}个交易日`;
  const rough=Math.max(0,h-Math.floor((Date.now()-d)/86400000*5/7));
  return rough>0?`约还需${rough}个交易日`:`等待收盘数据补齐`;
}
function outcomeCell(c,e,h){const r=c.outcomes?.[h];if(r)return `<span class="${num(r.return)>0?'pos-text':num(r.return)<0?'neg-text':''}">${pct(r.return)}</span><small>${esc(r.date||'')}</small>`;return `<span class="journal-pending">未成熟</span><small>${esc(maturityHint(e.date,h))}</small>`}
function validationHtml(data){
  if(!data)return `<div class="journal-empty"><b>历史市场规则验证等待生成</b><p>Daily Dashboard Update 会尝试运行市场提醒规则事件研究。期权 Delta/DTE 的真实历史收益不会用正股走势替代。</p></div>`;
  const groups=data.groups||[];
  return `<div class="journal-validation-grid">${groups.map(g=>`<article><div><b>${esc(g.label)}</b><span>${g.events}次事件</span></div><p>QQQ 20日平均 ${pct(g.forward?.['20']?.avg)} · 正收益 ${g.forward?.['20']?.positive_rate==null?'—':(g.forward['20'].positive_rate*100).toFixed(0)+'%'}</p><small>60日 ${pct(g.forward?.['60']?.avg)} · 20日最大不利波动均值 ${pct(g.mae20_avg)}</small></article>`).join('')}</div><p class="journal-method-note">这一块验证“市场级触发”；下面的本地历史学习则验证观察股 Trend Pulse / 动态阶段。二者分开，避免混淆。</p>`;
}
function stageProfileHtml(history){
  if(!history)return `<div class="journal-empty"><b>本地历史学习等待生成</b><p>把 STOOQ 历史包放入仓库后，Daily Dashboard Update 会自动生成 5 年状态样本并每天续写。</p></div>`;
  const profiles=history.profiles||{};const order=['二次启动','趋势启动','趋势延续','修复中','高位钝化','趋势退潮','趋势恶化'];
  return `<div class="learning-summary"><article><span>历史标的</span><b>${history.summary?.symbols??'—'}</b><small>本地 STOOQ 库</small></article><article><span>状态事件</span><b>${history.summary?.events??'—'}</b><small>5年因果回放</small></article><article><span>60日成熟</span><b>${history.summary?.mature_60??'—'}</b><small>可立即学习</small></article><article><span>120日成熟</span><b>${history.summary?.mature_120??'—'}</b><small>长期验证</small></article></div><div class="learning-grid">${order.map(stage=>{const p=profiles[stage]||{},s=p.horizons?.['60']||{},ev=p.evidence||{};return `<article class="learning-card ${esc(ev.level||'insufficient')}"><div><b>${esc(stage)}</b><span>${esc(ev.label||'样本不足')}</span></div><strong>${s.n||0} 个60日成熟样本</strong><p>平均 ${pct(s.avg)} · 中位 ${pct(s.median)} · 正收益 ${s.positive_rate==null?'—':(s.positive_rate*100).toFixed(0)+'%'}</p><small>平均MAE ${pct(s.mae_avg)} · MFE ${pct(s.mfe_avg)} · 相对QQQ ${pct(s.excess_vs_qqq_avg)} · 仅用于研究优先级</small></article>`}).join('')}</div>`;
}
function recentHistoryHtml(history){const rows=(history?.recent_events||[]).slice(0,18);if(!rows.length)return '';return `<details class="journal-history-details"><summary>查看最近历史状态样本</summary><div class="journal-table-wrap"><table class="journal-table"><thead><tr><th>日期</th><th>标的</th><th>状态</th><th>Pulse</th><th>20日</th><th>60日</th><th>120日</th></tr></thead><tbody>${rows.map(e=>`<tr><td>${esc(e.date)}</td><td><b>${esc(e.symbol)}</b><small>$${Number(e.price).toFixed(2)}</small></td><td>${esc(e.stage)}<small>${esc(e.zone||'')}</small></td><td>${Number(e.score)>0?'+':''}${Number(e.score).toFixed(0)}</td>${H.map(h=>`<td>${pct(e.outcomes?.[h]?.return)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></details>`}
let backtestCache=null;
async function render(error=''){
  const root=document.getElementById('decisionJournalRoot');if(!root)return;
  const rows=read(),candidateCount=rows.reduce((n,e)=>n+(e.candidates||[]).length,0),s20=matureStats(rows,20),s60=matureStats(rows,60),recent=candidateRows(rows),pending=pendingCount(rows);
  if(backtestCache===null)backtestCache=await loadJson('research/assistant_rule_validation.json');
  const history=await ensureHistory();
  root.innerHTML=`<section class="hero compact-hero"><div><h1>Decision Journal · 决策复盘</h1><p>两条证据链：历史回填立即学习 + 从今天起实时留痕。系统负责记录、验证和排序；投资者负责最终操作。</p></div><div class="journal-actions"><button type="button" onclick="MAVDecisionJournal.refreshOutcomes()">↻ 补齐实时成熟结果</button></div></section>
  <section class="journal-summary"><article><span>实时扫描快照</span><b>${rows.length}</b><small>${candidateCount} 条候选记录</small></article><article><span>等待成熟</span><b>${pending}</b><small>每条从入档日独立计算</small></article><article><span>实时20日成熟</span><b>${s20.n}</b><small>平均 ${pct(s20.avg)}</small></article><article><span>实时60日成熟</span><b>${s60.n}</b><small>平均 ${pct(s60.avg)}</small></article></section>
  ${error||state.lastAuthError?`<div class="journal-warning">${esc(error||state.lastAuthError)}。历史学习不依赖登录，仍可正常使用。</div>`:''}
  <section class="journal-panel"><div class="journal-head"><div><h2>自主学习 · 历史回填</h2><p>使用你提供的 STOOQ OHLCV，本地因果重放 Trend Pulse；不重复下载多年历史，也不使用未来数据。</p></div></div>${stageProfileHtml(history)}${recentHistoryHtml(history)}</section>
  <section class="journal-panel"><div class="journal-head"><div><h2>实时决策日志</h2><p>保存系统当时真实看到的环境和候选，防止事后改写。20 / 60 / 120均按各自入档交易日起算。</p></div><small>当前可补齐 ${pending===0?0:'部分'} 条</small></div>${recent.length?`<div class="journal-table-wrap"><table class="journal-table"><thead><tr><th>日期</th><th>环境</th><th>标的 / 当时判断</th><th>入档价格</th><th>20日</th><th>60日</th><th>120日</th></tr></thead><tbody>${recent.map(({e,c})=>`<tr><td>${esc(e.date)}</td><td>${esc(marketLabel(e))}<small>VIX ${e.vix==null?'—':Number(e.vix).toFixed(1)}</small></td><td><b>${esc(c.symbol)}</b><small>${esc(c.decision)} · ${esc(c.stage||c.zone||'')}</small></td><td>${c.price==null?'—':'$'+Number(c.price).toFixed(2)}</td>${H.map(h=>`<td>${outcomeCell(c,e,h)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:`<div class="journal-empty"><b>还没有实时记录</b><p>市场状态或候选发生有意义变化后会自动留下快照，不需要手工记录。</p></div>`}</section>
  <section class="journal-panel"><div class="journal-head"><div><h2>历史市场规则验证</h2><p>单独检查观察 / 大跌 / 极端市场触发，不与个股 Trend Pulse 样本混在一起。</p></div></div>${validationHtml(backtestCache)}</section>
  <section class="journal-panel journal-boundary"><h2>AI Agent 学习边界</h2><div><b>自动完成</b><p>历史回填、每日增量、结果成熟、样本统计、研究优先级、异常提醒和 QA。</p></div><div><b>必须由投资者决定</b><p>买卖、仓位、核心ETF阈值变更、把博主经验升级成正式规则。AI不会自动下单。</p></div></section>`;
}
function learningForStage(stage){const p=state.history?.profiles?.[stage];if(!p)return null;return {...p.evidence,stats:p.horizons?.['60']||null}}
async function init(){render();setTimeout(()=>refreshOutcomes({silent:true}),4500)}
global.MAVDecisionJournal={recordAssistantEvent,refreshOutcomes,render,getJournal:read,getHistorical:()=>state.history,learningForStage,state};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})(window);
