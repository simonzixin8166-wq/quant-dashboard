(function(global){
  'use strict';
  const ENDPOINT='https://rhielbkvhgqbthcgztci.supabase.co/functions/v1/options-market';
  const FILTERS={growth:{dteMin:365,dteMax:900,deltaMin:.50,deltaMax:.60},replacement:{dteMin:540,dteMax:900,deltaMin:.70,deltaMax:.85}};
  const state={symbol:'',mode:'growth',expirations:[]};
  const finite=value=>value!==null&&value!==undefined&&value!==''&&Number.isFinite(Number(value));
  const number=value=>finite(value)?Number(value):null;
  const escape=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const dte=(expiry,now=new Date())=>Math.max(0,Math.ceil((new Date(`${expiry}T20:00:00Z`)-now)/86400000));
  function normalizeColumnar(raw){
    if(!raw||raw.s!=='ok')return[];
    const keys=Object.keys(raw).filter(key=>Array.isArray(raw[key])),length=(raw.optionSymbol||[]).length,rows=[];
    for(let i=0;i<length;i++){const row={};keys.forEach(key=>row[key]=raw[key][i]);rows.push(row)}
    return rows;
  }
  function filterContracts(rows,mode='growth',now=new Date()){
    const rule=FILTERS[mode]||FILTERS.growth;
    return (rows||[]).map(row=>{
      const bid=number(row.bid),ask=number(row.ask),mid=number(row.mid)??(bid!==null&&ask!==null?(bid+ask)/2:null),delta=Math.abs(number(row.delta)??NaN);
      const spread=bid!==null&&ask!==null&&mid>0?(ask-bid)/mid:null;
      return {...row,bid,ask,mid,delta,spread,dte:dte(row.expiration,now)};
    }).filter(row=>row.dte>=rule.dteMin&&row.dte<=rule.dteMax&&Number.isFinite(row.delta)&&row.delta>=rule.deltaMin&&row.delta<=rule.deltaMax&&row.bid!==null&&row.ask!==null&&row.bid>0&&row.ask>=row.bid&&row.spread!==null&&row.spread<=.15)
      .sort((a,b)=>Math.abs(a.delta-(rule.deltaMin+rule.deltaMax)/2)-Math.abs(b.delta-(rule.deltaMin+rule.deltaMax)/2)||a.spread-b.spread).slice(0,12);
  }
  async function accessToken(){
    try{return (await global.mavSupabase?.auth?.getSession())?.data?.session?.access_token||null}catch(_error){return null}
  }
  async function api(params){
    const jwt=await accessToken();if(!jwt)throw new Error('请先登录私有看板');
    const endpoint=document.getElementById('optionV2Root')?.dataset.endpoint||ENDPOINT;
    const url=new URL(endpoint);Object.entries(params).forEach(([key,value])=>url.searchParams.set(key,value));
    const response=await fetch(url,{headers:{Authorization:`Bearer ${jwt}`,apikey:global.SUPABASE_ANON_KEY||''},signal:AbortSignal.timeout(15000)});
    const body=await response.json();if(!response.ok)throw new Error(body.error||`行情接口错误 ${response.status}`);return body;
  }
  function status(text,tone=''){
    const node=document.getElementById('leapsContractStatus');if(node){node.textContent=text;node.dataset.tone=tone}
  }
  function renderRows(raw){
    const body=document.getElementById('leapsContractBody');if(!body)return;
    const rows=filterContracts(normalizeColumnar(raw),state.mode,new Date());
    if(!rows.length){body.innerHTML='<tr><td colspan="7">当前到期日没有满足Delta与价差门槛的合约</td></tr>';status('未找到候选；可切换筛选方式或到期日。','warn');return}
    body.innerHTML=rows.map(row=>`<tr><td>${escape(row.expiration)}<small>${row.dte} DTE</small></td><td><b>$${Number(row.strike).toFixed(2)}</b></td><td>$${row.bid.toFixed(2)} / $${row.ask.toFixed(2)}</td><td>$${row.mid.toFixed(2)}</td><td><b>${row.delta.toFixed(3)}</b></td><td>${finite(row.iv)?(Number(row.iv)*100).toFixed(1)+'%':'—'}</td><td class="${row.spread<=.10?'spread-good':'spread-warn'}">${(row.spread*100).toFixed(1)}%</td></tr>`).join('');
    status(`已筛出 ${rows.length} 个候选；价差≤10%优先，10%–15%仅作谨慎参考。`,'good');
  }
  async function loadChain(){
    const expiry=document.getElementById('leapsExpiry')?.value;if(!state.symbol||!expiry)return;
    status(`正在读取 ${state.symbol} ${expiry} Call链…`);
    const body=document.getElementById('leapsContractBody');if(body)body.innerHTML='<tr><td colspan="7">读取中…</td></tr>';
    try{renderRows(await api({action:'chain',symbol:state.symbol,expiration:expiry,side:'call'}))}catch(error){if(body)body.innerHTML='<tr><td colspan="7">暂时无法读取候选合约</td></tr>';status(error.message,'bad')}
  }
  async function populateExpirations(symbol){
    state.symbol=symbol;state.mode=document.getElementById('leapsMode')?.value||'growth';
    const panel=document.getElementById('leapsContractPanel'),title=document.getElementById('leapsContractTitle'),select=document.getElementById('leapsExpiry');
    if(panel)panel.hidden=false;if(title)title.textContent=`${symbol} LEAPS 候选合约`;status(`正在读取 ${symbol} 到期日…`);
    panel?.scrollIntoView({behavior:'smooth',block:'nearest'});
    try{
      const raw=await api({action:'expirations',symbol}),rule=FILTERS[state.mode],now=new Date();
      state.expirations=(raw.expirations||[]).filter(expiry=>{const days=dte(expiry,now);return days>=rule.dteMin&&days<=rule.dteMax});
      if(!select)return;select.innerHTML=state.expirations.map(expiry=>`<option value="${escape(expiry)}">${escape(expiry)} · ${dte(expiry,now)} DTE</option>`).join('');
      if(!state.expirations.length){select.innerHTML='<option value="">无符合期限的到期日</option>';status('当前没有365–900天范围内的到期日。','warn');return}
      await loadChain();
    }catch(error){status(error.message,'bad')}
  }
  function bind(){
    document.querySelectorAll('[data-leaps-symbol]').forEach(button=>button.addEventListener('click',()=>populateExpirations(button.dataset.leapsSymbol)));
    document.getElementById('leapsExpiry')?.addEventListener('change',loadChain);
    document.getElementById('leapsReload')?.addEventListener('click',loadChain);
    document.getElementById('leapsMode')?.addEventListener('change',event=>{state.mode=event.target.value;if(state.symbol)populateExpirations(state.symbol)});
  }
  global.OpportunityRadar={FILTERS,normalizeColumnar,filterContracts,populateExpirations,loadChain};
  if(typeof document!=='undefined'){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind()}
  if(typeof module!=='undefined'&&module.exports)module.exports={FILTERS,normalizeColumnar,filterContracts,dte};
})(typeof window!=='undefined'?window:globalThis);
