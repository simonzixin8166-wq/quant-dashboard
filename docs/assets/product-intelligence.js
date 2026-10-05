(function(global){
'use strict';
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const rank={l3:3,l2:2,l1:1,unknown:0};
const state={timer:null,lastAt:0,systemStatus:null};

function optionRows(){
 const api=global.OptionV2;if(!api?.getPositions)return[];
 return api.getPositions().map(p=>{
   const cached=api.getCachedQuote?.(p.id)||null;
   const fresh=api.quoteFreshness?.(cached)||{status:'unavailable',usable:false,label:'等待报价'};
   const quote=fresh.usable?cached?.quote:null;
   const risk=api.positionRisk?.(p,quote,fresh)||{level:'unknown',label:'等待报价',dte:null,events:[]};
   const metrics=quote&&api.positionMetrics?api.positionMetrics(p,quote):null;
   return{p,cached,fresh,quote,risk,metrics};
 });
}
function optionActions(){
 return optionRows().map(x=>{
   const p=x.p,r=x.risk,m=x.metrics,dte=Number(r.dte),side=String(p.side||'').toLowerCase();
   let timing='继续观察',tone='neutral',reason=r.label||'等待有效报价';
   if(r.level==='l3'){timing='今日处理';tone='bad'}
   else if(r.level==='l2'){timing=dte<=7?'今日处理':'次日复核';tone='warn'}
   else if(m&&Number.isFinite(m.pnlPct)&&side==='short'&&m.pnlPct>=.70){timing='今日评估止盈';tone='good';reason=`已捕获约 ${(m.pnlPct*100).toFixed(0)}% 权利金，比较剩余收益与尾部风险`}
   else if(Number.isFinite(dte)&&dte<=14){timing='次日复核';tone='warn';reason=`距到期 ${dte} 天，检查 Delta / 事件 / 行权偏好`}
   return{symbol:p.symbol||'—',expiry:p.expiry||'',timing,tone,reason,risk:r.level||'unknown',id:p.id};
 }).sort((a,b)=>(rank[b.risk]||0)-(rank[a.risk]||0)||String(a.expiry).localeCompare(String(b.expiry)));
}
function stockStatus(){try{return global.StockWatchlist?.assistantStatus?.()||{count:0,researchCount:0,risk:[],improving:[],hot:[],loaded:false}}catch{return{count:0,researchCount:0,risk:[],improving:[],hot:[],loaded:false}}}
function opportunityScore(x,kind){
 let score=50;
 const pulse=Number(x?.score);
 if(Number.isFinite(pulse))score+=Math.max(-20,Math.min(20,pulse/5));
 if(x?.hasThesis)score+=10;
 if(kind==='improving')score+=15;
 if(kind==='hot')score-=8;
 if(kind==='risk')score-=25;
 return Math.max(0,Math.min(100,Math.round(score)));
}
function opportunities(){
 const s=stockStatus(),seen=new Set(),rows=[];
 const add=(x,tone,label,why,kind)=>{if(!x?.symbol||seen.has(x.symbol))return;seen.add(x.symbol);rows.push({symbol:x.symbol,tone,label,why,score:opportunityScore(x,kind)})};
 (s.improving||[]).forEach(x=>add(x,'good','修复 / 转强','趋势改善，下一步核对 Thesis、策略价与事件风险','improving'));
 (s.hot||[]).forEach(x=>add(x,'warn','强势但偏热','保持关注，不因高分追涨；等待更好的风险收益位置','hot'));
 (s.risk||[]).forEach(x=>add(x,'bad','风险优先','趋势退潮或恶化，优先复核 Thesis 与失效条件','risk'));
 return rows.sort((a,b)=>b.score-a.score).slice(0,4);
}
function dataHealth(){
 const rows=[];
 const live=$('liveStatusText')?.textContent?.trim();
 if(live)rows.push({name:'市场行情',status:/成功|正常/.test(live)?'ok':'warn',detail:live});
 const asof=$('usLiveAsOf')?.textContent?.trim();
 if(asof)rows.push({name:'美股日线',status:/截至/.test(asof)?'ok':'warn',detail:asof});
 const opt=global.OptionV2?.getPositions?optionRows():[];
 if(opt.length){
   const usable=opt.filter(x=>x.fresh?.usable).length;
   rows.push({name:'期权报价',status:usable===opt.length?'ok':usable?'warn':'bad',detail:`${usable}/${opt.length} 个持仓有可用报价`});
 }
 const s=stockStatus();
 rows.push({name:'观察池',status:s.loaded?'ok':'warn',detail:s.loaded?`${s.count} 只已载入 · ${s.researchCount} 只有 Thesis`:'等待登录后载入'});
 const sourceText=[...document.querySelectorAll('#tab-wenxuecity .wxc-warning')].map(x=>x.textContent).join(' ');
 if(sourceText)rows.push({name:'研究来源',status:'warn',detail:'部分来源需要核验；历史资料仍可用'});
 else rows.push({name:'研究来源',status:'ok',detail:'Source Intelligence 已启用 fail-closed 保护'});
 const guard=state.systemStatus?.resource_guard;
 if(guard)rows.push({name:'免费额度守门',status:guard.mode==='normal'?'ok':guard.mode==='watch'?'warn':'bad',detail:`${guard.mode==='normal'?'正常':'已进入'+guard.mode} · 缓存优先/事件驱动`});
 return rows.slice(0,6);
}
function actionItems(){
 const opt=optionActions(),s=stockStatus(),rows=[];
 opt.filter(x=>x.risk==='l3').slice(0,2).forEach(x=>rows.push({priority:100,tone:'bad',when:'今日',title:`${x.symbol} 期权需处理`,text:x.reason,target:'tab-options'}));
 opt.filter(x=>x.risk==='l2').slice(0,2).forEach(x=>rows.push({priority:80,tone:'warn',when:'今日 / 次日',title:`${x.symbol} 期权复核`,text:x.reason,target:'tab-options'}));
 opt.filter(x=>x.timing.includes('止盈')).slice(0,2).forEach(x=>rows.push({priority:70,tone:'good',when:'今日',title:`${x.symbol} 可评估止盈`,text:x.reason,target:'tab-options'}));
 (s.risk||[]).slice(0,2).forEach(x=>rows.push({priority:85,tone:'bad',when:'今日',title:`${x.symbol} Thesis 复核`,text:'趋势转弱/退潮，先确认原始逻辑是否仍成立。',target:'tab-stocks'}));
 (s.improving||[]).slice(0,2).forEach(x=>rows.push({priority:50,tone:'good',when:'观察',title:`${x.symbol} 出现修复`,text:'趋势改善，继续检查策略价、基本面与事件条件。',target:'tab-stocks'}));
 if(!rows.length)rows.push({priority:10,tone:'neutral',when:'当前',title:'没有必须立即处理的事项',text:'系统继续扫描市场、观察池、期权与研究来源；正常状态保持安静。',target:'tab-agent-center'});
 return rows.sort((a,b)=>(b.priority||0)-(a.priority||0)).slice(0,5);
}
function card(title,value,detail,tone='neutral'){return `<article class="pi-stat ${tone}"><span>${esc(title)}</span><b>${esc(value)}</b><small>${esc(detail)}</small></article>`}
function actionHtml(x,i){return `<article class="pi-action ${esc(x.tone)}"><span class="pi-seq">0${i+1}</span><div><div class="pi-action-top"><b>${esc(x.title)}</b><span>${esc(x.when)}</span></div><p>${esc(x.text)}</p><button type="button" data-pi-target="${esc(x.target)}">打开处理</button></div></article>`}
function opportunityHtml(x){return `<button type="button" class="pi-opportunity ${esc(x.tone)}" data-pi-symbol="${esc(x.symbol)}"><span>${esc(x.symbol)}</span><b>${esc(x.label)} <em>${esc(x.score)}/100</em></b><small>${esc(x.why)}</small></button>`}
function healthHtml(x){return `<div class="pi-health-row"><i class="${esc(x.status)}"></i><div><b>${esc(x.name)}</b><small>${esc(x.detail)}</small></div></div>`}

function render(){
 const root=$('productIntelligenceRoot');if(!root)return;
 const opts=optionRows(),actions=actionItems(),s=stockStatus(),opps=opportunities(),health=dataHealth();
 const urgent=actions.filter(x=>x.tone==='bad').length,watch=actions.filter(x=>x.tone==='warn').length;
 root.innerHTML=`<section class="pi-shell">
  <div class="pi-head"><div><span>MYALPHA DAILY COMMAND CENTER</span><h2>今日行动与组合智能</h2><p>把市场、持仓、期权、观察池、机会和数据状态合到一页；先看需要处理什么，再决定是否深入。</p></div><div class="pi-head-state"><b>${urgent?'有高优先级事项':'系统正常值守'}</b><small>最近整理 ${new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}</small></div></div>
  <div class="pi-stats">
   ${card('今日高优先级',urgent,urgent?'优先处理风险事项':'暂无 L3 / Thesis 失效提醒',urgent?'bad':'good')}
   ${card('待复核',watch,watch?'今日或次日处理':'当前无 L2 提醒',watch?'warn':'neutral')}
   ${card('期权持仓',opts.length,opts.length?'按账户独立监控':'等待私有持仓','neutral')}
   ${card('观察池',s.loaded?s.count:'—',s.loaded?`${s.researchCount} 只有完整 Thesis`:'登录后自动扫描','neutral')}
   ${card('机会候选',opps.filter(x=>x.tone==='good').length,'只显示修复/转强，不做自动交易','good')}
  </div>
  <div class="pi-grid">
   <section class="pi-panel pi-actions"><div class="pi-panel-head"><div><span>01 / ACTIONS</span><h3>今天需要你处理</h3></div><button data-pi-target="tab-agent-center">完整 AI 中心</button></div><div class="pi-action-list">${actions.map(actionHtml).join('')}</div></section>
   <section class="pi-panel"><div class="pi-panel-head"><div><span>02 / OPPORTUNITY</span><h3>观察池机会与风险</h3></div><button data-pi-target="tab-stocks">个股研究</button></div><div class="pi-opportunity-list">${opps.length?opps.map(opportunityHtml).join(''):'<div class="pi-empty">当前没有需要升级的个股状态。</div>'}</div></section>
   <section class="pi-panel"><div class="pi-panel-head"><div><span>03 / DATA HEALTH</span><h3>数据是否值得信任</h3></div><button data-pi-target="tab-system-health">系统状态</button></div><div class="pi-health-list">${health.map(healthHtml).join('')}</div></section>
  </div>
  <div class="pi-module-strip">
   <button data-pi-target="tab-overview"><span>市场</span><b>Regime / VIX / Breadth</b></button>
   <button data-pi-target="tab-stocks"><span>Portfolio</span><b>观察池 / Thesis / 风险</b></button>
   <button data-pi-target="tab-options"><span>Options</span><b>持仓 / Delta / DTE / Roll</b></button>
   <button data-pi-target="tab-engine"><span>Strategy</span><b>核心 ETF / TQQQ / LEAPS</b></button>
   <button data-pi-target="tab-wenxuecity"><span>Research</span><b>Source / Evidence / Authors</b></button>
  </div>
 </section>`;
 root.querySelectorAll('[data-pi-target]').forEach(b=>b.addEventListener('click',()=>global.openDashboardTab?.(b.dataset.piTarget)));
 root.querySelectorAll('[data-pi-symbol]').forEach(b=>b.addEventListener('click',()=>global.StockWatchlist?.focus?.(b.dataset.piSymbol)));
 state.lastAt=Date.now();
}
async function loadSystemStatus(){
 try{const r=await fetch('research/system_status.json?v='+Date.now(),{cache:'no-store'});state.systemStatus=r.ok?await r.json():null}catch{state.systemStatus=null}
}
function schedule(){clearInterval(state.timer);state.timer=setInterval(()=>{if(document.visibilityState==='visible')render()},120000)}
function init(){loadSystemStatus().finally(render);render();schedule();window.addEventListener('mav:options-updated',render);document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')render()});setTimeout(render,1200);setTimeout(render,3500)}
global.MAVProductIntelligence={render,optionActions,opportunities,dataHealth};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})(window);
