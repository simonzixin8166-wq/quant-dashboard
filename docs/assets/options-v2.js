(function(global){
  'use strict';
  const MULTIPLIER=100;
  const $=id=>document.getElementById(id);
  const money=n=>Number.isFinite(n)?new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(n):'—';
  const pct=n=>Number.isFinite(n)?`${(n*100).toFixed(1)}%`:'—';
  const quoteNumber=v=>v===null||v===undefined||v===''?NaN:Number(v);
  const clamp=(n,a,b)=>Math.min(b,Math.max(a,n));
  const QUOTE_FRESH_MS=30*60*1000,QUOTE_USABLE_MS=90*60*1000,CLOSED_REFERENCE_MS=5*24*60*60*1000,POSITION_REFRESH_MS=15*60*1000;
  function isUsRegularSession(now=new Date()){
    const parts=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',weekday:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(now),v=Object.fromEntries(parts.map(x=>[x.type,x.value]));
    const minute=Number(v.hour)*60+Number(v.minute);return !['Sat','Sun'].includes(v.weekday)&&minute>=570&&minute<960;
  }
  function quoteFreshness(cached,now=Date.now(),sessionOpen=isUsRegularSession(new Date(now))){
    if(!cached?.quote||!Number.isFinite(Number(cached.at)))return{status:'unavailable',label:'无有效报价',tone:'unavailable',usable:false,fresh:false,ageMs:Infinity};
    const providerAt=Number(cached.quote.updated)*1000,sourceAt=Number.isFinite(providerAt)&&providerAt>0?providerAt:Number(cached.at);
    const ageMs=Math.max(0,now-sourceAt),minutes=Math.max(1,Math.round(ageMs/60000));
    const ageLabel=minutes<60?`${minutes}分钟前`:`${Math.round(minutes/6)/10}小时前`;
    if(!sessionOpen&&ageMs<=CLOSED_REFERENCE_MS)return{status:'closed',label:`休市 · 上次报价 ${ageLabel}`,tone:'closed',usable:true,fresh:false,live:false,ageMs,sourceAt};
    if(ageMs<=QUOTE_FRESH_MS)return{status:'fresh',label:`新鲜 · ${ageLabel}`,tone:'fresh',usable:true,fresh:true,live:true,ageMs,sourceAt};
    if(ageMs<=QUOTE_USABLE_MS)return{status:'delayed',label:`延迟 · ${ageLabel}`,tone:'delayed',usable:true,fresh:false,live:true,ageMs,sourceAt};
    return{status:'stale',label:`已过期 · ${ageLabel}`,tone:'stale',usable:false,fresh:false,live:false,ageMs,sourceAt};
  }
  function readCachedQuote(id){
    if(typeof sessionStorage==='undefined')return null;
    try{return JSON.parse(sessionStorage.getItem(`optionQuote:${id}`)||'null')}catch(_error){return null}
  }
  function normCdf(x){const t=1/(1+.2316419*Math.abs(x)),d=.3989423*Math.exp(-x*x/2);let p=1-d*t*(.31938153+t*(-.356563782+t*(1.781477937+t*(-1.821255978+t*1.330274429))));return x>=0?p:1-p}
  function bsPrice(S,K,T,r,sigma,type,q=0){
    if(![S,K,T,sigma].every(Number.isFinite)||S<0||K<=0)return 0;
    if(T<=0||sigma<=0)return type==='call'?Math.max(0,S-K):Math.max(0,K-S);
    if(S===0)return type==='put'?K*Math.exp(-r*T):0;
    const root=Math.sqrt(T),d1=(Math.log(S/K)+(r-q+.5*sigma*sigma)*T)/(sigma*root),d2=d1-sigma*root;
    return type==='call'?S*Math.exp(-q*T)*normCdf(d1)-K*Math.exp(-r*T)*normCdf(d2):K*Math.exp(-r*T)*normCdf(-d2)-S*Math.exp(-q*T)*normCdf(-d1);
  }
  function rawDaysBetween(a,b){return Math.ceil((new Date(`${b}T20:00:00Z`)-new Date(`${a}T20:00:00Z`))/86400000)}
  function daysBetween(a,b){return Math.max(0,rawDaysBetween(a,b))}
  function strategyMeta(strategy){
    const map={SELL_PUT:{type:'put',side:'short',label:'Sell Put · 现金担保'},BUY_PUT:{type:'put',side:'long',label:'Buy Put'},BUY_CALL:{type:'call',side:'long',label:'Buy Call'},COVERED_CALL:{type:'call',side:'short',label:'Covered Call · 备兑'},NAKED_CALL:{type:'call',side:'short',label:'Naked Call · 裸卖'}};
    return map[strategy]||map.SELL_PUT;
  }
  function evaluate(p){
    const meta=strategyMeta(p.strategy),qty=Math.max(1,Number(p.qty)||1),mult=Number(p.multiplier)||MULTIPLIER,entry=Number(p.premium)||0,fee=(Number(p.fee)||0)*qty*2;
    const remaining=Math.max(0,(Number(p.dte)||0)-(Number(p.forwardDays)||0)),futureIv=Math.max(.0001,(Number(p.iv)||.35)*(1+(Number(p.ivChange)||0)));
    const option=bsPrice(Number(p.targetSpot),Number(p.strike),remaining/365,Number(p.rate)||.042,futureIv,meta.type,Number(p.dividend)||0);
    const optionPnl=(meta.side==='long'?option-entry:entry-option)*mult*qty;
    const stockQty=p.strategy==='COVERED_CALL'?mult*qty:0;
    const stockPnl=stockQty*((Number(p.targetSpot)||0)-(Number(p.stockCost)||Number(p.spot)||0));
    const gross=optionPnl+stockPnl,net=gross-fee,premiumCash=entry*mult*qty;
    let maxProfit=Infinity,maxLoss=Infinity,breakeven=0,capital=0;
    if(p.strategy==='SELL_PUT'){maxProfit=premiumCash-fee;maxLoss=(p.strike-entry)*mult*qty+fee;breakeven=p.strike-entry;capital=maxLoss}
    if(p.strategy==='BUY_PUT'){maxProfit=(p.strike-entry)*mult*qty-fee;maxLoss=premiumCash+fee;breakeven=p.strike-entry;capital=maxLoss}
    if(p.strategy==='BUY_CALL'){maxLoss=premiumCash+fee;breakeven=p.strike+entry;capital=maxLoss}
    if(p.strategy==='NAKED_CALL'){maxProfit=premiumCash-fee;breakeven=p.strike+entry;capital=0}
    if(p.strategy==='COVERED_CALL'){const c=Number(p.stockCost)||Number(p.spot)||0;maxProfit=(p.strike-c+entry)*mult*qty-fee;maxLoss=(c-entry)*mult*qty+fee;breakeven=c-entry;capital=c*mult*qty-premiumCash}
    return{optionPrice:option,positionValue:option*mult*qty,grossPnl:gross,netPnl:net,returnOnCapital:capital>0?net/capital:null,maxProfit,maxLoss,breakeven,capital,remaining,futureIv,premiumCash,qty,mult,meta};
  }
  function normalizeColumnar(raw){
    if(!raw||raw.s!=='ok')return[];const keys=Object.keys(raw).filter(k=>Array.isArray(raw[k])),n=(raw.optionSymbol||[]).length,out=[];
    for(let i=0;i<n;i++){const row={};keys.forEach(k=>row[k]=raw[k][i]);out.push(row)}return out;
  }
  const state={chain:[],selected:null,strategy:'SELL_PUT',refreshTimer:null,positionsTimer:null,bulkRefreshing:false,lastBulkAt:0,apiMode:false,positions:new Map(),positionMode:false,events:[],eventsUpdated:null};
  async function token(){try{const r=await supabaseClient.auth.getSession();return r.data.session?.access_token||null}catch(e){return null}}
  async function api(params){
    const root=$('optionV2Root'),endpoint=root?.dataset.endpoint;if(!endpoint)throw new Error('尚未配置实时接口');
    const jwt=await token();if(!jwt)throw new Error('请先登录私有看板');
    const cacheKey=`optionApi:${JSON.stringify(params)}`,cached=JSON.parse(sessionStorage.getItem(cacheKey)||'null'),ttl=params.action==='quote'?60000:600000;
    if(cached&&Date.now()-cached.at<ttl)return cached.body;
    const u=new URL(endpoint);Object.entries(params).forEach(([k,v])=>v!==undefined&&u.searchParams.set(k,v));
    const res=await fetch(u,{headers:{Authorization:`Bearer ${jwt}`,apikey:global.SUPABASE_ANON_KEY||''},signal:AbortSignal.timeout(12000)});const body=await res.json();
    if(!res.ok){
      const upstream=body.error||body.errmsg||`接口错误 ${res.status}`;
      if(res.status===401)throw new Error(`Alpaca密钥无效或密钥类型不匹配：${upstream}`);
      if(res.status===403)throw new Error(`Alpaca拒绝访问，请检查账户的数据权限：${upstream}`);
      if(res.status===402)throw new Error(`当前行情套餐无权读取该数据：${upstream}`);
      if(res.status===429)throw new Error(`行情额度或并发已达上限：${upstream}`);
      throw new Error(upstream);
    }
    sessionStorage.setItem(cacheKey,JSON.stringify({body,at:Date.now()}));return body;
  }
  function setStatus(text,tone='warn'){$('optV2Status').textContent=text;$('optV2Status').className=`option-v2-status ${tone}`;if(tone==='bad')global.MAV?.toast(text,'bad')}
  function feedLabel(raw){return raw?.provider==='Alpaca'?'Alpaca Indicative参考行情':raw?.provider||'参考行情'}
  function todayIso(){const parts=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date()),v=Object.fromEntries(parts.map(x=>[x.type,x.value]));return `${v.year}-${v.month}-${v.day}`}
  function nextFriday(){const d=new Date(`${todayIso()}T12:00:00Z`);let add=(5-d.getUTCDay()+7)%7;if(add===0)add=7;d.setUTCDate(d.getUTCDate()+add);return d.toISOString().slice(0,10)}
  function inputs(){
    const expiry=$('optExpiryV2').value||$('manualExpiry').value||todayIso(),target=$('targetDate').value||nextFriday();
    return{strategy:state.strategy,spot:+$('manualSpot').value,strike:+$('manualStrike').value,premium:+$('manualPremium').value,qty:+$('optionQty').value,multiplier:+$('contractMultiplier').value,targetSpot:+$('targetSpot').value,iv:+$('manualIv').value/100,ivChange:+document.querySelector('[data-iv].active')?.dataset.iv||0,fee:+$('feePerContract').value,rate:+$('riskFreeRate').value/100,dividend:+$('dividendYield').value/100,dte:daysBetween(todayIso(),expiry),forwardDays:daysBetween(todayIso(),target),stockCost:+$('stockCost').value};
  }
  function render(){
    const p=inputs();if(!p.spot||!p.strike||!p.premium||!p.targetSpot)return;
    if(p.forwardDays>p.dte){$('scenarioAnswer').innerHTML='<strong>目标日期不能晚于期权到期日。</strong><div class="sub">请缩短目标日期，或在左侧选择更远的到期日。</div>';$('optionStats').innerHTML='';$('optionHeatmap').innerHTML='';return}
    const r=evaluate(p),direction=r.netPnl>=0?'预计盈利':'预计亏损';
    $('scenarioAnswer').innerHTML=`如果目标日正股为 <strong>${money(p.targetSpot)}</strong>，IV为 <strong>${pct(r.futureIv)}</strong>，预计每股期权价值 <strong>${money(r.optionPrice)}</strong>；${r.qty}张合约价值 <strong>${money(r.positionValue)}</strong>，${direction} <strong>${money(Math.abs(r.netPnl))}</strong>。<div class="sub">目标日剩余 ${r.remaining} DTE；结果已按 ${r.mult}×${r.qty} 计算并扣除双边估算费用。</div>`;
    const stats=[['目标日合约价值',money(r.positionValue),'整仓，不是每股'],['预计净盈亏',money(r.netPnl),r.returnOnCapital==null?'—':`资金回报 ${pct(r.returnOnCapital)}`],['最大盈利',Number.isFinite(r.maxProfit)?money(r.maxProfit):'无限','到期口径'],['最大亏损',Number.isFinite(r.maxLoss)?money(r.maxLoss):'无限','到期口径'],['盈亏平衡价',money(r.breakeven),'到期口径'],['资金占用',r.capital?money(r.capital):'依券商保证金','现金担保/成本'],['未来IV',pct(r.futureIv),'当前IV按相对比例变化'],['剩余期限',`${r.remaining}天`,'目标日期时']];
    $('optionStats').innerHTML=stats.map((x,i)=>`<div class="option-stat ${i===1?(r.netPnl>=0?'positive':'negative'):''}"><div class="k">${x[0]}</div><div class="v">${x[1]}</div><div class="s">${x[2]}</div></div>`).join('');
    renderHeatmap(p);
  }
  function renderHeatmap(base){
    const spots=[-.2,-.1,-.05,0,.05,.1,.2].map(x=>base.spot*(1+x)),ivs=[-.2,-.1,0,.1,.2];
    let html='<table><thead><tr><th>目标股价</th>'+ivs.map(v=>`<th>IV ${v===0?'不变':v>0?'+'+v*100+'%':v*100+'%'}</th>`).join('')+'</tr></thead><tbody>';
    spots.forEach(s=>{html+=`<tr><th>${money(s)}</th>`;ivs.forEach(v=>{const r=evaluate({...base,targetSpot:s,ivChange:v}),c=Math.abs(r.netPnl)<5?'heat-flat':r.netPnl>0?'heat-pos':'heat-neg';html+=`<td class="${c}">${money(r.netPnl)}</td>`});html+='</tr>'});
    $('optionHeatmap').innerHTML=html+'</tbody></table>';
  }
  function strategyChanged(value){state.strategy=value;document.querySelectorAll('[data-strategy]').forEach(b=>b.classList.toggle('active',b.dataset.strategy===value));const m=strategyMeta(value);$('chainSide').value=m.type;$('stockCostWrap').style.display=value==='COVERED_CALL'?'grid':'none';renderChain();render()}
  async function loadExpirations(){
    const symbol=$('optionSymbol').value.trim().toUpperCase();if(!symbol)return setStatus('请输入股票代码','bad');setStatus('正在读取到期日…','warn');
    try{const raw=await api({action:'expirations',symbol}),dates=raw.expirations||raw.expiration||[];const arr=Array.isArray(dates)?dates:[];$('optExpiryV2').innerHTML='<option value="">选择到期日</option>'+arr.map(d=>{const v=typeof d==='number'?new Date(d*1000).toISOString().slice(0,10):String(d).slice(0,10);return `<option value="${v}">${v}</option>`}).join('');if(!arr.length)throw new Error(`${symbol} 没有返回可用期权到期日`);state.apiMode=true;setStatus(`${feedLabel(raw)} · ${symbol} · ${arr.length}个到期日`,'good')}catch(e){state.apiMode=false;setStatus(`${e.message}；可使用手动报价模式`,'bad');$('manualPanel').classList.add('active')}
  }
  async function loadChain(){
    const symbol=$('optionSymbol').value.trim().toUpperCase(),expiration=$('optExpiryV2').value,side=$('chainSide').value;if(!symbol||!expiration)return;
    setStatus('正在读取期权链…','warn');try{const raw=await api({action:'chain',symbol,expiration,side}),rows=normalizeColumnar(raw);state.chain=rows.filter(x=>x.side===side||!x.side).sort((a,b)=>a.strike-b.strike);renderChain();setStatus(`${feedLabel(raw)} · ${state.chain.length}份合约`,'good')}catch(e){setStatus(e.message,'bad')}
  }
  function renderChain(){
    const tbody=$('optionChainBody');if(!tbody)return;const rows=state.chain.filter(x=>!x.side||x.side===$('chainSide').value);tbody.innerHTML=rows.length?rows.map((x,i)=>`<tr data-chain-index="${state.chain.indexOf(x)}"><td>${money(x.strike)}</td><td>${money(x.bid)}</td><td>${money(x.ask)}</td><td>${money(x.mid)}</td><td>${pct(x.iv)}</td><td>${Number.isFinite(x.delta)?Number(x.delta).toFixed(3):'—'}</td><td>${x.volume??'—'}</td><td>${x.openInterest??'—'}</td></tr>`).join(''):'<tr><td colspan="8" style="text-align:center">请选择到期日加载期权链，或展开手动报价</td></tr>';
    tbody.querySelectorAll('tr[data-chain-index]').forEach(tr=>tr.addEventListener('click',()=>selectContract(+tr.dataset.chainIndex,tr)));
  }
  function selectContract(i,tr){
    const x=state.chain[i];state.selected=x;document.querySelectorAll('#optionChainBody tr').forEach(r=>r.classList.remove('selected'));tr.classList.add('selected');
    state.positionMode=false;$('manualStrike').value=x.strike;$('manualSpot').value=x.underlyingPrice||$('manualSpot').value;$('manualIv').value=Number.isFinite(x.iv)?(x.iv*100).toFixed(2):$('manualIv').value;
    const basis=$('quoteBasis').value,v=x[basis]??x.mid??x.last??x.ask??x.bid;$('manualPremium').value=Number(v||0).toFixed(2);$('targetSpot').value=$('manualSpot').value;$('manualExpiry').value=$('optExpiryV2').value;
    $('selectedContract').textContent=`已选 ${x.optionSymbol||''}｜Strike ${money(x.strike)}｜Bid ${money(x.bid)} / Mid ${money(x.mid)} / Ask ${money(x.ask)}｜IV ${pct(x.iv)}｜Alpaca Indicative · ${x.updated?new Date(x.updated*1000).toLocaleString():'时间未知'}`;render();scheduleQuoteRefresh();
  }
  async function refreshQuote(){if(!state.selected?.optionSymbol||!state.apiMode||document.visibilityState==='hidden')return;try{const raw=await api({action:'quote',optionSymbol:state.selected.optionSymbol}),x=normalizeColumnar(raw)[0];if(!x)return;state.selected={...state.selected,...x};const basis=$('quoteBasis').value;$('manualPremium').value=Number(x[basis]??x.mid??x.last??0).toFixed(2);$('manualIv').value=Number.isFinite(x.iv)?(x.iv*100).toFixed(2):$('manualIv').value;setStatus(`报价已刷新 · ${new Date().toLocaleTimeString()}`,'good');render()}catch(e){setStatus(`刷新失败：${e.message}`,'bad')}}
  function scheduleQuoteRefresh(){clearInterval(state.refreshTimer);state.refreshTimer=setInterval(()=>{if(isUsRegularSession())refreshQuote()},15*60*1000);setStatus('Alpaca Indicative参考行情 · 常规交易时段每15分钟刷新；下单前请以IBKR Bid/Ask确认','warn')}
  function setPreset(kind,value){
    if(kind==='date'){if(value==='friday')$('targetDate').value=nextFriday();else{const d=new Date(`${todayIso()}T12:00:00Z`);d.setUTCDate(d.getUTCDate()+Number(value));$('targetDate').value=d.toISOString().slice(0,10)}}
    if(kind==='spot'){const s=+$('manualSpot').value,k=+$('manualStrike').value,p=+$('manualPremium').value;let v=s;if(value==='strike')v=k;else if(value==='breakeven')v=strategyMeta(state.strategy).type==='put'?k-p:k+p;else v=s*(1+Number(value));$('targetSpot').value=v.toFixed(2)}render();
  }
  function changeQty(d){$('optionQty').value=Math.max(1,+$('optionQty').value+d);render()}
  function bind(){
    if(!$('optionV2Root'))return;$('targetDate').value=nextFriday();
    if(!$('manualExpiry').value||$('manualExpiry').value<=todayIso()){const d=new Date(`${todayIso()}T12:00:00Z`);d.setUTCDate(d.getUTCDate()+45);$('manualExpiry').value=d.toISOString().slice(0,10)}
    document.querySelectorAll('[data-strategy]').forEach(b=>b.addEventListener('click',()=>strategyChanged(b.dataset.strategy)));
    document.querySelectorAll('[data-date-preset]').forEach(b=>b.addEventListener('click',()=>setPreset('date',b.dataset.datePreset)));
    document.querySelectorAll('[data-spot-preset]').forEach(b=>b.addEventListener('click',()=>setPreset('spot',b.dataset.spotPreset)));
    document.querySelectorAll('[data-iv]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('[data-iv]').forEach(x=>x.classList.remove('active'));b.classList.add('active');render()}));
    $('loadExpirations').addEventListener('click',loadExpirations);$('optExpiryV2').addEventListener('change',loadChain);$('chainSide').addEventListener('change',loadChain);$('manualToggle').addEventListener('click',()=>$('manualPanel').classList.toggle('active'));$('advancedToggle').addEventListener('click',()=>$('advancedPanel').classList.toggle('active'));$('qtyMinus').addEventListener('click',()=>changeQty(-1));$('qtyPlus').addEventListener('click',()=>changeQty(1));$('runScenario').addEventListener('click',render);
    ['manualSpot','manualStrike','manualPremium','manualIv','manualExpiry','targetDate','targetSpot','optionQty','feePerContract','stockCost','riskFreeRate','dividendYield'].forEach(id=>$(id)?.addEventListener('input',render));
    $('quoteBasis').addEventListener('change',()=>{if(state.selected){const x=state.selected,v=x[$('quoteBasis').value]??x.mid??x.last;$('manualPremium').value=Number(v||0).toFixed(2);render()}});strategyChanged('SELL_PUT');renderChain();
  }
  async function loadPrivatePositions(){
    const tbody=$('optionsTableBody');if(!tbody)return;
    tbody.innerHTML='<tr><td colspan="14"><div class="skeleton" style="height:42px;border-radius:8px">正在读取私有持仓</div></td></tr>';
    try{
      const {data:{session}}=await supabaseClient.auth.getSession();
      if(!session){tbody.innerHTML='<tr><td colspan="14" style="text-align:center;color:var(--muted)">请登录后查看私有期权持仓</td></tr>';state.positions.clear();clearInterval(state.positionsTimer);setAutoStatus('登录后启用持仓自动检查');renderRiskSummary();return}
      const {data,error}=await supabaseClient.from('options_positions').select('*').order('expiry');if(error)throw error;
      const rows=data||[],expiredOpen=rows.filter(x=>(!x.status||x.status==='open')&&rawDaysBetween(todayIso(),x.expiry)<0).map(x=>x.id);
      if(expiredOpen.length){const {error:updateError}=await supabaseClient.from('options_positions').update({status:'pending_settlement'}).in('id',expiredOpen);if(!updateError)rows.forEach(x=>{if(expiredOpen.includes(x.id))x.status='pending_settlement'})}
      const active=rows.filter(x=>!x.status||['open','pending_settlement'].includes(x.status));state.positions=new Map(active.map(x=>[String(x.id),x]));
      tbody.innerHTML=active.length?active.map(x=>{const cached=readCachedQuote(x.id),freshness=quoteFreshness(cached);return renderPositionRow(x,cached?.quote,freshness.label,freshness)}).join(''):'<tr><td colspan="14" style="text-align:center;color:var(--muted)">当前没有开放或待结算的期权持仓</td></tr>';
      renderRiskSummary();schedulePositionRefresh();setTimeout(()=>refreshAllPositions({onlyNeeded:true,reason:'登录后检查'}),250);
    }catch(e){tbody.innerHTML=`<tr><td colspan="14" style="text-align:center;color:var(--red)">持仓读取失败：${e.message}</td></tr>`;global.MAV?.toast(`持仓读取失败：${e.message}`,'bad')}
  }
  function occSymbol(position){
    const root=String(position.symbol||'').toUpperCase().replace(/[^A-Z0-9]/g,''),date=String(position.expiry||'').replaceAll('-','').slice(2),cp=String(position.opt_type||'put').toLowerCase()==='call'?'C':'P',strike=String(Math.round(Number(position.strike)*1000)).padStart(8,'0');
    return `${root}${date}${cp}${strike}`;
  }
  function positionMetrics(position,quote){
    const short=String(position.side).toLowerCase()==='short',qty=Math.max(1,Number(position.qty)||1),cost=Number(position.cost)||0,multiplier=Math.max(1,Number(position.multiplier)||MULTIPLIER);
    const bid=quoteNumber(quote.bid),ask=quoteNumber(quote.ask),mid=quoteNumber(quote.mid),last=quoteNumber(quote.last);
    const mark=short?(Number.isFinite(ask)?ask:Number.isFinite(mid)?mid:last):(Number.isFinite(bid)?bid:Number.isFinite(mid)?mid:last);
    const pnl=Number.isFinite(mark)?(short?cost-mark:mark-cost)*multiplier*qty:null;
    const base=cost*multiplier*qty,pnlPct=Number.isFinite(pnl)&&base>0?pnl/base:null,type=String(position.opt_type).toLowerCase();
    const breakeven=type==='put'?Number(position.strike)-cost:Number(position.strike)+cost;
    return{mark,pnl,pnlPct,breakeven,qty,short,multiplier};
  }
  function annualizedRoc(position,quote=null){
    const mode=String(position.collateral_mode||'').toLowerCase(),side=String(position.side||'').toLowerCase(),type=String(position.opt_type||'').toLowerCase();
    if(mode!=='cash_secured'||side!=='short'||type!=='put')return{value:null,label:'仅Cash-Secured Put'};
    if(!position.entry_date)return{value:null,label:'待补建仓日期'};
    const entryDte=rawDaysBetween(position.entry_date,position.expiry),qty=Math.max(1,Number(position.qty)||1),multiplier=Math.max(1,Number(position.multiplier)||MULTIPLIER),cost=Number(position.cost)||0,openFee=Math.max(0,Number(position.open_fee)||0);
    const netPremium=cost*multiplier*qty-openFee,securedCapital=Number(position.strike)*multiplier*qty-netPremium;
    if(entryDte<=0||netPremium<=0||securedCapital<=0)return{value:null,label:'建仓数据无效'};
    const value=netPremium/securedCapital*365/entryDte;
    const bid=quoteNumber(quote?.bid),ask=quoteNumber(quote?.ask),mid=quoteNumber(quote?.mid),delta=quoteNumber(quote?.delta),spot=quoteNumber(quote?.underlyingPrice),strike=Number(position.strike),dte=rawDaysBetween(todayIso(),position.expiry);
    const spread=Number.isFinite(bid)&&Number.isFinite(ask)&&Number.isFinite(mid)&&mid>0?(ask-bid)/mid:null,otm=Number.isFinite(spot)&&strike>0?spot/strike-1:null;
    const candidate=value>=.12&&value<=.25&&Number.isFinite(delta)&&Math.abs(delta)>=.10&&Math.abs(delta)<=.25&&dte>=21&&dte<=60&&otm>=.05&&spread!==null&&spread<=.10&&eventsBefore(position.expiry).length===0;
    const tone=value<.12?'roc-low':value<=.25?'roc-good':value<=.35?'roc-warn':'roc-hot';
    return{value,label:candidate?'效率候选':'年化估算',candidate,tone,entryDte,netPremium,securedCapital};
  }
  function eventsBefore(expiry){const start=new Date(`${todayIso()}T00:00:00`),end=new Date(`${expiry}T23:59:59`);return state.events.filter(x=>{const d=new Date(x.datetime);return d>=start&&d<=end})}
  function positionRisk(position,quote,freshness=null){
    const dte=rawDaysBetween(todayIso(),position.expiry),spot=quoteNumber(quote?.underlyingPrice),strike=Number(position.strike),type=String(position.opt_type).toLowerCase(),bid=quoteNumber(quote?.bid),ask=quoteNumber(quote?.ask),mid=quoteNumber(quote?.mid),spread=Number.isFinite(bid)&&Number.isFinite(ask)&&mid>0?(ask-bid)/mid:null;
    const itm=Number.isFinite(spot)?(type==='put'?spot<strike:spot>strike):null,distance=Number.isFinite(spot)&&strike>0?Math.abs(spot/strike-1):null;
    let level='unknown',label='等待有效报价';
    if(dte<0){level='l3';label='L3 已到期 · 待结算'}
    else if(freshness?.status==='stale'){level=dte<=7?'l3':'l2';label=`${level.toUpperCase()} 报价已过期 · 请刷新`}
    else if(dte<=7&&!Number.isFinite(spot)){level='l3';label='L3 临期但缺报价'}
    else if(dte<=7&&(itm===true||(distance!==null&&distance<=.01))){level='l3';label='L3 临期且近平值/实值'}
    else if(dte<=14&&(itm===true||(distance!==null&&distance<=.05))){level='l2';label='L2 接近行权风险区'}
    else if(spread!==null&&spread>.15){level='l2';label='L2 买卖价差偏大'}
    else if(Number.isFinite(spot)){level='l1';label='L1 暂未触发风险线'}
    const events=eventsBefore(position.expiry);
    if(events.length&&level==='l1'){level='l2';label=`L2 到期前含${[...new Set(events.map(x=>x.type))].join('/')}`}
    return{dte,spot,itm,distance,spread,level,label,events};
  }
  function renderRiskTodo(){
    const host=$('riskTodoList');if(!host)return;const items=[];
    document.querySelectorAll('.risk-alert.l2,.risk-alert.l3').forEach(x=>items.push({level:x.classList.contains('l3')?'l3':'l2',text:x.querySelector('strong')?.textContent||'市场宽度预警'}));
    state.positions.forEach(p=>{const cached=readCachedQuote(p.id),freshness=quoteFreshness(cached),risk=positionRisk(p,freshness.usable?cached?.quote:null,freshness);if(risk.level==='l2'||risk.level==='l3')items.push({level:risk.level,text:`${p.symbol} ${p.expiry}：${risk.label.replace(/^L[23]\s*/, '')}`})});
    host.innerHTML=items.length?items.map(x=>`<div class="risk-todo-item ${x.level}"><span>${x.level.toUpperCase()}</span><strong>${x.text}</strong></div>`).join(''):'<div class="risk-todo-empty">当前没有触发 L2/L3 待办；仍需在下单前核对券商报价与保证金。</div>';
  }
  function riskEscalationClass(id,level){
    if(typeof sessionStorage==='undefined')return'';const rank={unknown:0,l1:1,l2:2,l3:3},key=`optionRiskLevel:${id}`,previous=sessionStorage.getItem(key);sessionStorage.setItem(key,level);return previous&&rank[level]>rank[previous]?' risk-escalated':'';
  }
  function renderRiskSummary(){
    const host=$('optionRiskSummary');if(!host)return;
    const positions=[...state.positions.values()].filter(x=>!x.status||['open','pending_settlement'].includes(x.status));let obligation=0,due=0,liveCovered=0,referenceCovered=0,eventCount=0;
    positions.forEach(p=>{const mult=Math.max(1,Number(p.multiplier)||MULTIPLIER),qty=Math.max(1,Number(p.qty)||1);if(String(p.side).toLowerCase()==='short'&&String(p.opt_type).toLowerCase()==='put')obligation+=Number(p.strike)*mult*qty;const cached=readCachedQuote(p.id),freshness=quoteFreshness(cached);if(freshness.live&&freshness.usable)liveCovered++;else if(freshness.status==='closed')referenceCovered++;const risk=positionRisk(p,freshness.usable?cached?.quote:null,freshness);if(risk.dte<=14)due++;if(risk.events.length)eventCount++});
    const stamp=state.eventsUpdated?new Date(state.eventsUpdated).toLocaleString():'未读取';
    const coverageText=isUsRegularSession()?`${liveCovered}/${positions.length}`:`${referenceCovered}/${positions.length}`;
    const coverageNote=isUsRegularSession()?'美股常规时段有效Alpaca参考报价':`休市参考覆盖；实时覆盖 ${liveCovered}/${positions.length}`;
    host.innerHTML=`<div class="risk-card"><div class="k">理论行权资金</div><div class="v">${money(obligation)}</div><div class="s">Short Put行权价×乘数×张数；不是IBKR实际保证金</div></div><div class="risk-card"><div class="k">14天内到期</div><div class="v">${due} 笔</div><div class="s">临期仓位需结合虚实值和价差检查</div></div><div class="risk-card"><div class="k">${isUsRegularSession()?'实时行情覆盖':'休市参考覆盖'}</div><div class="v">${coverageText}</div><div class="s">${coverageNote}</div></div><div class="risk-card"><div class="k">到期前宏观事件</div><div class="v">${eventCount} 笔</div><div class="s">FOMC/CPI官方日历更新：${stamp}</div></div>`;
    renderRiskTodo();
  }
  function renderPositionRow(x,quote=null,message='点击“刷新”读取行情',freshness=null){
    const riskQuote=freshness&&!freshness.usable?null:quote,risk=positionRisk(x,riskQuote,freshness),dte=risk.dte,m=quote?positionMetrics(x,quote):null,underlying=quoteNumber(quote?.underlyingPrice),iv=quoteNumber(quote?.iv),delta=quoteNumber(quote?.delta);
    const isReference=freshness&&['closed','stale'].includes(freshness.status),pnlClass=isReference?'quote-reference':m&&Number.isFinite(m.pnl)?(m.pnl>=0?'pos-text':'neg-text'):'',distance=Number.isFinite(underlying)?(underlying/m.breakeven-1):null;
    const eventText=risk.events.length?[...new Set(risk.events.map(e=>e.type))].join('/'):'无已知宏观事件',roc=annualizedRoc(x,quote),rocHtml=Number.isFinite(roc.value)?`<span class="roc-chip ${roc.tone}" title="净权利金 ${money(roc.netPremium)}；现金担保资本 ${money(roc.securedCapital)}；建仓DTE ${roc.entryDte}">${pct(roc.value)}${roc.candidate?' · 候选':''}</span>`:`<span class="roc-missing">— ${roc.label}</span>`;
    const rocButton=(!x.entry_date||!x.collateral_mode)?` <button onclick="OptionV2.completeRocFields('${x.id}')" title="补录建仓日期与担保方式">补ROC</button>`:'';
    const quoteState=freshness?`<div class="quote-state ${freshness.tone}">${freshness.label}</div>`:'';
    const pnlPrefix=isReference&&m&&Number.isFinite(m.pnl)?'约 ':'';
    return `<tr id="opt-row-${x.id}"><td>${x.symbol} <span class="badge neutral">${x.side} ${x.opt_type}</span></td><td>$${Number(x.strike).toFixed(2)}</td><td>${x.expiry} (${dte}d)</td><td>$${Number(x.cost).toFixed(2)} / 每股</td><td>${m&&Number.isFinite(m.mark)?money(m.mark):'—'}${quoteState}</td><td class="${m?pnlClass:''}" title="${isReference?'基于上一有效报价，仅供参考':''}">${m&&Number.isFinite(m.pnl)?pnlPrefix+money(m.pnl):message}</td><td class="${m?pnlClass:''}">${m&&Number.isFinite(m.pnlPct)?pnlPrefix+pct(m.pnlPct):'—'}</td><td>$${Number(m?.breakeven??(String(x.opt_type).toLowerCase()==='put'?Number(x.strike)-Number(x.cost):Number(x.strike)+Number(x.cost))).toFixed(2)}</td><td>${Number.isFinite(underlying)?money(underlying):'—'}</td><td>${Number.isFinite(distance)?pct(distance):'—'}</td><td>${rocHtml}</td><td><span class="risk-chip ${risk.level}${riskEscalationClass(x.id,risk.level)}" title="${eventText}">${risk.label}</span></td><td>${Number.isFinite(iv)?pct(iv):'—'} / ${Number.isFinite(delta)?delta.toFixed(3):'—'}</td><td><button onclick="OptionV2.refreshPosition('${x.id}')" title="刷新报价">↻</button> <button onclick="OptionV2.openPositionScenario('${x.id}')" title="按真实成本推演">推演</button>${rocButton} <button onclick="deleteOptionPosition(${x.id})" title="删除">🗑️</button></td></tr>`;
  }
  async function completeRocFields(id){
    const p=state.positions.get(String(id));if(!p)return;const entry=prompt(`请输入 ${p.symbol} 的真实建仓日期（YYYY-MM-DD）`,p.entry_date||'');if(entry===null)return;
    if(!/^\d{4}-\d{2}-\d{2}$/.test(entry)||entry>String(p.expiry)){alert('日期格式无效，或建仓日期晚于到期日。');return}
    const suggested=String(p.side).toLowerCase()==='short'&&String(p.opt_type).toLowerCase()==='put'?'cash_secured':String(p.side).toLowerCase()==='long'?'debit':'covered';
    const mode=prompt('请输入担保方式：cash_secured / naked / covered / debit',p.collateral_mode||suggested);if(mode===null)return;
    if(!['cash_secured','naked','covered','debit'].includes(mode)){alert('担保方式无效。');return}
    const {data,error}=await supabaseClient.from('options_positions').update({entry_date:entry,collateral_mode:mode}).eq('id',id).select().single();
    if(error){global.MAV?.toast(`ROC字段补录失败：${error.message}`,'bad');return}state.positions.set(String(id),data);await loadPrivatePositions();global.MAV?.toast(`${p.symbol} ROC字段已补录`,'good');
  }
  async function refreshPosition(id,{silent=false}={}){
    const position=state.positions.get(String(id));if(!position)return;
    const row=$(`opt-row-${id}`);if(row&&!silent)row.innerHTML=`<td colspan="14" style="text-align:center;color:var(--muted)"><div class="skeleton" style="height:32px;border-radius:7px">正在读取 ${position.symbol} 合约报价…</div></td>`;
    try{
      const raw=await api({action:'quote',optionSymbol:occSymbol(position)}),quote=normalizeColumnar(raw)[0];if(!quote)throw new Error('行情源没有返回该合约');
      const cached={quote,at:Date.now()};sessionStorage.setItem(`optionQuote:${id}`,JSON.stringify(cached));
      if(row)row.outerHTML=renderPositionRow(position,quote,quoteFreshness(cached).label,quoteFreshness(cached));
      renderRiskSummary();return true;
    }catch(e){
      const cached=readCachedQuote(id),freshness=quoteFreshness(cached);
      if(row)row.outerHTML=renderPositionRow(position,cached?.quote,cached?freshness.label:e.message,freshness);
      renderRiskSummary();return false;
    }
  }
  function setAutoStatus(text,tone=''){
    const node=$('optionAutoStatus');if(node){node.textContent=text;node.className=`option-auto-status ${tone}`}
    const button=$('refreshAllOptions');if(button)button.disabled=state.bulkRefreshing;
  }
  async function refreshAllPositions({force=false,onlyNeeded=false,reason='手动'}={}){
    if(state.bulkRefreshing||document.visibilityState==='hidden'||!state.positions.size)return;
    const entries=[...state.positions.entries()].filter(([id])=>{if(force)return true;const freshness=quoteFreshness(readCachedQuote(id));return onlyNeeded?freshness.status==='unavailable'||(isUsRegularSession()&&!freshness.fresh):!freshness.fresh});
    if(!entries.length){setAutoStatus(isUsRegularSession()?'持仓报价仍在有效期':'休市 · 保留上次有效报价','good');renderRiskSummary();return}
    state.bulkRefreshing=true;setAutoStatus(`${reason}：正在刷新 0/${entries.length}`,'warn');let success=0;
    for(let i=0;i<entries.length;i++){
      const [id]=entries[i];setAutoStatus(`${reason}：正在刷新 ${i+1}/${entries.length}`,'warn');if(await refreshPosition(id,{silent:true}))success++;if(i<entries.length-1)await new Promise(resolve=>setTimeout(resolve,450));
    }
    state.lastBulkAt=Date.now();state.bulkRefreshing=false;setAutoStatus(`完成 ${success}/${entries.length} · ${new Date().toLocaleTimeString()}`,success===entries.length?'good':'warn');renderRiskSummary();
  }
  function schedulePositionRefresh(){
    clearInterval(state.positionsTimer);state.positionsTimer=setInterval(()=>{if(document.visibilityState==='visible'&&isUsRegularSession())refreshAllPositions({onlyNeeded:true,reason:'15分钟自动检查'})},POSITION_REFRESH_MS);
  }
  async function openPositionScenario(id){
    const p=state.positions.get(String(id));if(!p)return;
    state.positionMode=true;state.strategy=`${String(p.side).toUpperCase()==='SHORT'?'SELL':'BUY'}_${String(p.opt_type).toUpperCase()}`;if(state.strategy==='SELL_CALL')state.strategy='NAKED_CALL';
    const nav=document.querySelector('[onclick*="tab-sandbox"]');if(typeof global.switchTab==='function')global.switchTab('tab-sandbox',nav);
    $('optionSymbol').value=p.symbol;$('manualStrike').value=Number(p.strike).toFixed(2);$('manualPremium').value=Number(p.cost).toFixed(2);$('manualExpiry').value=p.expiry;$('optionQty').value=p.qty||1;$('contractMultiplier').value=p.multiplier||100;
    strategyChanged(state.strategy);$('manualPanel').classList.add('active');$('selectedContract').textContent=`持仓推演模式：${p.symbol} ${p.side} ${p.opt_type}｜真实建仓成本 ${money(Number(p.cost))}/股｜${p.qty||1}张 × ${p.multiplier||100}`;
    const cached=readCachedQuote(id),freshness=quoteFreshness(cached);if(cached?.quote){const q=cached.quote;$('manualSpot').value=q.underlyingPrice||$('manualSpot').value;$('manualIv').value=Number.isFinite(q.iv)?(q.iv*100).toFixed(2):$('manualIv').value;if(!freshness.usable)global.MAV?.toast(`${p.symbol} 缓存报价已过期，推演前请刷新或手工确认`,'warn')}
    $('targetSpot').value=$('manualSpot').value;render();
  }
  function setMarketEvents(events,updatedAt){state.events=Array.isArray(events)?events:[];state.eventsUpdated=updatedAt||null;const tbody=$('optionsTableBody');if(tbody&&state.positions.size)tbody.innerHTML=[...state.positions.values()].map(p=>{const cached=readCachedQuote(p.id),freshness=quoteFreshness(cached);return renderPositionRow(p,cached?.quote,freshness.label,freshness)}).join('');renderRiskSummary()}
  global.OptionV2={bsPrice,evaluate,normalizeColumnar,loadPrivatePositions,refreshQuote,refreshPosition,refreshAllPositions,openPositionScenario,completeRocFields,occSymbol,positionMetrics,annualizedRoc,positionRisk,quoteFreshness,isUsRegularSession,setMarketEvents};
  if(typeof document!=='undefined'){
    document.addEventListener('DOMContentLoaded',()=>{bind();$('refreshAllOptions')?.addEventListener('click',()=>refreshAllPositions({force:true,reason:'手动刷新'}))});
    document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&Date.now()-state.lastBulkAt>=POSITION_REFRESH_MS)refreshAllPositions({onlyNeeded:true,reason:'返回页面检查'})});
  }
})(typeof window!=='undefined'?window:globalThis);
