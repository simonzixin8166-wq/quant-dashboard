(function(global){
'use strict';
const playbook=()=>global.MYALPHA_STRATEGY_PLAYBOOK||{strategies:[]};
const registry=()=>global.MYALPHA_RULE_REGISTRY||{rules:[]};
const state={last:null,lastSnapshot:null,lastAlertKey:null,lastAlertAt:0,optionIdeas:[],optionScanAt:0,scanning:false,lastScanAt:0};
const n=v=>Number.isFinite(Number(v))?Number(v):null;
const pct=v=>v===null?'—':`${v>=0?'+':''}${(v*100).toFixed(2)}%`;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function classify(spx,ixic,vix){
  spx=n(spx);ixic=n(ixic);vix=n(vix);
  if((ixic!==null&&ixic<=-.04)||(spx!==null&&spx<=-.035)||(vix!==null&&vix>=35)) return {mode:'fear',level:'panic',title:'极端回撤 · 风险优先',tone:'bad',rank:3};
  if((ixic!==null&&ixic<=-.025)||(spx!==null&&spx<=-.02)||(vix!==null&&vix>=28)) return {mode:'fear',level:'fear',title:'市场大跌 · 机会扫描完成',tone:'warn',rank:2};
  if((ixic!==null&&ixic<=-.015)||(spx!==null&&spx<=-.0125)||(vix!==null&&vix>=25)) return {mode:'fear',level:'watch',title:'波动升温 · 开始机会扫描',tone:'watch',rank:1};
  if((ixic!==null&&ixic>=.025||spx!==null&&spx>=.02)&&(vix===null||vix<20)) return {mode:'greed',level:'greed',title:'强势加速 · 高位风险观察',tone:'caution',rank:1};
  return {mode:'normal',level:'normal',title:'',tone:'neutral',rank:0};
}
function strategy(id){return (playbook().strategies||[]).find(x=>x.id===id)}
function learningForStage(stage){try{return global.MAVDecisionJournal?.learningForStage?.(stage)||null}catch{return null}}
function learningNote(x){const l=learningForStage(x.stage);if(!l||!l.stats||!l.stats.n)return '';const s=l.stats;return `历史同类60日：${s.n}样本 · 正收益${s.positive_rate==null?'—':Math.round(s.positive_rate*100)+'%'} · 平均${s.avg==null?'—':pct(s.avg)} · ${l.label||''}`;}
function candidates(mode){try{const rows=global.StockWatchlist?.assistantCandidates?.(mode)||[];return [...rows].sort((a,b)=>{const la=learningForStage(a.stage)?.research_adjustment||0,lb=learningForStage(b.stage)?.research_adjustment||0;return (b.hasThesis-a.hasThesis)||(lb-la)||((b.score??-999)-(a.score??-999));})}catch{return []}}
function stockStatus(){try{return global.StockWatchlist?.assistantStatus?.()||{count:0,researchCount:0,risk:[],improving:[],hot:[],loaded:false}}catch{return {count:0,researchCount:0,risk:[],improving:[],hot:[],loaded:false}}}
function usRegular(){const p=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',weekday:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date());const v=Object.fromEntries(p.map(x=>[x.type,x.value])),m=Number(v.hour)*60+Number(v.minute);return !['Sat','Sun'].includes(v.weekday)&&m>=570&&m<960}
function scanCadence(){return usRegular()?'盘中约5分钟自动复查':'当前休市；页面打开时检查，盘前盘后约30分钟复查'}
function nextScanAt(){const ms=usRegular()?5*60*1000:30*60*1000;return clock((state.lastScanAt||Date.now())+ms)}
function clock(ts=Date.now()){try{return new Date(ts).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}catch{return '—'}}
function button(label,tab){return `<button type="button" onclick="openDashboardTab('${tab}')">${label}</button>`}
function readJournal(){try{return JSON.parse(localStorage.getItem('mavDecisionJournalV51')||'[]')}catch{return []}}
function writeJournal(items){try{localStorage.setItem('mavDecisionJournalV51',JSON.stringify(items.slice(-120)))}catch{}}
function recordEvent(snapshot,c,items){
  const enriched=(items||[]).map(x=>{const snap=global.StockWatchlist?.assistantSnapshot?.(x.symbol)||{};return {...x,...snap}});
  if(global.MAVDecisionJournal?.recordAssistantEvent){global.MAVDecisionJournal.recordAssistantEvent({snapshot,classification:c,candidates:enriched,optionIdeas:state.optionIdeas});return}
  const key=[new Date().toISOString().slice(0,10),c.level,Math.round((snapshot.ixic||0)*1000),Math.round((snapshot.spx||0)*1000),Math.round(snapshot.vix||0)].join('|');
  const journal=readJournal();if(journal.some(x=>x.key===key))return;
  journal.push({key,at:new Date().toISOString(),level:c.level,mode:c.mode,spx:snapshot.spx,ixic:snapshot.ixic,vix:snapshot.vix,candidates:enriched,source:'automatic-scan-v5.3'});writeJournal(journal);
}
function notifyTransition(c){
  const key=`${c.mode}:${c.level}`;const prev=state.lastAlertKey;if(key===prev)return;
  state.lastAlertKey=key;state.lastAlertAt=Date.now();
  if(c.level==='normal'){if(prev&&prev!=='normal:normal')global.MAV?.toast?.('市场风险提醒已缓和，返回常态监测。','good');return}
  const msg=c.level==='panic'?'市场进入极端回撤级别，AI助手已重新扫描风险与机会。':c.level==='fear'?'市场进入大跌级别，AI助手已自动扫描关注股与期权研究方案。':c.mode==='greed'?'市场处于强势高位，AI助手已检查高位风险管理方案。':'市场波动升温，AI助手已开始机会扫描。';
  global.MAV?.toast?.(msg,c.level==='panic'?'bad':'warn');
}
function plainMarket(snapshot,c){
  if(c.level==='panic')return '市场出现极端波动。先处理风险与流动性，再看机会；不要因为跌幅大就默认“便宜”。';
  if(c.level==='fear')return '市场已经达到“大跌”提醒级别。现在更适合准备候选方案，而不是抢第一根反弹。';
  if(c.level==='watch')return '波动明显升温，但证据还不够强。系统先扫描候选，等待更清晰的修复或风险升级。';
  if(c.mode==='greed')return '市场处于强势高位。上涨很强不等于继续追高，已有仓位可开始比较保护和收益封顶方案。';
  return '市场处于常态。';
}
function stockDecision(x,c){
  const stage=String(x.stage||''),has=x.hasThesis;
  if(!has&&c.mode==='fear')return {tone:'wait',label:'先补研究论点',text:'没有 Thesis，不把技术反弹直接升级为期权机会。'};
  if(/退潮|恶化/.test(stage))return {tone:'risk',label:'等待修复',text:'分数可能仍高，但动态方向在转弱；Long Call/LEAPS 暂不优先。'};
  if(/二次启动|启动|重新/.test(stage))return {tone:'good',label:'优先研究',text:'趋势出现修复/重新转强，可进一步比较股票、Sell Put、Buy Call 或 LEAPS。'};
  if(/钝化|高位/.test(stage))return {tone:'watch',label:'谨慎观察',text:'仍然强，但上涨速度放慢；不因为高分继续追涨。'};
  return {tone:'watch',label:'继续观察',text:x.why||'等待更多证据确认。'};
}
function buildAgentSummary(snapshot,c,list){
  const ss=stockStatus();
  const market={name:'Market Agent',status:c.level==='normal'?'正常值守':c.title,detail:`NASDAQ ${pct(snapshot.ixic)} · S&P 500 ${pct(snapshot.spx)} · VIX ${snapshot.vix===null?'—':snapshot.vix.toFixed(1)}`};
  const stock={name:'Stock Agent',status:ss.loaded?`已扫描 ${ss.count} 只关注股`:'等待私有观察池',detail:ss.loaded?(ss.risk.length?`风险优先：${ss.risk.map(x=>x.symbol).join(' / ')}`:ss.improving.length?`修复关注：${ss.improving.map(x=>x.symbol).join(' / ')}`:`已有研究卡 ${ss.researchCount}/${ss.count}`):'登录后自动扫描 Thesis 与 Trend Pulse'};
  const options={name:'Options Agent',status:c.mode==='normal'?'当前无需启动':c.mode==='fear'?'检查 Sell Put / Buy Call / LEAPS':'检查 Covered Call / Protective Put',detail:c.mode==='normal'?'未达到市场级期权机会阈值':state.optionIdeas.length?`已找到 ${state.optionIdeas.length} 个合约/期限候选`:'触发环境中自动尝试读取期权链'};
  const risk={name:'Risk Agent',status:c.level==='panic'?'风险优先':c.level==='normal'?'暂无市场级高优先风险':'冲突过滤已启用',detail:'Thesis缺失、趋势退潮、数据过期时会降低优先级'};
  return [market,stock,options,risk];
}
function topThree(snapshot,c){
  const ss=stockStatus(),items=[];
  if(c.level==='normal') items.push({tone:'good',title:'市场无需特别处理',text:`NASDAQ ${pct(snapshot.ixic)}、S&P 500 ${pct(snapshot.spx)}、VIX ${snapshot.vix===null?'—':snapshot.vix.toFixed(1)}；尚未触发观察阈值。`,actions:[['查看市场细节','tab-overview']]});
  else items.push({tone:c.level==='panic'?'bad':'warn',title:c.title,text:plainMarket(snapshot,c),actions:[['查看市场细节','tab-overview']]});
  if(ss.loaded){
    if(ss.risk.length){const sym=ss.risk[0].symbol;items.push({tone:'bad',title:'关注池先看风险',text:`${ss.risk.map(x=>x.symbol).join(' / ')} 处于弱势或退潮阶段，优先复核 Thesis 与失效条件。`,symbol:sym,actions:[['查看研究卡','stock'],['看趋势','trend']]});}
    else if(ss.improving.length){const sym=ss.improving[0].symbol;items.push({tone:'good',title:'关注池出现修复',text:`${ss.improving.map(x=>x.symbol).join(' / ')} 出现重新转强/修复迹象，仍需基本面与价格条件确认。`,symbol:sym,actions:[['查看研究卡','stock'],['看趋势','trend']]});}
    else items.push({tone:'neutral',title:`关注池已扫描 ${ss.count} 只`,text:`当前没有需要升级为高优先级的个股变化；已有研究卡 ${ss.researchCount}/${ss.count}。`,actions:[['打开观察池','tab-stocks']]});
  }else items.push({tone:'neutral',title:'关注池等待扫描',text:'登录私有模式后，Stock Agent 会自动检查观察股、研究卡和 Trend Pulse。',actions:[['打开观察池','tab-stocks']]});
  if(c.mode==='normal')items.push({tone:'neutral',title:'期权暂不需要动作',text:'当前没有达到市场级 Sell Put / Buy Call / LEAPS 机会提醒阈值；继续等待条件变化。',actions:[['期权决策台','tab-sandbox']]});
  else if(c.mode==='fear')items.push({tone:'warn',title:'期权进入研究模式',text:'Sell Put / Buy Call / LEAPS 仅作为候选；先检查 Thesis、财报、IV、DTE 与最大风险。',actions:[['期权决策台','tab-sandbox']]});
  else items.push({tone:'warn',title:'高位风险管理',text:'可比较 Covered Call / Protective Put 的收益封顶与保护成本，不因高分继续追涨。',actions:[['期权决策台','tab-sandbox']]});
  return items.slice(0,3);
}
function actionHtml(item){
  const actions=item.actions||[];if(!actions.length)return '';
  return `<div class="assistant-inline-actions">${actions.map(([label,target])=>{if(target==='stock'&&item.symbol)return `<button type="button" onclick="StockWatchlist.focus('${esc(item.symbol)}')">${esc(label)}</button>`;if(target==='trend')return `<button type="button" onclick="openDashboardTab('tab-trend-pulse')">${esc(label)}</button>`;return `<button type="button" onclick="openDashboardTab('${esc(target)}')">${esc(label)}</button>`}).join('')}</div>`;
}
function optionIdeasHtml(){
  if(state.scanning)return '<div class="agent-option-scan"><b>Options Agent 正在自动读取期权链…</b><small>只扫描前3个关注池候选，避免无意义请求。</small></div>';
  if(!state.optionIdeas.length)return '<div class="agent-option-scan"><b>期权链候选尚未生成</b><small>未登录、行情权限不足或当前没有满足条件的标的时，系统只保留策略级提醒。</small></div>';
  return `<div class="agent-option-grid">${state.optionIdeas.map(x=>`<article><div><b>${esc(x.symbol)}</b><span>${esc(x.kind)}</span></div><strong>${esc(x.contract||x.expiration||'研究候选')}</strong><p>${esc(x.reason||'')}</p><small>${esc(x.metrics||'')}</small></article>`).join('')}</div>`;
}
function render(snapshot){
  const root=document.getElementById('marketOptionAlert');if(!root)return;
  const c=classify(snapshot.spx,snapshot.ixic,snapshot.vix);state.last={...snapshot,...c};state.lastSnapshot=snapshot;state.lastScanAt=Date.now();notifyTransition(c);
  root.hidden=false;root.classList.toggle('assistant-normal',c.mode==='normal');
  const list=candidates(c.mode),sp=strategy('fear-sell-put'),bc=strategy('fear-buy-call'),leaps=strategy('fear-leaps'),cc=strategy('greed-covered-call'),pp=strategy('greed-protective-put');
  recordEvent(snapshot,c,list);
  const agents=buildAgentSummary(snapshot,c,list);
  if(c.mode==='normal'){
    const top=topThree(snapshot,c);
    root.innerHTML=`<div class="assistant-duty-head"><div><span>AI INVESTMENT ASSISTANT · 自动值守</span><h2>AI 投资助手 · 正常值守</h2><p>没有重要触发也会持续扫描；只有状态变化时才升级提醒。</p></div><div class="assistant-scan-time"><b>最近扫描 ${clock(state.lastScanAt)}</b><small>${esc(scanCadence())} · 下一次约 ${nextScanAt()}</small></div></div><div class="agent-strip">${agents.map(a=>`<div><span>${esc(a.name)}</span><b>${esc(a.status)}</b><small>${esc(a.detail)}</small></div>`).join('')}</div><div class="assistant-top3"><div class="agent-section-title"><b>今天最重要的 3 件事</b><small>系统先替你看完，再告诉你什么值得处理。</small></div><div class="assistant-top3-grid">${top.map((x,i)=>`<article class="${esc(x.tone)}"><span>0${i+1}</span><div><b>${esc(x.title)}</b><p>${esc(x.text)}</p>${actionHtml(x)}</div></article>`).join('')}</div></div><p class="market-option-disclaimer">正常值守不等于“没有扫描”。Market / Stock / Options / Risk Agent 会持续复查；仅在条件变化时提高提醒等级。</p>`;
    return;
  }
  const candidateHtml=list.length?list.slice(0,6).map(x=>{const d=stockDecision(x,c);return `<article class="agent-stock ${d.tone}"><div><b>${esc(x.symbol)}</b><span>${esc(x.zone||'')}</span></div><strong>${esc(d.label)}</strong><p>${esc(d.text)}</p><small>${esc(x.why||'')} ${x.hasThesis?'· 已有研究卡':'· Thesis未填写'}${learningNote(x)?`<br>${esc(learningNote(x))}`:''}</small><div class="assistant-inline-actions"><button type="button" onclick="StockWatchlist.focus('${esc(x.symbol)}')">研究卡</button><button type="button" onclick="openDashboardTab('tab-trend-pulse')">趋势</button><button type="button" onclick="OptionV2.openForSymbol('${esc(x.symbol)}','SELL_PUT')">期权方案</button></div></article>`}).join(''):'<article class="agent-stock wait"><div><b>暂无个股候选</b></div><p>市场条件已触发，但观察池还没有满足多条件过滤的标的。</p></article>';
  const strategyHtml=c.mode==='fear'?`<article><strong>Sell Put</strong><p>${esc(sp?.plain||'')}</p><small>${esc(sp?.params||'')}</small></article><article><strong>Buy Call</strong><p>${esc(bc?.plain||'')}</p><small>先等修复确认，再检查IV与到期时间。</small></article><article><strong>LEAPS Call</strong><p>${esc(leaps?.plain||'')}</p><small>${esc(leaps?.params||'')}</small></article>`:`<article><strong>Covered Call</strong><p>${esc(cc?.plain||'')}</p></article><article><strong>Protective Put</strong><p>${esc(pp?.plain||'')}</p></article>`;
  root.innerHTML=`<div class="market-option-alert-head"><div><span>AUTONOMOUS INVESTMENT ASSISTANT · 最近 ${clock(state.lastScanAt)} · ${esc(scanCadence())} · 下次约 ${nextScanAt()}</span><h2>${esc(c.title)}</h2></div><div class="market-option-alert-numbers"><b>NASDAQ ${pct(snapshot.ixic)}</b><b>S&P 500 ${pct(snapshot.spx)}</b><b>VIX ${snapshot.vix===null?'—':snapshot.vix.toFixed(1)}</b></div></div><p class="market-option-alert-lead">${esc(plainMarket(snapshot,c))}</p><div class="agent-strip">${agents.map(a=>`<div><span>${esc(a.name)}</span><b>${esc(a.status)}</b><small>${esc(a.detail)}</small></div>`).join('')}</div><div class="agent-section-title"><b>关注池自动筛选</b><small>先过滤冲突，再给研究优先级；不会自动下单。</small></div><div class="agent-stock-grid">${candidateHtml}</div><div class="agent-section-title"><b>可研究的期权表达</b><small>策略经验先作为候选，不把单一市场跌幅机械转换为交易。</small></div><div class="market-option-strategies">${strategyHtml}</div>${c.mode==='fear'?`<div class="agent-section-title"><b>自动期权链初筛</b><small>Sell Put 按30–45 DTE、|Delta| 0.16–0.20；LEAPS 只做长期期限与流动性比较。</small></div>${optionIdeasHtml()}`:''}<div class="market-option-actions">${button('打开个股观察池','tab-stocks')}${button('进入期权决策与推演','tab-sandbox')}${button('查看决策复盘','tab-journal')}</div><details class="agent-rules"><summary>查看本次用到的策略规则</summary><div>${(registry().rules||[]).filter(r=>['首页','个股观察池','期权','全站'].includes(r.module)).map(r=>`<p><b>${esc(r.agent)} · ${esc(r.id)}</b> ${esc(r.trigger)}<br><span>${esc(r.action)}</span></p>`).join('')}</div></details><p class="market-option-disclaimer">自动扫描 ≠ 自动交易。AI只负责发现、解释、排序和冲突检查；核心ETF阈值不会自行学习修改，所有交易由投资者决定。</p>`;
  root.hidden=false;
  if(c.mode==='fear')scheduleOptionScan(list,c);
}
async function scheduleOptionScan(list,c){
  if(state.scanning||!list.length||!global.OptionV2?.autoScreenOpportunity)return;
  if(Date.now()-state.optionScanAt<10*60*1000)return;
  state.scanning=true;state.optionScanAt=Date.now();
  try{
    const picks=[];for(const x of list.slice(0,3)){try{const r=await global.OptionV2.autoScreenOpportunity(x.symbol,{marketLevel:c.level,stage:x.stage,hasThesis:x.hasThesis});if(Array.isArray(r))picks.push(...r)}catch(_){} }
    state.optionIdeas=picks.slice(0,8);
  }finally{state.scanning=false;if(state.lastSnapshot)render(state.lastSnapshot)}
}
function updateFromMarket(body){
  const spx=body?.exact?.spx?.changeBasis==='previous_regular_close'?n(body.exact.spx.changepct):null,ixic=body?.exact?.ixic?.changeBasis==='previous_regular_close'?n(body.exact.ixic.changepct):null,vix=n(body?.exact?.vix?.price);
  if(spx===null&&ixic===null&&vix===null)return;render({spx,ixic,vix,updated:Date.now()});
}
function rescan(){if(state.lastSnapshot)render(state.lastSnapshot)}
global.MAVInvestmentAssistant={classify,render,updateFromMarket,rescan,state,getJournal:readJournal,getRules:()=>registry().rules||[]};
})(window);
