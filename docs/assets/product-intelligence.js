(function(global){
'use strict';
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const rank={l3:3,l2:2,l1:1,unknown:0};
const state={timer:null,lastAt:0,systemStatus:null,serverAction:null,strategyData:null,systemLoaded:false,serverLoaded:false,strategyLoaded:false};
const HOME_TEXT_LIMIT=52;
function compactText(value,limit=HOME_TEXT_LIMIT){
 const text=String(value||'').replace(/\s+/g,' ').trim();
 if(!text)return '';
 return text.length<=limit?text:text.slice(0,Math.max(8,limit-1)).trimEnd()+'…';
}
function actionBadges(x){
 const out=[],action=String(x?.title||'').split('·').pop()?.trim()||'';
 if(action&&action.length<=20)out.push(action);
 if(x?.when&&x.when!=='当前')out.push(String(x.when));
 if(x?.target==='tab-options')out.push('期权');
 else if(x?.target==='tab-engine')out.push('正式策略');
 else if(x?.target==='tab-stocks')out.push('个股');
 return [...new Set(out)].slice(0,3);
}
function mergeActionRows(rows){
 const toneRank={bad:4,warn:3,good:2,neutral:1},map=new Map();
 for(const row of rows||[]){
  const key=[row.target||'',row.title||''].join('|'),prev=map.get(key);
  if(!prev){map.set(key,{...row,reasons:[row.text].filter(Boolean),evidenceCount:1});continue}
  prev.priority=Math.max(Number(prev.priority)||0,Number(row.priority)||0);
  if((toneRank[row.tone]||0)>(toneRank[prev.tone]||0))prev.tone=row.tone;
  if(row.when&&row.when!==prev.when)prev.when=[prev.when,row.when].filter(Boolean).join(' / ');
  if(row.text&&!prev.reasons.includes(row.text))prev.reasons.push(row.text);
  prev.text=prev.reasons[0]||prev.text;prev.evidenceCount+=1;
 }
 return [...map.values()];
}

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
function stockHeld(x){
 const qty=Number(x?.position_qty??x?.quantity??x?.shares??0);
 return x?.held===true||x?.isHeld===true||(Number.isFinite(qty)&&qty!==0);
}
function explicitSignal(x,authority,held=stockHeld(x)){
 const base=global.MAVSignalPolicy?.classify?.({
   symbol:x?.symbol,score:x?.score,stage:x?.stage,held,
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
 const signal=explicitSignal(x,authority);
 return{opportunity,risk,confidence,action:signal.action,tone:signal.tone,actionZh:signal.zh,reason:signal.reason,nextConfirmation:signal.next_confirmation};
}
function opportunities(){
 const s=stockStatus(),seen=new Set(),rows=[],authority=decisionAuthority();
 const add=(x,label,why,kind)=>{if(!x?.symbol||seen.has(x.symbol))return;seen.add(x.symbol);const axes=opportunityAxes(x,kind,authority);rows.push({symbol:x.symbol,label,why:axes.reason||why,kind,...axes})};
 (s.improving||[]).forEach(x=>add(x,'趋势形成','趋势改善，等待系统动作判断','improving'));
 (s.hot||[]).forEach(x=>add(x,'强势区','强势不等于追涨，等待系统动作判断','hot'));
 (s.risk||[]).forEach(x=>add(x,'风险状态','系统将风险状态翻译为明确动作','risk'));
 const order={EXIT:8,REDUCE:7,CONFIRMED_ENTRY:6,EARLY_ENTRY:5,NO_ADD:4,HOLD:3,WAIT:2,WATCH:1,NO_SIGNAL:0};
 return rows.sort((a,b)=>(order[b.action]||0)-(order[a.action]||0));
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

function formalStrategyActions(data=state.strategyData){
 const rows=[];
 if(!data||typeof data!=='object')return rows;
 const core=data.core||{};
 Object.entries(core).forEach(([symbol,row])=>{
   const level=Number(row?.level||0),dd=Number(row?.strategy_drawdown);
   if(level>0){
     rows.push({priority:85,tone:'warn',when:'正式策略',title:`${symbol} · CORE TIER ${level}`,text:`正式核心 ETF 回撤档位已触发${Number.isFinite(dd)?` · 当前回撤 ${(dd*100).toFixed(1)}%`:``}；仅提示进入对应档位，不自动下单。`,target:'tab-engine'});
   }else{
     rows.push({priority:20,tone:'neutral',when:'HOLD',title:`${symbol} · HOLD`,text:'正式核心 ETF Tier 未触发；Trend / 新闻 / 外部研究不得提前升级为介入。',target:'tab-engine'});
   }
 });
 const x2=data.tqqq_x2||{};
 if(x2.available){
   if(x2.changed===true){
     rows.push({priority:88,tone:x2.snapshot?.hard_exit?'bad':'warn',when:'正式策略',title:'TQQQ X2 · ACTION',text:`${x2.action||x2.status_label||`正式状态变化`}；正式 X2 规则优先于技术/外部研究。`,target:'tab-engine'});
   }else{
     rows.push({priority:22,tone:'neutral',when:'HOLD',title:'TQQQ X2 · HOLD',text:`当前正式状态：${x2.status_label||`无变化`}；未发生正式状态迁移。`,target:'tab-engine'});
   }
 }
 const radar=data.leaps_radar||{};
 (radar.assets||[]).forEach(r=>{
   const triggered=String(r?.status||'normal')!=='normal';
   rows.push({priority:triggered?40:18,tone:triggered?'warn':'neutral',when:triggered?'WATCH':'HOLD',title:`${r.symbol||`LEAPS`} LEAPS · ${triggered?`WATCH`:`HOLD`}`,text:triggered?`LEAPS Radar：${r.status_label||r.status}；仍需 IV / Bid-Ask / DTE / Delta / 风险预算核验。`:'LEAPS Radar 未触发；外部文章或趋势信号不得升级为介入。',target:'tab-engine'});
 });
 return rows;
}
function actionItems(){
 const opt=optionActions(),s=stockStatus(),rows=formalStrategyActions();
 opt.filter(x=>x.risk==='l3').forEach(x=>rows.push({priority:100,tone:'bad',when:'今日',title:`${x.symbol} 期权需处理`,text:x.reason,target:'tab-options'}));
 opt.filter(x=>x.risk==='l2').forEach(x=>rows.push({priority:80,tone:'warn',when:'今日 / 次日',title:`${x.symbol} 期权复核`,text:x.reason,target:'tab-options'}));
 opt.filter(x=>x.timing.includes('止盈')).forEach(x=>rows.push({priority:70,tone:'good',when:'今日',title:`${x.symbol} 可评估止盈`,text:x.reason,target:'tab-options'}));
 (s.risk||[]).forEach(x=>{const sig=explicitSignal(x,decisionAuthority());rows.push({priority:sig.action==='NO_SIGNAL'?120:sig.action==='REDUCE'||sig.action==='EXIT'?90:65,tone:sig.tone,when:sig.action==='NO_SIGNAL'?'当前':'今日',title:`${x.symbol} · ${sig.label}`,text:`${sig.zh}。 ${sig.reason}`,target:'tab-stocks'})});
 (s.improving||[]).forEach(x=>{const sig=explicitSignal(x,decisionAuthority());rows.push({priority:sig.action==='CONFIRMED_ENTRY'?75:sig.action==='EARLY_ENTRY'?65:45,tone:sig.tone,when:/ENTRY/.test(sig.action)?'介入机会':'观察',title:`${x.symbol} · ${sig.label}`,text:`${sig.zh}。 ${sig.reason}`,target:'tab-stocks'})});
 if(state.strategyLoaded&&!state.strategyData)rows.push({priority:110,tone:'bad',when:'当前',title:'正式策略数据缺失',text:'Core Tier / TQQQ X2 / LEAPS Radar 无法可靠判断，禁止用技术信号代替正式策略。',target:'tab-system-health'});
 const authority=decisionAuthority();
 if(!authority.decision_eligible){
   return [{priority:120,tone:'bad',when:'当前',title:authority.title,text:authority.detail,target:'tab-system-health'}];
 }
 if(!rows.length)rows.push({priority:10,tone:'neutral',when:'当前',title:'当前无需操作',text:'已完成当前可用数据检查，未发现需要升级处理的事项。',target:'tab-agent-center'});
 return mergeActionRows(rows).sort((a,b)=>(b.priority||0)-(a.priority||0));
}
function actionGroup(x){
 const t=String(x.title||'');
 if(/EXIT|REDUCE|需处理|高风险|止盈/.test(t)||x.tone==='bad')return '立即处理';
 if(/CONFIRMED ENTRY|EARLY ENTRY|介入机会/.test(t))return '介入机会';
 if(/HOLD|NO ADD/.test(t))return '持有 / 停止加仓';
 return '观察 / 复核';
}
function groupKey(name){return {'立即处理':'urgent','介入机会':'entry','持有 / 停止加仓':'hold','观察 / 复核':'review'}[name]||'review'}
function groupedActionsHtml(rows){
 const order=['立即处理','介入机会','持有 / 停止加仓','观察 / 复核'];
 return order.map(name=>{
   const all=rows.filter(x=>actionGroup(x)===name),limit=name==='立即处理'?5:4,xs=all.slice(0,limit);
   if(!xs.length)return '';
   const more=all.length>xs.length?`<div class="pi-more-note">另有 ${all.length-xs.length} 项，进入对应模块查看</div>`:'';
   return `<div class="pi-action-group" data-pi-group="${groupKey(name)}"><div class="pi-action-group-head"><b>${esc(name)}</b><span>${all.length} 项</span></div><div class="pi-action-list">${xs.map(actionHtml).join('')}</div>${more}</div>`;
 }).join('');
}
function card(title,value,detail,tone='neutral',jump='',aria=''){
 const attrs=jump?` role="button" tabindex="0" data-pi-jump="${esc(jump)}" aria-label="${esc(aria||title)}"`:'';
 return `<article class="pi-stat ${tone}${jump?' clickable':''}"${attrs}><span>${esc(title)}</span><b>${esc(value)}</b><small>${esc(detail)}</small>${jump?'<em>点击查看 →</em>':''}</article>`;
}
function actionHtml(x,i){
 const badges=actionBadges(x).map(v=>`<i>${esc(v)}</i>`).join(''),merged=x.evidenceCount>1?`<i>${x.evidenceCount}条依据</i>`:'';
 return `<article class="pi-action ${esc(x.tone)}"><span class="pi-seq">${String(i+1).padStart(2,'0')}</span><div class="pi-action-body"><div class="pi-action-top"><b>${esc(x.title)}</b><span>${esc(x.when)}</span></div><p>${esc(compactText(x.text))}</p><div class="pi-action-foot"><div class="pi-tags">${badges}${merged}</div><button type="button" data-pi-target="${esc(x.target)}">依据</button></div></div></article>`}
function opportunityHtml(x){
 const why=compactText(x.why,46);
 return `<button type="button" class="pi-opportunity ${esc(x.tone)}" data-pi-symbol="${esc(x.symbol)}"><div class="pi-opportunity-head"><span>${esc(x.symbol)}</span><b>${esc(x.action)}</b></div><small>${esc(why)}</small><div class="pi-axes"><i>机会 ${esc(x.opportunity)}</i><i>风险 ${esc(x.risk)}</i><i>置信 ${esc(x.confidence)}</i></div></button>`
}
function healthHtml(x){return `<div class="pi-health-row"><i class="${esc(x.status)}"></i><div><b>${esc(x.name)}</b><small>${esc(x.detail)}</small></div></div>`}

function render(){
 const root=$('productIntelligenceRoot');if(!root)return;
 const opts=optionRows(),actions=actionItems(),s=stockStatus(),opps=opportunities(),health=dataHealth(),server=state.serverAction,authority=decisionAuthority();
 const urgent=actions.filter(x=>x.tone==='bad').length,watch=actions.filter(x=>x.tone==='warn').length;
 root.innerHTML=`<section class="pi-shell">
  <div class="pi-head"><div><span>MYALPHA TODAY</span><h2>今日结论</h2><p>首页只显示需要关注的结果；详细证据与推导下沉到对应模块。</p></div><div class="pi-head-state"><b>${esc(authority.title)}</b><small>${server?.generated_at?'更新 '+new Date(server.generated_at).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):'等待状态'}</small></div></div>
  <div class="pi-stats">
   ${card('今日高优先级',urgent,!authority.decision_eligible?'数据不足，不能下“无需操作”结论':urgent?'优先处理风险事项':'暂无高优先级触发',!authority.decision_eligible?'bad':urgent?'bad':'good','group:urgent','查看今日高优先级事项')}
   ${card('待复核',watch,watch?'今日或次日处理':'当前无 L2 提醒',watch?'warn':'neutral','group:review','查看待复核事项')}
   ${card('期权持仓',opts.length,opts.length?'按账户独立监控':'等待私有持仓','neutral','tab:tab-options','进入期权持仓')}
   ${card('观察池',s.loaded?s.count:'—',s.loaded?`${s.researchCount} 只有完整 Thesis`:'登录后自动扫描','neutral','tab:tab-stocks','进入观察池')}
   ${card('机会候选',opps.filter(x=>['EARLY_ENTRY','CONFIRMED_ENTRY','WATCH','WAIT'].includes(x.action)).length,'三轴：机会 / 风险 / 置信','good','group:entry','查看机会候选')}
  </div>
  <div class="pi-grid">
   <section class="pi-panel pi-actions"><div class="pi-panel-head"><div><span>01 / ACTION</span><h3>需要关注</h3></div><button data-pi-target="tab-agent-center">全部依据</button></div><div class="pi-action-groups">${groupedActionsHtml(actions)}</div></section>
   <section class="pi-panel"><div class="pi-panel-head"><div><span>02 / WATCH</span><h3>机会与风险</h3></div><button data-pi-target="tab-stocks">个股模块</button></div><div class="pi-opportunity-list">${opps.length?opps.slice(0,6).map(opportunityHtml).join(''):'<div class="pi-empty">当前没有需要升级的状态。</div>'}</div></section>
   <section class="pi-panel"><div class="pi-panel-head"><div><span>03 / TRUST</span><h3>系统状态</h3></div><button data-pi-target="tab-system-health">数据模块</button></div><div class="pi-health-list">${health.slice(0,5).map(healthHtml).join('')}</div></section>
  </div>
  <div class="pi-module-strip">
   <button data-pi-target="tab-overview"><span>市场</span><b>Regime / VIX / Breadth</b></button>
   <button data-pi-target="tab-stocks"><span>Portfolio</span><b>观察池 / Thesis / 风险</b></button>
   <button data-pi-target="tab-options"><span>Options</span><b>持仓 / Delta / DTE / Roll</b></button>
   <button data-pi-target="tab-engine"><span>Strategy</span><b>核心 ETF / TQQQ / LEAPS</b></button>
   <button data-pi-target="tab-wenxuecity"><span>Research</span><b>Source / Evidence / Authors</b></button>
  </div>
 </section>`;
 function jumpStat(el){
   const jump=el?.dataset?.piJump||'';
   if(jump.startsWith('tab:')){global.openDashboardTab?.(jump.slice(4));return}
   if(jump.startsWith('group:')){
     const key=jump.slice(6),target=root.querySelector('[data-pi-group="'+key+'"]')||root.querySelector('.pi-actions');
     target?.scrollIntoView?.({behavior:'smooth',block:'start'});
     target?.classList?.add('pi-focus-flash');setTimeout(()=>target?.classList?.remove('pi-focus-flash'),1400);
   }
 }
 root.querySelectorAll('[data-pi-target]').forEach(b=>b.addEventListener('click',()=>global.openDashboardTab?.(b.dataset.piTarget)));
 root.querySelectorAll('[data-pi-symbol]').forEach(b=>b.addEventListener('click',()=>global.StockWatchlist?.focus?.(b.dataset.piSymbol)));
 root.querySelectorAll('[data-pi-jump]').forEach(el=>{el.addEventListener('click',()=>jumpStat(el));el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();jumpStat(el)}})});
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
 try{const r=await fetch('data.json?v='+Date.now(),{cache:'no-store'});state.strategyData=r.ok?await r.json():null}catch{state.strategyData=null}finally{state.strategyLoaded=true}
 window.dispatchEvent(new CustomEvent('mav:decision-authority',{detail:decisionAuthority()}));
 recordDecisionState();
}
function schedule(){clearInterval(state.timer);state.timer=setInterval(()=>{if(document.visibilityState==='visible')render()},120000)}
function init(){loadSystemStatus().finally(render);render();schedule();window.addEventListener('mav:options-updated',render);document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')render()});setTimeout(render,1200);setTimeout(render,3500)}
global.MAVProductIntelligence={render,optionActions,opportunities,dataHealth,decisionAuthority,formalStrategyActions,explicitSignal};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})(window);
