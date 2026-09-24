(function(global){
  'use strict';
  const endpoint='https://rhielbkvhgqbthcgztci.supabase.co/functions/v1/stock-market';
  const DAILY_CACHE_KEY='mav-stock-daily-v1';
  const state={items:[],quotes:{},daily:{},dailyPhase:'',timer:null,loading:false};
  const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const num=value=>Number.isFinite(Number(value))?Number(value):null;
  const money=value=>num(value)===null?'—':`$${Number(value).toFixed(2)}`;
  const pct=value=>num(value)===null?'—':`${Number(value)>=0?'+':''}${(Number(value)*100).toFixed(2)}%`;

  function nyParts(){
    const parts=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',weekday:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date());
    return Object.fromEntries(parts.map(x=>[x.type,x.value]));
  }
  function sessionOpen(){const v=nyParts(),m=Number(v.hour)*60+Number(v.minute);return !['Sat','Sun'].includes(v.weekday)&&m>=570&&m<960}
  function dailyPhase(){const v=nyParts(),m=Number(v.hour)*60+Number(v.minute),date=`${v.year}-${v.month}-${v.day}`;return `${date}:${!['Sat','Sun'].includes(v.weekday)&&m>=965?'post-close':'carry'}`}
  function combined(symbol){return{...(state.daily[symbol]||{}),...(state.quotes[symbol]||{})}}

  async function authHeaders(){
    const {data:{session}}=await supabaseClient.auth.getSession();
    if(!session)throw new Error('请先登录私有看板');
    return{Authorization:`Bearer ${session.access_token}`,apikey:global.SUPABASE_ANON_KEY};
  }
  async function fetchMarket(symbols,scope){
    if(!symbols.length)return{};
    const headers=await authHeaders(),chunks=[];
    for(let i=0;i<symbols.length;i+=25)chunks.push(symbols.slice(i,i+25));
    const groups=await Promise.all(chunks.map(async chunk=>{
      const response=await fetch(`${endpoint}?symbols=${encodeURIComponent(chunk.join(','))}&scope=${scope}&t=${Date.now()}`,{headers,cache:'no-store',signal:AbortSignal.timeout(15000)});
      const body=await response.json();
      if(!response.ok||body.s!=='ok')throw new Error(body.error||`HTTP ${response.status}`);
      return body.rows||{};
    }));
    return Object.assign({},...groups);
  }
  function loadDailyCache(){
    try{
      const cached=JSON.parse(localStorage.getItem(DAILY_CACHE_KEY)||'null');
      if(cached&&cached.rows&&typeof cached.rows==='object'){state.daily=cached.rows;state.dailyPhase=cached.phase||'';}
    }catch{localStorage.removeItem(DAILY_CACHE_KEY)}
  }
  function saveDailyCache(){
    try{localStorage.setItem(DAILY_CACHE_KEY,JSON.stringify({phase:state.dailyPhase,rows:state.daily,savedAt:new Date().toISOString()}))}catch{}
  }
  async function ensureDaily(symbols,{force=false}={}){
    const phase=dailyPhase();
    const missing=symbols.filter(symbol=>!state.daily[symbol]||!state.daily[symbol].dailyAsOf);
    const requested=force||state.dailyPhase!==phase?symbols:missing;
    if(!requested.length)return;
    const rows=await fetchMarket(requested,'daily');
    state.daily={...state.daily,...rows};
    state.dailyPhase=phase;
    saveDailyCache();
  }

  function statusOf(q,target){
    const price=num(q?.price),rsi=num(q?.rsi),dist=num(q?.dist200),t=num(target);
    if(price!==null&&t!==null&&t>0){if(price<=t)return['triggered','已触发'];if(price/t-1<=.05)return['near','接近策略价']}
    if(rsi!==null&&rsi<35)return['oversold','超卖观察'];
    if(dist!==null&&dist<-.10)return['weak','趋势偏弱'];
    if((rsi!==null&&rsi>70)||(dist!==null&&dist>.25))return['hot','过热'];
    return['normal','正常观察'];
  }
  function rowHtml(item,index){
    const symbol=String(item.symbol).toUpperCase(),q=combined(symbol),price=num(q.price),chg=num(q.changePct),dd=num(q.ytdDrawdown),rsi=num(q.rsi),dist=num(q.dist200),[status,label]=statusOf(q,null),history=Number(q.historyDays)||0;
    const actions=isAdmin?`<div class="watchlist-actions"><button onclick="StockWatchlist.openEdit('${esc(symbol)}')">修改</button><button class="danger" onclick="StockWatchlist.remove('${esc(symbol)}')">删除个股</button></div>`:'';
    return `<tr data-stock-row data-status="${status}" data-target-distance="999" data-drawdown="${dd===null?0:Math.abs(dd)}" data-rsi="${rsi===null?999:rsi}" data-dist200="${dist===null?0:dist}" data-default-order="${index}"><td class="stock-identity"><div class="stock-name">${esc(item.display_name||symbol)}</div><div class="stock-symbol">${esc(symbol)}</div><details class="stock-details"><summary>行情详情</summary><div>盘中开 ${money(q.open)} · 高 ${money(q.high)} · 低 ${money(q.low)}<br>YTD高点 ${money(q.ytdHigh)} · 完整日线截至 ${esc(q.dailyAsOf||'等待数据')}<br>${esc(q.quoteSource||'等待盘中行情')} · ${esc(q.dailySource||'等待收盘指标')} · 有效历史 ${history} 日</div></details>${actions}</td><td data-label="最新价 / 涨跌"><b id="close-${esc(symbol)}">${money(price)}</b><small id="chg-${esc(symbol)}" class="${chg!==null&&chg>=0?'pos-text':'neg-text'}">${pct(chg)}</small></td><td data-label="YTD回撤" class="neg-text fw-bold">${pct(dd)}</td><td data-label="RSI">${rsi===null?'—':rsi.toFixed(2)}</td><td data-label="距200MA" class="${dist!==null&&dist<0?'neg-text':''}">${pct(dist)}</td><td data-label="策略价 / 距离" id="target-cell-${esc(symbol)}"><b id="target-${esc(symbol)}">—</b><small id="target-gap-${esc(symbol)}">等待策略数据</small></td><td data-label="状态"><span id="stock-status-${esc(symbol)}" class="stock-status ${status}">${label}</span><span id="action-${esc(symbol)}"></span></td></tr>`;
  }
  function render(){
    const body=document.getElementById('stocksTableBody');if(!body)return;
    body.innerHTML=state.items.length?state.items.map(rowHtml).join(''):'<tr><td colspan="7" class="stock-watch-empty">观察池为空，点击“新增个股”开始添加。</td></tr>';
    global.StockDecision?.sort('priority');
    global.fetchAndRenderTargets?.();
    const stamp=document.getElementById('stockWatchStatus');
    if(stamp)stamp.textContent=`${state.items.length}只 · ${sessionOpen()?'价格盘中5分钟更新':'休市保留最近报价'} · 指标${Object.keys(state.daily).length?'按完整收盘日线':'等待日线'} · ${new Date().toLocaleTimeString()}`;
  }
  async function load(){
    if(state.loading)return;state.loading=true;
    try{
      const {data:{session}}=await supabaseClient.auth.getSession();if(!session)return;
      const {data,error}=await supabaseClient.from('stock_watchlist').select('*').order('sort_order').order('symbol');if(error)throw error;
      state.items=data||[];
      loadDailyCache();
      const symbols=state.items.map(x=>x.symbol);
      const [quotes]=await Promise.all([fetchMarket(symbols,'quote'),ensureDaily(symbols)]);
      state.quotes=quotes;
      render();schedule();
    }catch(error){global.MAV?.toast(`观察池读取失败：${error.message}。请确认已执行V3.4迁移并部署stock-market。`,'bad')}
    finally{state.loading=false}
  }
  async function refresh(){
    if(!state.items.length)return;
    try{
      const symbols=state.items.map(x=>x.symbol);
      const [quotes]=await Promise.all([fetchMarket(symbols,'quote'),ensureDaily(symbols)]);
      state.quotes={...state.quotes,...quotes};render();
    }catch(error){global.MAV?.toast(`个股行情刷新失败：${error.message}`,'warn')}
    finally{schedule()}
  }
  function schedule(){clearTimeout(state.timer);state.timer=setTimeout(()=>{if(document.visibilityState==='visible')refresh();else schedule()},sessionOpen()?300000:1800000)}

  function openAdd(){
    if(!isAdmin){alert('请先使用主理人账户登录。');return}
    document.getElementById('watchOriginalSymbol').value='';document.getElementById('watchSymbol').disabled=false;document.getElementById('watchSymbol').value='';document.getElementById('watchName').value='';document.getElementById('watchTarget').value='';document.getElementById('stockWatchModalTitle').textContent='新增观察个股';document.getElementById('stockWatchModal').style.display='grid';
  }
  function openEdit(symbol){
    if(!isAdmin)return;const item=state.items.find(x=>x.symbol===symbol);if(!item)return;
    document.getElementById('watchOriginalSymbol').value=symbol;document.getElementById('watchSymbol').value=symbol;document.getElementById('watchSymbol').disabled=true;document.getElementById('watchName').value=item.display_name||symbol;document.getElementById('watchTarget').value='';document.getElementById('stockWatchModalTitle').textContent='修改观察标的';document.getElementById('stockWatchModal').style.display='grid';
  }
  function close(){document.getElementById('stockWatchModal').style.display='none';document.getElementById('watchSymbol').disabled=false}
  async function save(){
    const original=document.getElementById('watchOriginalSymbol').value,symbol=document.getElementById('watchSymbol').value.trim().toUpperCase(),name=document.getElementById('watchName').value.trim()||symbol,target=num(document.getElementById('watchTarget').value);
    if(!/^[A-Z0-9.-]{1,12}$/.test(symbol)){alert('请输入有效的美股代码，例如 AAPL、BRK.B。');return}
    try{
      if(!original){
        const [quote,daily]=await Promise.all([fetchMarket([symbol],'quote'),fetchMarket([symbol],'daily')]);
        if(!quote[symbol]||num(quote[symbol].price)===null)throw new Error('行情源未识别该代码，请核对后重试');
        state.quotes[symbol]=quote[symbol];state.daily[symbol]=daily[symbol]||{};state.dailyPhase=dailyPhase();saveDailyCache();
      }
      const payload={symbol,display_name:name,sort_order:original?(state.items.find(x=>x.symbol===symbol)?.sort_order||100):Math.max(0,...state.items.map(x=>Number(x.sort_order)||0))+10};
      const {error}=await supabaseClient.from('stock_watchlist').upsert(payload);if(error)throw error;
      if(target!==null&&target>0){const {error:targetError}=await supabaseClient.from('stock_targets').upsert({symbol,target_price:target});if(targetError)throw targetError}
      close();await load();global.MAV?.toast(original?'观察标的已修改':'个股已加入观察池，行情和收盘指标已载入','good');
    }catch(error){alert(`保存失败：${error.message}`)}
  }
  async function remove(symbol){
    if(!isAdmin)return;
    if(!confirm(`从观察池删除 ${symbol}？\n\n只删除观察记录和策略参考价，不影响期权持仓或券商账户。`))return;
    const typed=prompt(`输入 ${symbol} 确认删除该个股`);if(typed!==symbol)return;
    const {error}=await supabaseClient.from('stock_watchlist').delete().eq('symbol',symbol);if(error){alert(`删除失败：${error.message}`);return}
    await supabaseClient.from('stock_targets').delete().eq('symbol',symbol);
    state.items=state.items.filter(x=>x.symbol!==symbol);delete state.quotes[symbol];delete state.daily[symbol];saveDailyCache();render();global.MAV?.toast(`${symbol} 已从观察池删除`,'good');
  }
  global.StockWatchlist={load,refresh,openAdd,openEdit,close,save,remove};
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&state.items.length)refresh()});
})(window);
