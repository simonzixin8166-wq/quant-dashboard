(function(global){
  'use strict';
  const money=n=>Number.isFinite(n)?new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(n):'—';
  const cards=()=>[...document.querySelectorAll('[data-budget-symbol]')];
  const saveTimers=new Map();

  function renderCard(card){
    const reserve=Math.max(0,Number(card.querySelector('.budget-input')?.value)||0),rawDrawdown=card.dataset.drawdown,drawdown=rawDrawdown===''?NaN:Number(rawDrawdown),loss=Number.isFinite(drawdown)?-drawdown:null,tiers=[Number(card.dataset.t1),Number(card.dataset.t2),Number(card.dataset.t3)],alloc=[.2,.3,.5];
    card.querySelectorAll('[data-tier-amount]').forEach((node,i)=>node.textContent=reserve?money(reserve*alloc[i]):'—');
    let reached=0;tiers.forEach((x,i)=>{if(loss!==null&&loss>=x)reached=i+1});
    card.classList.toggle('triggered',reached>0);
    const next=card.querySelector('[data-budget-next]');
    if(!reserve)next.textContent='输入该资产预留资金后计算每档金额';
    else if(loss===null)next.textContent='ATH 尚未校验，不触发正式加仓档位';
    else if(reached===3)next.textContent=`已达三级：本档计划 ${money(reserve*.5)}（仅提示，不自动下单）`;
    else{const gap=Math.max(0,tiers[reached]-loss);next.textContent=`下一档：${reached+1}级，回撤幅度还差 ${Math.round(gap*1000)/10} 个百分点 · 计划 ${money(reserve*alloc[reached])}`}
  }

  function duplicateExposureNotice(){
    const grid=document.getElementById('strategyBudgetGrid');if(!grid)return;let notice=document.getElementById('budgetOverlapNotice');
    const values=Object.fromEntries(cards().map(c=>[c.dataset.budgetSymbol,Number(c.querySelector('.budget-input')?.value)||0]));
    const duplicate=values.QQQ>0&&values.QQQM>0;
    if(duplicate&&!notice){notice=document.createElement('div');notice.id='budgetOverlapNotice';notice.className='risk-alert l2';notice.innerHTML='<span class="risk-level">L2</span><div><strong>QQQ 与 QQQM 预算存在重叠敞口</strong><p>两者高度重合，请确认这是有意分配，避免把同一纳指100风险重复计算。</p></div>';grid.after(notice)}
    if(!duplicate&&notice)notice.remove();
  }

  async function save(card){
    const {data:{session}}=await supabaseClient.auth.getSession();if(!session)return;
    const payload={user_id:session.user.id,symbol:card.dataset.budgetSymbol,reserve_amount:Math.max(0,Number(card.querySelector('.budget-input').value)||0),currency:'USD',tier1_pct:.20,tier2_pct:.30,tier3_pct:.50,updated_at:new Date().toISOString()};
    const {error}=await supabaseClient.from('strategy_budgets').upsert(payload,{onConflict:'user_id,symbol'});
    if(error)global.MAV?.toast(`预算保存失败：${error.message}`,'bad');else global.MAV?.toast(`${payload.symbol} 预留资金已保存`,'good');
  }

  function bindCard(card,enabled){
    const input=card.querySelector('.budget-input');if(!input)return;input.disabled=!enabled;
    let clear=card.querySelector('.budget-clear');if(!clear){clear=document.createElement('button');clear.type='button';clear.className='budget-clear';clear.textContent='清除预算';clear.addEventListener('click',()=>clearBudget(card));card.append(clear)}clear.disabled=!enabled;
    if(input.dataset.bound)return;input.dataset.bound='1';input.addEventListener('input',()=>{renderCard(card);duplicateExposureNotice();const symbol=card.dataset.budgetSymbol;clearTimeout(saveTimers.get(symbol));saveTimers.set(symbol,setTimeout(()=>{saveTimers.delete(symbol);save(card)},600))});
  }

  async function clearBudget(card){
    const {data:{session}}=await supabaseClient.auth.getSession();if(!session)return;const symbol=card.dataset.budgetSymbol;if(!confirm(`清除 ${symbol} 的预留加仓资金？\n\n只删除手工预算，不改变策略阈值。`))return;clearTimeout(saveTimers.get(symbol));saveTimers.delete(symbol);const {error}=await supabaseClient.from('strategy_budgets').delete().eq('user_id',session.user.id).eq('symbol',symbol);if(error){global.MAV?.toast(`预算清除失败：${error.message}`,'bad');return}card.querySelector('.budget-input').value='';renderCard(card);duplicateExposureNotice();global.MAV?.toast(`${symbol} 预算已清除`,'good');
  }

  async function load(){
    if(typeof supabaseClient==='undefined')return;const {data:{session}}=await supabaseClient.auth.getSession();
    cards().forEach(c=>bindCard(c,Boolean(session)));
    if(!session){saveTimers.forEach(clearTimeout);saveTimers.clear();cards().forEach(card=>{const input=card.querySelector('.budget-input');if(input)input.value='';renderCard(card)});duplicateExposureNotice();return}
    const {data,error}=await supabaseClient.from('strategy_budgets').select('*');
    if(error){global.MAV?.toast(`预算读取失败：${error.message}`,'bad');return}
    const map=new Map((data||[]).map(x=>[x.symbol,x]));cards().forEach(card=>{const row=map.get(card.dataset.budgetSymbol),input=card.querySelector('.budget-input');if(row)input.value=Number(row.reserve_amount)||0;renderCard(card)});duplicateExposureNotice();
  }

  global.StrategyBudget={load,renderCard,clearBudget};
  if(typeof document!=='undefined')document.addEventListener('DOMContentLoaded',()=>cards().forEach(renderCard));
})(typeof window!=='undefined'?window:globalThis);
