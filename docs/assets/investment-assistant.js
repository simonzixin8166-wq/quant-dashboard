(function(global){
'use strict';
const playbook=()=>global.MYALPHA_STRATEGY_PLAYBOOK||{strategies:[]};
const state={last:null};
const n=v=>Number.isFinite(Number(v))?Number(v):null;
const pct=v=>v===null?'—':`${v>=0?'+':''}${(v*100).toFixed(2)}%`;
function classify(spx,ixic,vix){
  spx=n(spx);ixic=n(ixic);vix=n(vix);
  const worst=Math.min(spx??0,ixic??0);
  const best=Math.max(spx??0,ixic??0);
  if(worst<=-.04 || (spx!==null&&spx<=-.035) || (vix!==null&&vix>=35)) return {mode:'fear',level:'panic',title:'极端回撤 · 期权研究提醒',tone:'bad'};
  if(worst<=-.025 || (spx!==null&&spx<=-.02) || (vix!==null&&vix>=28)) return {mode:'fear',level:'fear',title:'市场大跌 · 期权机会观察',tone:'warn'};
  if(worst<=-.015 || (spx!==null&&spx<=-.0125) || (vix!==null&&vix>=25)) return {mode:'fear',level:'watch',title:'波动升温 · 提前检查期权方案',tone:'watch'};
  if(best>=.025 && (vix===null||vix<20)) return {mode:'greed',level:'greed',title:'强势加速 · 高位风险观察',tone:'caution'};
  return {mode:'normal',level:'normal',title:'',tone:'neutral'};
}
function candidates(mode){
  try{return global.StockWatchlist?.assistantCandidates?.(mode)||[]}catch{return []}
}
function strategy(id){return (playbook().strategies||[]).find(x=>x.id===id)}
function button(label,tab){return `<button type="button" onclick="openDashboardTab('${tab}')">${label}</button>`}
function render(snapshot){
  const root=document.getElementById('marketOptionAlert');if(!root)return;
  const c=classify(snapshot.spx,snapshot.ixic,snapshot.vix);state.last={...snapshot,...c};
  if(c.mode==='normal'){root.hidden=true;root.innerHTML='';return}
  const list=candidates(c.mode);
  if(c.mode==='fear'){
    const sp=strategy('fear-sell-put'),bc=strategy('fear-buy-call'),leaps=strategy('fear-leaps');
    const candidateText=list.length?list.map(x=>`<span><b>${x.symbol}</b><small>${x.zone} · ${x.why}${x.hasThesis?' · 已有研究卡':''}</small></span>`).join(''):'<span><b>QQQ</b><small>指数长期策略候选；个股候选登录后从观察池筛选</small></span>';
    root.innerHTML=`<div class="market-option-alert-head"><div><span>盘中5分钟检查</span><h2>${c.title}</h2></div><div class="market-option-alert-numbers"><b>NASDAQ ${pct(snapshot.ixic)}</b><b>S&P 500 ${pct(snapshot.spx)}</b><b>VIX ${snapshot.vix===null?'—':snapshot.vix.toFixed(1)}</b></div></div><p class="market-option-alert-lead">市场出现较大回撤时，先判断“基本逻辑是否仍成立”，再研究期权；不要把下跌本身当成买入理由。</p><div class="market-option-strategies"><article><strong>Sell Put</strong><p>${sp?.plain||''}</p><small>${sp?.params||''}</small></article><article><strong>Buy Call</strong><p>${bc?.plain||''}</p><small>先等修复确认，再检查IV与到期时间。</small></article><article><strong>LEAPS Call</strong><p>${leaps?.plain||''}</p><small>${leaps?.params||''}</small></article></div><div class="market-option-candidates"><div><b>关注池研究候选</b><small>自动排除明显“趋势恶化/退潮”；仍需人工核对 Thesis、财报和最大风险。</small></div><div class="market-option-candidate-list">${candidateText}</div></div><div class="market-option-actions">${button('打开个股观察池','tab-stocks')}${button('进入期权决策与推演','tab-sandbox')}</div><p class="market-option-disclaimer">研究触发器：NASDAQ约≤-1.5% / S&P 500约≤-1.25% / VIX≥25开始观察，更深回撤提高提醒级别。阈值是V5.0初始研究参数，后续应结合历史样本验证，不是自动交易信号。</p>`;
  }else{
    const cc=strategy('greed-covered-call'),pp=strategy('greed-protective-put');
    root.innerHTML=`<div class="market-option-alert-head"><div><span>盘中5分钟检查</span><h2>${c.title}</h2></div><div class="market-option-alert-numbers"><b>NASDAQ ${pct(snapshot.ixic)}</b><b>S&P 500 ${pct(snapshot.spx)}</b><b>VIX ${snapshot.vix===null?'—':snapshot.vix.toFixed(1)}</b></div></div><p class="market-option-alert-lead">强势上涨不等于继续追高。已有持仓可以研究收益封顶或尾部保护的代价。</p><div class="market-option-strategies"><article><strong>Covered Call</strong><p>${cc?.plain||''}</p></article><article><strong>Protective Put</strong><p>${pp?.plain||''}</p></article></div><div class="market-option-actions">${button('查看趋势状态','tab-trend-pulse')}${button('进入期权决策与推演','tab-sandbox')}</div><p class="market-option-disclaimer">高位提醒同样只是研究入口；是否使用期权取决于持仓、成本、催化剂和最大可承受风险。</p>`;
  }
  root.hidden=false;
}
function updateFromMarket(body){
  const spx=body?.exact?.spx?.changeBasis==='previous_regular_close'?n(body.exact.spx.changepct):null,ixic=body?.exact?.ixic?.changeBasis==='previous_regular_close'?n(body.exact.ixic.changepct):null,vix=n(body?.exact?.vix?.price);
  if(spx===null&&ixic===null&&vix===null)return;
  render({spx,ixic,vix,updated:Date.now()});
}
global.MAVInvestmentAssistant={classify,render,updateFromMarket,state};
})(window);
