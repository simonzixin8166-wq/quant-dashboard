(function(global){
'use strict';
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const rank={l3:3,l2:2,l1:1,unknown:0};
const state={timer:null,lastAt:0,systemStatus:null,serverAction:null,systemLoaded:false,serverLoaded:false};

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
function explicitSignal(x,authority,held=false){
 const base=global.MAVSignalPolicy?.classify?.({
   score:x?.score,stage:x?.stage,held,
   decisionEligible:authority?.decision_eligible!==false,
   hasThesis:x?.hasThesis
 });
 return base||{action:'WATCH',label:'WATCH',zh:'观察，不介入',tone:'neutral',reason:'等待统一信号策略加载',next_confirmation:''};
}
function opportunityAxes(x,kind,authority){
 const pulse=Number(x?.score);
 let opportunity='中',risk='中',confidence='低';
 if(kind==='improving')opportunity='高';
 if(kind==='hot'){opportunity='中';risk='高'}
 if(kind==='risk'){opportunity='低';risk='高'}
 if(Number.isFinite(pulse)&&pulse>=60&&kind==='improving')opportunity='高';
 if(Number.isFinite(pulse)&&pulse<20)opportunity='低';
 confidence=x?.hasThesis?'中':'低';
 const signal=explicitSignal(x,authority,false);
 return{opportunity,risk,confidence,action:signal.action,tone:signal.tone,actionZh:signal.zh,reason:signal.reason,nextConfirmation:signal.next_confirmation};
}
function opportunities(){
 const s=stockStatus(),seen=new Set(),rows=[],authority=decisionAuthority();
 const add=(x,label,why,kind)=>{if(!x?.symbol||seen.has(x.symbol))return;seen.add(x.symbol);const axes=opportunityAxes(x,kind,authority);rows.push({symbol:x.symbol,label,why:axes.reason||why,kind,...axes})};
 (s.improving||[]).forEach(x=>add(x,'趋势形成','趋势改善，等待系统动作判断','improving'));
 (s.hot||[]).forEach(x=>add(x,'强势区','强势不等于追涨，等待系统动作判断','hot'));
 (s.risk||[]).forEach(x=>add(x,'风险状态','系统将风险状态翻译为明确动作','risk'));
 const order={EXIT:8,REDUCE:7,CONFIRMED_ENTRY:6,EARLY_ENTRY:5,NO_ADD:4,HOLD:3,WAIT:2,WATCH:1,NO_SIGNAL:0};
 return rows.sort((a,b)=>(order[b.action]||0)-(order[a.action]||0)).slice(0,6);
}
function decisionAuthority(){
 const sys=state.systemStatus,server=state.serverAction,market=sys?.artifacts?.market_dashboard;
 const blocked=(detail,status='cannot_judge')=>({status,decision_eligible:false,title:'今日无法可靠判断',detail});
 if(!state.systemLoaded||!state.serverLoaded)return blocked('决策数据仍在加载；在 Data Trust 完整确认前不发布“正常/无需处理”结论。','loading');
 if(!sys||!server||!market)return blocked('系统状态或服务端动作状态缺失。');
 const generatedAt=Date.parse(sys.generated_at||'');
 const statusAgeHours=Number.isFinite(generatedAt)?(Date.now()-generatedAt)/36e5:Infinity;
 const marketOk=market.decision_eligible===true
   && market.business_freshness==='fresh'
   && Boolean(market.market_as_of)
   && Boolean(market.expected_market_date)
   && market.market_as_of===market.expected_market_date
   && statusAgeHours>=0
   && statusAgeHours<=30;
 if(!marketOk){
   return blocked(`美股日线 ${market.market_as_of||'未知'}，应为 ${market.expected_market_date||'最新完整交易日'}；Data Trust 未通过或状态快照已过期。`);
 }
 if(sys.overall==='attention'||sys.overall==='unknown')return blocked('系统状态存在未解决异常，暂不发布行动结论。');
 const unknown=Number(server?.action_counts?.unknown||0);
 const trustOk=server?.data_trust?.ok===true && ['ok','running'].includes(String(server?.data_trust?.overall||''));
 const serverOk=['clear','action_required'].includes(String(server?.status||''))&&unknown===0&&trustOk;
 if(!serverOk)return blocked('服务端发现数据缺失、过期或关键风险状态未知。');
 if(server.status==='action_required')return{status:'action_required',decision_eligible:true,title:'存在需要处理的事项',detail:'服务端风险扫描已发现需要处理或复核的事项。'};
 return{status:'ready',decision_eligible:true,title:'系统正常值守',detail:'关键数据与服务端风险状态允许当前判断。'};
}
function dataHealth(){
 const rows=[];
 const live=$('liveStatusText')?.textContent?.trim();
 if(live)rows.push({name:'市场行情',status:/成功|正常/.test(live)?'ok':'warn',detail:live});
 const market=state.systemStatus?.artifacts?.market_dashboard;
 if(market){
   const ok=market.decision_eligible===true&&market.business_freshness==='fresh';
   rows.push({name:'美股日线',status:ok?'ok':'bad',detail:ok?`业务日期 ${market.market_as_of} · 已匹配最新完整交易日`:`业务日期 ${market.market_as_of||'未知'} · 应为 ${market.expected_market_date||'最新完整交易日'}`});
 }else{
   const asof=$('usLiveAsOf')?.textContent?.trim();
   if(asof)rows.push({name:'美股日线',status:'warn',detail:asof});
 }
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
 (s.risk||[]).slice(0,3).forEach(x=>{const sig=explicitSignal(x,decisionAuthority(),false);rows.push({priority:sig.action==='NO_SIGNAL'?120:sig.action==='REDUCE'||sig.action==='EXIT'?90:65,tone:sig.tone,when:sig.action==='NO_SIGNAL'?'当前':'今日',title:`${x.symbol} · ${sig.label}`,text:`${sig.zh}。 ${sig.reason}`,target:'tab-stocks'})});
 (s.improving||[]).slice(0,3).forEach(x=>{const sig=explicitSignal(x,decisionAuthority(),false);rows.push({priority:sig.action==='CONFIRMED_ENTRY'?75:sig.action==='EARLY_ENTRY'?65:45,tone:sig.tone,when:/ENTRY/.test(sig.action)?'介入机会':'观察',title:`${x.symbol} · ${sig.label}`,text:`${sig.zh}。 ${sig.reason}`,target:'tab-stocks'})});
 const authority=decisionAuthority();
 if(!authority.decision_eligible){
   return [{priority:120,tone:'bad',when:'当前',title:authority.title,text:authority.detail,target:'tab-system-health'}];
 }
 if(!rows.length)rows.push({priority:10,tone:'neutral',when:'当前',title:'当前无需操作',text:'已完成当前可用数据检查，未发现需要升级处理的事项。',target:'tab-agent-center'});
 return rows.sort((a,b)=>(b.priority||0)-(a.priority||0)).slice(0,5);
}
function card(title,value,detail,tone='neutral'){return `<article class="pi-stat ${tone}"><span>${esc(title)}</span><b>${esc(value)}</b><small>${esc(detail)}</small></article>`}
function actionHtml(x,i){return `<article class="pi-action ${esc(x.tone)}"><span class="pi-seq">0${i+1}</span><div><div class="pi-action-top"><b>${esc(x.title)}</b><span>${esc(x.when)}</span></div><p>${esc(x.text)}</p><button type="button" data-pi-target="${esc(x.target)}">查看依据</button></div></article>`}
function opportunityHtml(x){return `<button type="button" class="pi-opportunity ${esc(x.tone)}" data-pi-symbol="${esc(x.symbol)}"><span>${esc(x.symbol)}</span><b>${esc(x.action)} <em>${esc(x.actionZh||'')}</em></b><small>${esc(x.why)}</small>${x.nextConfirmation?`<small>下一条件：${esc(x.nextConfirmation)}</small>`:''}<div class="pi-axes"><i>机会 ${esc(x.opportunity)}</i><i>风险 ${esc(x.risk)}</i><i>置信 ${esc(x.confidence)}</i></div></button>`}
function healthHtml(x){return `<div class="pi-health-row"><i class="${esc(x.status)}"></i><div><b>${esc(x.name)}</b><small>${esc(x.detail)}</small></div></div>`}

function render(){
 const root=$('productIntelligenceRoot');if(!root)return;
 const opts=optionRows(),actions=actionItems(),s=stockStatus(),opps=opportunities(),health=dataHealth(),server=state.serverAction,authority=decisionAuthority();
 const urgent=actions.filter(x=>x.tone==='bad').length,watch=actions.filter(x=>x.tone==='warn').length;
 root.innerHTML=`<section class="pi-shell">
  <div class="pi-head"><div><span>MYALPHA TODAY COCKPIT · SOLE ACTION OUTLET</span><h2>今日行动 · 唯一正式出口</h2><p>市场、个股、期权、策略及经 Promotion Gate 放行的学习信号统一在这里排序；其他页面只提供证据与解释。</p></div><div class="pi-head-state"><b>${esc(authority.title)}</b><small>${server?.generated_at?'服务端 '+new Date(server.generated_at).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):'等待服务端状态'}</small></div></div>
  <div class="pi-stats">
   ${card('今日高优先级',urgent,!authority.decision_eligible?'数据不足，不能下“无需操作”结论':urgent?'优先处理风险事项':'暂无高优先级触发',!authority.decision_eligible?'bad':urgent?'bad':'good')}
   ${card('待复核',watch,watch?'今日或次日处理':'当前无 L2 提醒',watch?'warn':'neutral')}
   ${card('期权持仓',opts.length,opts.length?'按账户独立监控':'等待私有持仓','neutral')}
   ${card('观察池',s.loaded?s.count:'—',s.loaded?`${s.researchCount} 只有完整 Thesis`:'登录后自动扫描','neutral')}
   ${card('机会候选',opps.filter(x=>x.action==='ACT'||x.action==='WATCH').length,'三轴：机会 / 风险 / 置信','good')}
  </div>
  <div class="pi-grid">
   <section class="pi-panel pi-actions"><div class="pi-panel-head"><div><span>01 / ACTIONS</span><h3>今天需要你处理</h3></div><button data-pi-target="tab-agent-center">查看研究过程</button></div><div class="pi-action-list">${actions.map(actionHtml).join('')}</div></section>
   <section class="pi-panel"><div class="pi-panel-head"><div><span>02 / OPPORTUNITY</span><h3>观察池机会与风险</h3></div><button data-pi-target="tab-stocks">查看个股依据</button></div><div class="pi-opportunity-list">${opps.length?opps.map(opportunityHtml).join(''):'<div class="pi-empty">当前没有需要升级的个股状态。</div>'}</div></section>
   <section class="pi-panel"><div class="pi-panel-head"><div><span>03 / DATA HEALTH</span><h3>数据是否值得信任</h3></div><button data-pi-target="tab-system-health">查看数据依据</button></div><div class="pi-health-list">${health.map(healthHtml).join('')}</div></section>
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
function recordDecisionState(){
 const s=state.serverAction,sys=state.systemStatus,market=sys?.artifacts?.market_dashboard;
 if(!s||!global.MAVDecisionJournal?.recordOperatorDecision)return;
 const authority=decisionAuthority();
 const decision=authority.status==='action_required'?'action_required':authority.decision_eligible?'no_action':'cannot_judge';
 const attribution=decision==='cannot_judge'?'data_error':'pending';
 const evidenceFingerprint=[
   authority.status,
   market?.market_as_of||'',
   market?.expected_market_date||'',
   s.status||'',
   Number(s?.action_counts?.unknown||0),
   Number(s?.action_counts?.l2||0),
   Number(s?.action_counts?.l3||0),
   Number(s?.action_counts?.thesis_review||0)
 ].join('|');
 global.MAVDecisionJournal.recordOperatorDecision({
   decision,source:'decision_authority',
   reason:authority.detail||authority.title||'',
   dataState:authority.decision_eligible?'eligible':'blocked',
   evidenceState:authority.decision_eligible?'usable':'insufficient',
   fingerprint:evidenceFingerprint,attribution
 });
}
async function loadSystemStatus(){
 try{const r=await fetch('research/system_status.json?v='+Date.now(),{cache:'no-store'});state.systemStatus=r.ok?await r.json():null}catch{state.systemStatus=null}finally{state.systemLoaded=true}
 try{const r=await fetch('research/server_action_status.json?v='+Date.now(),{cache:'no-store'});state.serverAction=r.ok?await r.json():null}catch{state.serverAction=null}finally{state.serverLoaded=true}
 window.dispatchEvent(new CustomEvent('mav:decision-authority',{detail:decisionAuthority()}));
 recordDecisionState();
}
function schedule(){clearInterval(state.timer);state.timer=setInterval(()=>{if(document.visibilityState==='visible')render()},120000)}
function init(){loadSystemStatus().finally(render);render();schedule();window.addEventListener('mav:options-updated',render);document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')render()});setTimeout(render,1200);setTimeout(render,3500)}
global.MAVProductIntelligence={render,optionActions,opportunities,dataHealth,decisionAuthority};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})(window);
