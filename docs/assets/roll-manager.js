(function(global){
  'use strict';
  const $=id=>typeof document==='undefined'?null:document.getElementById(id);
  const money=n=>Number.isFinite(Number(n))?new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(Number(n)):'—';
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const dateDiff=(a,b)=>Math.ceil((new Date(`${b}T20:00:00Z`)-new Date(`${a}T20:00:00Z`))/86400000);
  const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const state={underlyings:[],positions:[],journal:[],activeId:null,session:null};

  function classifyRoll({delta,observation='intraday',watch=.70,urgent=.80,catalyst=false,watchCloses=0,dte=99,optionType='call',assignmentMode='avoid'}={}){
    const d=Math.abs(Number(delta));
    if(!Number.isFinite(d))return{key:'missing',level:'neutral',label:'待补Delta',action:'先从IBKR录入Delta'};
    if(observation!=='close')return{key:'intraday',level:'neutral',label:'盘中参考',action:'不触发纪律，等待收盘确认'};
    if(dte<=7&&d<.30)return{key:'expiry',level:'good',label:'低Delta临期',action:'观察自然到期；仍需留意提前指派'};
    if(String(optionType).toLowerCase()==='put'&&assignmentMode==='accept'){
      if(d>=urgent)return{key:'assignment',level:'warn',label:'接货/展期二选一',action:'已深度承压；愿意接货则核对现金，不愿接货则尽快Roll Down & Out'};
      if(d>=watch)return{key:'put_watch',level:'warn',label:'接货风险上升',action:'检查基本面、现金担保与有效接货成本'};
      return{key:'hold',level:'good',label:'继续持有',action:'尚未进入Sell Put观察区'};
    }
    if(d>=urgent)return{key:'urgent',level:'bad',label:'尽快评估展期',action:'已越过紧急阈值；核对价差、指派与事件风险'};
    if(d>=watch&&catalyst)return{key:'catalyst',level:'bad',label:'催化剂触发',action:'有实锤事件，尽快评估展期'};
    if(d>=watch&&Number(watchCloses)>=2)return{key:'roll',level:'warn',label:'考虑展期',action:'已连续两个收盘处于观察区'};
    if(d>=watch)return{key:'watch',level:'warn',label:'观察1–2个收盘',action:'未确认催化剂，不因单日脉冲仓促操作'};
    return{key:'hold',level:'good',label:'继续持有',action:'Delta尚未进入观察区'};
  }

  function rollMath({type='call',oldStrike,newStrike,oldExpiry,newExpiry,closeDebit,openCredit,closeFee=0,openFee=0,qty=1,multiplier=100,priorPremium=0}={}){
    const units=Math.max(1,Number(qty)||1)*Math.max(1,Number(multiplier)||100);
    const netCash=(Number(openCredit)-Number(closeDebit))*units-Number(closeFee||0)-Number(openFee||0);
    const chain=Number(priorPremium)+(Number(openCredit)-Number(closeDebit))-(Number(closeFee||0)+Number(openFee||0))/units;
    const addedDays=dateDiff(oldExpiry,newExpiry),strikeChange=Number(newStrike)-Number(oldStrike);
    return{units,netCash,chain,addedDays,strikeChange,effectivePrice:String(type).toLowerCase()==='call'?Number(newStrike)+chain:Number(newStrike)-chain};
  }

  function coverage(shares,positions){
    const total=Math.max(0,Number(shares)||0);
    const contracts=(positions||[]).filter(p=>String(p.side).toLowerCase()==='short'&&String(p.opt_type).toLowerCase()==='call'&&String(p.collateral_mode).toLowerCase()==='covered').reduce((sum,p)=>sum+(Number(p.qty)||0)*(Number(p.multiplier)||100),0);
    return{shares:total,contractShares:contracts,covered:Math.min(total,contracts),uncovered:Math.max(0,total-contracts),excess:Math.max(0,contracts-total)};
  }

  function parseTranches(text){
    if(Array.isArray(text))return text;
    return String(text||'').split(/\n|;/).map(x=>x.trim()).filter(Boolean).map(line=>{
      const m=line.match(/^\s*([0-9.]+)(?:\s*[-~至]\s*([0-9.]+))?\s*[:：,，]\s*([0-9.]+)%?\s*$/);
      return m?{low:Number(m[1]),high:Number(m[2]||m[1]),pct:Number(m[3])}:null;
    }).filter(Boolean);
  }
  function formatTranches(rows){return(rows||[]).map(x=>`${x.low}${x.high!==x.low?`-${x.high}`:''}:${x.pct}%`).join('\n')}
  function etDate(value){return value?new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(value)):''}
  function observationDue(p){return p.delta_observation!=='close'||etDate(p.delta_observed_at)!==today()}
  function getPosition(id){return state.positions.find(x=>String(x.id)===String(id))}
  function getUnderlying(symbol){return state.underlyings.find(x=>x.symbol===symbol)}
  function cachedQuote(id){try{return JSON.parse(sessionStorage.getItem(`optionQuote:${id}`)||'null')?.quote||null}catch(_e){return null}}

  async function load(){
    const root=$('rollManagerRoot');if(!root)return;
    const {data:{session}}=await supabaseClient.auth.getSession();state.session=session;
    if(!session){$('rollManagerSummary').innerHTML='<div class="roll-empty">登录私有看板后读取展期计划。</div>';$('rollUnderlyingGrid').innerHTML='';$('rollPositionList').innerHTML='';return}
    $('rollManagerSummary').innerHTML='<div class="roll-empty skeleton">正在读取展期纪律与日志</div>';
    const [u,p,j]=await Promise.all([
      supabaseClient.from('option_underlyings').select('*').order('symbol'),
      supabaseClient.from('options_positions').select('*').in('status',['open','pending_settlement']).order('expiry'),
      supabaseClient.from('option_roll_journal').select('*').order('executed_at',{ascending:false}).limit(20)
    ]);
    const error=u.error||p.error||j.error;
    if(error){
      const hint=/option_underlyings|option_roll_journal|monitor_delta|schema cache/i.test(error.message)?'请先执行 supabase/migrations/202609230001_option_roll_manager.sql。':'';
      $('rollManagerSummary').innerHTML=`<div class="roll-empty roll-error">展期管理尚未初始化：${esc(error.message)} ${esc(hint)}</div>`;return;
    }
    state.underlyings=u.data||[];state.positions=(p.data||[]).filter(x=>String(x.side).toLowerCase()==='short'&&['call','put'].includes(String(x.opt_type).toLowerCase()));state.journal=j.data||[];
    render();
  }

  function render(){renderSummary();renderUnderlyings();renderPositions();renderHistory()}
  function renderSummary(){
    let covered=0,uncovered=0,watch=0,urgent=0,due=0;
    state.underlyings.forEach(u=>{const c=coverage(u.shares,state.positions.filter(p=>p.symbol===u.symbol));covered+=c.covered;uncovered+=c.uncovered});
    state.positions.forEach(p=>{const q=cachedQuote(p.id),u=getUnderlying(p.symbol),isPut=String(p.opt_type).toLowerCase()==='put',delta=p.monitor_delta??q?.delta,observation=p.monitor_delta!==null&&p.monitor_delta!==undefined?p.delta_observation:'intraday',dte=dateDiff(today(),p.expiry),s=classifyRoll({delta,observation,watch:isPut?(u?.put_watch_delta??.50):(u?.watch_delta??.70),urgent:isPut?(u?.put_urgent_delta??.70):(u?.urgent_delta??.80),catalyst:p.catalyst_confirmed,watchCloses:p.watch_close_count,dte,optionType:p.opt_type,assignmentMode:u?.put_assignment_mode??'accept'});if(s.level==='warn')watch++;if(s.level==='bad')urgent++;if(observationDue(p))due++});
    $('rollManagerSummary').innerHTML=`<div class="roll-kpi"><span>收盘Delta待更新</span><strong class="${due?'neg-text':''}">${due}笔</strong></div><div class="roll-kpi"><span>已覆盖正股</span><strong>${covered}股</strong></div><div class="roll-kpi"><span>保留上涨空间</span><strong>${uncovered}股</strong></div><div class="roll-kpi"><span>观察区</span><strong>${watch}笔</strong></div><div class="roll-kpi"><span>需尽快评估</span><strong class="${urgent?'neg-text':''}">${urgent}笔</strong></div>`;
  }
  function renderUnderlyings(){
    const host=$('rollUnderlyingGrid');if(!state.underlyings.length){host.innerHTML='<div class="roll-empty">尚无正股覆盖计划。可载入IREN示例后再按实际成交修改。</div>';return}
    host.innerHTML=state.underlyings.map(u=>{const positions=state.positions.filter(p=>p.symbol===u.symbol),c=coverage(u.shares,positions),pnl=Number.isFinite(Number(u.current_price))?(Number(u.current_price)-Number(u.cost_basis))*Number(u.shares):null,tranches=Array.isArray(u.target_tranches)?u.target_tranches:[];return `<article class="underlying-card"><div class="underlying-head"><div><strong>${esc(u.symbol)}</strong><span>${u.shares}股 · 成本 ${money(u.cost_basis)}</span></div><button onclick="RollManager.openUnderlying('${esc(u.symbol)}')">编辑计划</button></div><div class="coverage-bar"><i style="width:${c.shares?Math.min(100,c.covered/c.shares*100):0}%"></i></div><div class="coverage-grid"><span>Covered <b>${c.covered}</b></span><span>裸露 <b>${c.uncovered}</b></span><span>正股浮盈亏 <b class="${pnl!==null&&pnl<0?'neg-text':'pos-text'}">${pnl===null?'—':money(pnl)}</b></span></div>${c.excess?`<div class="roll-warning">覆盖合约超出持股 ${c.excess} 股，请核对是否为裸Call。</div>`:''}<div class="tranche-row">${tranches.length?tranches.map(x=>`<span>${money(x.low)}${x.high!==x.low?`–${money(x.high)}`:''} · ${x.pct}%</span>`).join(''):'<span>未设置分层减仓目标</span>'}</div><button class="roll-add-contract" onclick="RollManager.prefillOption('${esc(u.symbol)}')">＋ 为${esc(u.symbol)}录入Covered Call</button></article>`}).join('');
  }
  function renderPositions(){
    const host=$('rollPositionList');if(!state.positions.length){host.innerHTML='<div class="roll-empty">当前没有开放的 Short Call / Short Put。录入持仓后会自动出现在这里。</div>';return}
    host.innerHTML=state.positions.map(p=>{const isCall=String(p.opt_type).toLowerCase()==='call',u=getUnderlying(p.symbol),q=cachedQuote(p.id),manual=p.monitor_delta!==null&&p.monitor_delta!==undefined,delta=manual?Number(p.monitor_delta):Number(q?.delta),observation=manual?p.delta_observation:'intraday',dte=dateDiff(today(),p.expiry),status=classifyRoll({delta,observation,watch:isCall?(u?.watch_delta??.70):(u?.put_watch_delta??.50),urgent:isCall?(u?.urgent_delta??.80):(u?.put_urgent_delta??.70),catalyst:p.catalyst_confirmed,watchCloses:p.watch_close_count,dte,optionType:p.opt_type,assignmentMode:u?.put_assignment_mode??'accept'}),units=(Number(p.qty)||1)*(Number(p.multiplier)||100),netEntry=Number(p.cost)-(Number(p.open_fee)||0)/units,chain=Number.isFinite(Number(p.premium_chain_per_share))?Number(p.premium_chain_per_share):netEntry,effective=isCall?Number(p.strike)+chain:Number(p.strike)-chain,entryDte=p.entry_date?Math.max(1,dateDiff(p.entry_date,p.expiry)):null,capital=isCall?Number(u?.current_price||u?.cost_basis):Number(p.strike)-netEntry,annualized=entryDte&&capital>0?netEntry/capital*365/entryDte:null,belowCost=isCall&&u&&effective<Number(u.cost_basis),due=observationDue(p);return `<article class="roll-position ${status.level}"><div class="roll-position-main"><div><div class="roll-symbol">${esc(p.symbol)} <span>${isCall?'Covered Call · Roll Up':'Sell Put · Roll Down & Out'}</span></div><strong>${money(p.strike)} · ${esc(p.expiry)} · ${dte} DTE</strong><small>${p.qty}张 × ${p.multiplier||100}｜累计净权利金 ${money(chain)}/股｜${isCall?'有效卖出价':'有效接货成本'} ${money(effective)}${belowCost?' · ⚠ 低于正股成本':''}</small></div><div class="roll-status ${status.level}"><b>${status.label}</b><span>${status.action}</span></div></div><div class="roll-observation"><span class="${due?'roll-due':''}">${due?'收盘Delta待更新':'今日收盘已更新'}</span><span>Delta <b>${Number.isFinite(delta)?delta.toFixed(3):'—'}</b></span><span>${observation==='close'?'收盘确认':'盘中/自动参考'}</span><span>连续观察 ${p.watch_close_count||0} 次</span><span>${p.catalyst_confirmed?'已确认催化剂':'无实锤催化剂'}</span><span>本周期年化参考 <b>${Number.isFinite(annualized)?(annualized*100).toFixed(1)+'%':'待补数据'}</b></span></div><div class="roll-actions"><button onclick="RollManager.openMonitor('${p.id}')">更新收盘Delta</button><button class="primary" onclick="RollManager.openCalculator('${p.id}')">计算并记录展期</button></div></article>`}).join('');
  }
  function renderHistory(){
    const host=$('rollHistoryBody');if(!host)return;host.innerHTML=state.journal.length?state.journal.map(x=>`<tr><td>${esc(x.symbol)} · ${x.strategy==='covered_call'?'CC':'SP'}</td><td>${money(x.old_strike)} / ${esc(x.old_expiry)}</td><td>${money(x.new_strike)} / ${esc(x.new_expiry)}</td><td class="${Number(x.net_roll_cash)>=0?'pos-text':'neg-text'}">${money(x.net_roll_cash)}</td><td>${money(x.cumulative_premium_per_share)}/股</td><td>${new Date(x.executed_at).toLocaleString()}</td></tr>`).join(''):'<tr><td colspan="6" class="roll-empty">尚无展期记录</td></tr>';
  }

  function openUnderlying(symbol=''){
    const u=getUnderlying(symbol);$('underlyingSymbol').value=u?.symbol||symbol;$('underlyingSymbol').disabled=Boolean(u);$('underlyingShares').value=u?.shares??600;$('underlyingCost').value=u?.cost_basis??51;$('underlyingPrice').value=u?.current_price??'';$('underlyingTargets').value=formatTranches(u?.target_tranches||[{low:65,high:70,pct:50},{low:75,high:80,pct:50}]);$('underlyingWatch').value=u?.watch_delta??.70;$('underlyingUrgent').value=u?.urgent_delta??.80;$('putWatch').value=u?.put_watch_delta??.50;$('putUrgent').value=u?.put_urgent_delta??.70;$('putAssignmentMode').value=u?.put_assignment_mode??'accept';$('underlyingModal').style.display='grid';
  }
  function closeUnderlying(){$('underlyingModal').style.display='none'}
  async function saveUnderlying(){
    const symbol=$('underlyingSymbol').value.trim().toUpperCase(),shares=Number($('underlyingShares').value),cost_basis=Number($('underlyingCost').value),currentRaw=$('underlyingPrice').value,current_price=currentRaw===''?null:Number(currentRaw),target_tranches=parseTranches($('underlyingTargets').value),watch_delta=Number($('underlyingWatch').value),urgent_delta=Number($('underlyingUrgent').value),put_watch_delta=Number($('putWatch').value),put_urgent_delta=Number($('putUrgent').value),put_assignment_mode=$('putAssignmentMode').value;
    if(!symbol||!Number.isInteger(shares)||shares<0||cost_basis<0||!(watch_delta>0&&watch_delta<urgent_delta&&urgent_delta<=1)||!(put_watch_delta>0&&put_watch_delta<put_urgent_delta&&put_urgent_delta<=1)){alert('请检查股票代码、股数、成本和Call/Put两套Delta阈值。');return}
    if($('underlyingTargets').value.trim()&&!target_tranches.length){alert('减仓计划格式示例：65-70:50%（每行一档）。');return}
    const payload={user_id:state.session.user.id,symbol,shares,cost_basis,current_price,target_tranches,watch_delta,urgent_delta,put_watch_delta,put_urgent_delta,put_assignment_mode,updated_at:new Date().toISOString()};const {error}=await supabaseClient.from('option_underlyings').upsert(payload,{onConflict:'user_id,symbol'});if(error){global.MAV?.toast(`保存失败：${error.message}`,'bad');return}closeUnderlying();await load();global.MAV?.toast(`${symbol} 覆盖计划已保存`,'good');
  }
  function loadIrenPreset(){openUnderlying('');$('underlyingSymbol').value='IREN';$('underlyingShares').value='600';$('underlyingCost').value='51';$('underlyingTargets').value='65-70:50%\n75-80:50%'}
  function prefillOption(symbol){
    if(typeof global.openAddOptionModal!=='function')return;global.openAddOptionModal();$('optSym').value=symbol;$('optStrategy').value='SELL CALL';$('optCollateralMode').value='covered';$('optQty').value='3';$('optMultiplier').value='100';
  }

  function fillMonitor(p){
    const q=cachedQuote(p.id);$('rollPositionId').value=p.id;$('rollModalTitle').textContent=`${p.symbol} ${p.opt_type} ${money(p.strike)} 展期管理`;$('rollModalSummary').textContent=`${p.qty}张 × ${p.multiplier||100}｜到期 ${p.expiry}｜先录入收盘Delta，再按IBKR组合单实际成交记账`;$('rollDelta').value=p.monitor_delta??(Number.isFinite(Number(q?.delta))?Number(q.delta).toFixed(4):'');$('rollObservation').value=p.delta_observation||'close';$('rollWatchCloses').value=p.watch_close_count||0;$('rollCatalyst').checked=Boolean(p.catalyst_confirmed);$('rollNotes').value=p.strategy_note||'';
  }
  async function openMonitor(id){let p=getPosition(id);if(!p){await load();p=getPosition(id)}if(!p){global.MAV?.toast('未找到可展期的开放仓位','warn');return}state.activeId=String(id);fillMonitor(p);$('rollCalculator').hidden=true;$('confirmRollBtn').hidden=true;$('rollModal').style.display='grid';updateMonitorPreview()}
  async function openCalculator(id){let p=getPosition(id);if(!p){await load();p=getPosition(id)}if(!p){global.MAV?.toast('未找到可展期的开放仓位','warn');return}state.activeId=String(id);fillMonitor(p);$('rollCalculator').hidden=false;$('confirmRollBtn').hidden=false;$('newRollStrike').value=String(p.opt_type).toLowerCase()==='call'?(Number(p.strike)+5).toFixed(2):Math.max(.01,Number(p.strike)-5).toFixed(2);$('newRollExpiry').value=p.expiry;$('rollCloseDebit').value='';$('rollOpenCredit').value='';$('rollCloseFee').value='0';$('rollOpenFee').value='0';$('rollModal').style.display='grid';updateMonitorPreview();updateRollPreview()}
  function closeRoll(){$('rollModal').style.display='none';state.activeId=null}
  function updateMonitorPreview(){
    const p=getPosition(state.activeId);if(!p)return;const u=getUnderlying(p.symbol),isPut=String(p.opt_type).toLowerCase()==='put',s=classifyRoll({delta:Number($('rollDelta').value),observation:$('rollObservation').value,watch:isPut?(u?.put_watch_delta??.50):(u?.watch_delta??.70),urgent:isPut?(u?.put_urgent_delta??.70):(u?.urgent_delta??.80),catalyst:$('rollCatalyst').checked,watchCloses:Number($('rollWatchCloses').value),dte:dateDiff(today(),p.expiry),optionType:p.opt_type,assignmentMode:u?.put_assignment_mode??'accept'});$('monitorPreview').innerHTML=`<b class="${s.level==='bad'?'neg-text':s.level==='good'?'pos-text':''}">${s.label}</b><span>${s.action}</span>`;
  }
  async function saveObservation(){
    const p=getPosition(state.activeId),delta=Number($('rollDelta').value),observation=$('rollObservation').value,watch_close_count=Number($('rollWatchCloses').value)||0,catalyst_confirmed=$('rollCatalyst').checked,strategy_note=$('rollNotes').value.trim();if(!p||!Number.isFinite(delta)||Math.abs(delta)>1){alert('Delta必须在 -1 到 1 之间。');return}
    const {error}=await supabaseClient.from('options_positions').update({monitor_delta:delta,delta_observation:observation,delta_observed_at:new Date().toISOString(),watch_close_count,catalyst_confirmed,strategy_note:strategy_note||null}).eq('id',p.id);if(error){global.MAV?.toast(`保存失败：${error.message}`,'bad');return}await load();if($('rollModal').style.display==='grid'){const fresh=getPosition(p.id);if(fresh)fillMonitor(fresh);updateMonitorPreview()}global.MAV?.toast('Delta观察已保存','good');
  }
  function updateRollPreview(){
    const p=getPosition(state.activeId);if(!p)return;const prior=Number.isFinite(Number(p.premium_chain_per_share))?Number(p.premium_chain_per_share):Number(p.cost)-(Number(p.open_fee)||0)/((Number(p.qty)||1)*(Number(p.multiplier)||100)),inputs={type:p.opt_type,oldStrike:p.strike,newStrike:Number($('newRollStrike').value),oldExpiry:p.expiry,newExpiry:$('newRollExpiry').value,closeDebit:Number($('rollCloseDebit').value),openCredit:Number($('rollOpenCredit').value),closeFee:Number($('rollCloseFee').value)||0,openFee:Number($('rollOpenFee').value)||0,qty:p.qty,multiplier:p.multiplier,priorPremium:prior};if(!inputs.newExpiry||![inputs.newStrike,inputs.closeDebit,inputs.openCredit].every(Number.isFinite)){$('rollPreview').innerHTML='<span>填入IBKR旧仓买回价和新仓卖出价后计算。</span>';return}const r=rollMath(inputs),type=String(p.opt_type).toLowerCase();$('rollPreview').innerHTML=`<div><span>本次净收/付</span><b class="${r.netCash>=0?'pos-text':'neg-text'}">${money(r.netCash)}</b></div><div><span>行权价变化</span><b>${r.strikeChange>=0?'+':''}${money(r.strikeChange)}</b></div><div><span>延长天数</span><b>${r.addedDays}天</b></div><div><span>累计净权利金</span><b>${money(r.chain)}/股</b></div><div><span>${type==='call'?'有效卖出价':'有效接货成本'}</span><b>${money(r.effectivePrice)}</b></div>`;
  }
  async function confirmRoll(){
    const p=getPosition(state.activeId);if(!p)return;const newStrike=Number($('newRollStrike').value),newExpiry=$('newRollExpiry').value,closeDebit=Number($('rollCloseDebit').value),openCredit=Number($('rollOpenCredit').value),closeFee=Number($('rollCloseFee').value)||0,openFee=Number($('rollOpenFee').value)||0,observation=$('rollObservation').value,catalyst=$('rollCatalyst').checked,notes=$('rollNotes').value.trim();if(!(newStrike>0)||!newExpiry||closeDebit<0||openCredit<0){alert('请完整填写新行权价、到期日和双腿实际成交价。');return}if(newExpiry<p.expiry){alert('新到期日不能早于旧合约到期日。');return}if(String(p.opt_type).toLowerCase()==='call'&&newStrike<Number(p.strike)){alert('Roll Up的新行权价不能低于旧行权价。');return}if(String(p.opt_type).toLowerCase()==='put'&&newStrike>Number(p.strike)){alert('Roll Down的新行权价不能高于旧行权价。');return}if(!confirm('仅在IBKR组合单已经成交后确认。系统将关闭旧仓、建立新仓并写入不可混淆的展期日志。继续吗？'))return;
    $('confirmRollBtn').disabled=true;const {data,error}=await supabaseClient.rpc('record_option_roll',{p_old_position_id:Number(p.id),p_new_strike:newStrike,p_new_expiry:newExpiry,p_close_debit:closeDebit,p_open_credit:openCredit,p_close_fee:closeFee,p_open_fee:openFee,p_observation_type:observation,p_catalyst_confirmed:catalyst,p_notes:notes||null});$('confirmRollBtn').disabled=false;if(error){global.MAV?.toast(`展期记账失败：${error.message}`,'bad');return}closeRoll();await load();await global.OptionV2?.loadPrivatePositions();global.MAV?.toast(`展期已记账：净额 ${money(data?.net_roll_cash)}`,'good');
  }

  global.RollManager={classifyRoll,rollMath,coverage,parseTranches,load,openUnderlying,closeUnderlying,saveUnderlying,loadIrenPreset,prefillOption,openMonitor,openCalculator,closeRoll,updateMonitorPreview,saveObservation,updateRollPreview,confirmRoll};
  if(typeof document!=='undefined')document.addEventListener('DOMContentLoaded',load);
})(typeof window!=='undefined'?window:globalThis);
