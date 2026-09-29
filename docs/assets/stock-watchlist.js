(function(global){
  'use strict';
  const endpoint='https://rhielbkvhgqbthcgztci.supabase.co/functions/v1/stock-market';
  const DAILY_CACHE_KEY='mav-stock-daily-v1';
  const state={items:[],quotes:{},daily:{},research:{},researchReady:true,dailyPhase:'',timer:null,loading:false};
  const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const num=value=>Number.isFinite(Number(value))?Number(value):null;
  const money=value=>num(value)===null?'—':`$${Number(value).toFixed(2)}`;
  const pct=value=>num(value)===null?'—':`${Number(value)>=0?'+':''}${(Number(value)*100).toFixed(2)}%`;
  const trendZone=score=>{score=num(score);if(score===null)return '数据不足';if(score>=75)return '强势高位';if(score>=50)return '上升确认';if(score>=20)return '转强区';if(score>-20)return '震荡区';if(score>-60)return '弱势区';return '风险区'};
  const trendStage=state=>({二次启动:'↗ 回踩后重新转强',高位钝化:'→ 强势但上涨变慢',趋势退潮:'↘ 分数仍高但正在转弱',趋势启动:'↗ 趋势刚转强',趋势延续:'↗ 趋势继续增强',修复中:'↗ 弱势开始修复',趋势恶化:'↘ 弱势继续恶化',震荡观察:'→ 方向仍不清晰'})[state]||state||'等待数据';

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
  function plainGuide(q,tp){
    const score=Number.isFinite(Number(tp?.score))?Number(tp.score):null,rsi=num(q?.rsi),dist=num(q?.dist200);
    if(score!==null&&score>=75)return '趋势很强但位置可能不低。已有研究论点可继续跟踪；没有论点时不要只因高分追涨，优先等待价格与基本面再次确认。';
    if(score!==null&&score>=50)return '趋势处于上升确认区。先看投资论点是否成立，再把Trend Pulse当第二层确认，不把它单独当买入按钮。';
    if(score!==null&&score<20)return '趋势证据偏弱或仍在震荡。优先确认基本面论点、催化剂和失效条件，技术指标暂不提供强确认。';
    if(rsi!==null&&rsi<35)return '短线可能偏超卖，但超卖不等于见底。先检查下跌原因是否破坏原来的投资论点。';
    if(dist!==null&&dist<-.10)return '价格明显低于长期均线，市场结构偏弱。普通投资者应先核对基本面是否恶化，再考虑价格是否真的更有吸引力。';
    return '目前没有单一指标给出强方向。先看“为什么关注、什么会证明我错”，再用趋势与价格位置做辅助确认。';
  }
  function researchHtml(symbol,q,tp){
    const r=state.research[symbol];const edit=Boolean(global.isAdmin ?? (typeof isAdmin!=='undefined'&&isAdmin));
    const btn=edit?`<button type="button" onclick="StockWatchlist.openResearch('${esc(symbol)}')">${r?'编辑研究卡':'＋ 写研究卡'}</button>`:'';
    if(!state.researchReady)return `<div class="stock-research-card"><div class="stock-research-head"><div><h4>投资论点 · Research Thesis</h4><p>私有研究层</p></div>${btn}</div><div class="stock-research-empty">研究卡数据库尚未启用。先执行 V4.9.6 Supabase migration，再刷新页面。</div></div>`;
    if(!r)return `<div class="stock-research-card"><div class="stock-research-head"><div><h4>投资论点 · Research Thesis</h4><p>先写为什么，再看价格；Trend Pulse只做第二层确认。</p></div>${btn}</div><div class="stock-research-guide"><b>通俗判断：</b>${esc(plainGuide(q,tp))}</div><div class="stock-research-empty">还没有研究卡。建议先写：为什么不直接买指数、核心论点、催化剂、最大风险、什么事实会证明判断错了。</div></div>`;
    const box=(label,key,wide='')=>`<div class="stock-research-item ${wide}"><span>${label}</span><p>${esc(r[key]||'未填写')}</p></div>`;
    return `<div class="stock-research-card"><div class="stock-research-head"><div><h4>投资论点 · Research Thesis</h4><p>最近更新 ${esc((r.updated_at||'').slice(0,10)||'—')} · 下次核验 ${esc(r.next_review_date||'未设置')}</p></div>${btn}</div><div class="stock-research-guide"><b>现在怎么看：</b>${esc(plainGuide(q,tp))}</div><div class="stock-research-grid">${box('我的 Edge / 为什么不是直接买指数','edge')}${box('投资论点 Thesis','thesis','wide')}${box('催化剂','catalysts')}${box('最大风险','risks')}${box('失效条件 / 什么事实说明我错了','invalidation','wide')}${box('估值 / 价格位置','valuation_note')}${box('下一步研究方案','plan','wide')}</div></div>`;
  }
  async function loadResearch(symbols){
    state.research={};state.researchReady=true;if(!symbols.length)return;
    try{const {data,error}=await supabaseClient.from('stock_research_notes').select('*').in('symbol',symbols);if(error)throw error;(data||[]).forEach(r=>state.research[r.symbol]=r)}catch(error){state.researchReady=false;const msg=String(error?.message||error);if(!/stock_research_notes|schema cache|does not exist|PGRST/i.test(msg))global.MAV?.toast(`研究卡读取失败：${msg}`,'warn')}
  }
  function ensureResearchModal(){
    let modal=document.getElementById('stockResearchModal');if(modal)return modal;modal=document.createElement('div');modal.id='stockResearchModal';modal.className='option-modal-backdrop';modal.style.display='none';modal.innerHTML=`<div class="option-modal-card stock-research-modal"><div class="option-modal-head"><div><h3 id="stockResearchTitle">个股研究卡</h3><p>先写论点、反证和下一核验；不记录真实持仓金额。</p></div><button type="button" onclick="StockWatchlist.closeResearch()">×</button></div><p class="stock-research-help">普通投资者模板：不会的指标可以不填。重点是“为什么关注、什么会证明我错、下一步看什么证据”。</p><div class="stock-research-form"><label>我的 Edge / 为什么不是直接买指数<textarea id="researchEdge"></textarea></label><label>下一核验日期<input id="researchNextReview" type="date"></label><label class="wide">投资论点 Thesis<textarea id="researchThesis"></textarea></label><label>主要催化剂<textarea id="researchCatalysts"></textarea></label><label>最大风险<textarea id="researchRisks"></textarea></label><label class="wide">失效条件 / 什么事实说明判断错了<textarea id="researchInvalidation"></textarea></label><label>估值 / 价格位置<textarea id="researchValuation"></textarea></label><label>下一步研究方案<textarea id="researchPlan"></textarea></label></div><div class="option-modal-actions"><button type="button" onclick="StockWatchlist.closeResearch()">取消</button><button class="primary" type="button" onclick="StockWatchlist.saveResearch()">保存研究卡</button></div><input id="researchSymbol" type="hidden"></div>`;document.body.appendChild(modal);return modal;
  }
  function openResearch(symbol){const m=ensureResearchModal(),r=state.research[symbol]||{};document.getElementById('researchSymbol').value=symbol;document.getElementById('stockResearchTitle').textContent=`${symbol} · 个股研究卡`;document.getElementById('researchEdge').value=r.edge||'';document.getElementById('researchThesis').value=r.thesis||'';document.getElementById('researchCatalysts').value=r.catalysts||'';document.getElementById('researchRisks').value=r.risks||'';document.getElementById('researchInvalidation').value=r.invalidation||'';document.getElementById('researchValuation').value=r.valuation_note||'';document.getElementById('researchPlan').value=r.plan||'';document.getElementById('researchNextReview').value=r.next_review_date||'';m.style.display='grid'}
  function closeResearch(){const m=document.getElementById('stockResearchModal');if(m)m.style.display='none'}
  async function saveResearch(){const symbol=document.getElementById('researchSymbol').value;const {data:{session}}=await supabaseClient.auth.getSession();if(!session){alert('请先登录');return}const payload={user_id:session.user.id,symbol,edge:document.getElementById('researchEdge').value.trim(),thesis:document.getElementById('researchThesis').value.trim(),catalysts:document.getElementById('researchCatalysts').value.trim(),risks:document.getElementById('researchRisks').value.trim(),invalidation:document.getElementById('researchInvalidation').value.trim(),valuation_note:document.getElementById('researchValuation').value.trim(),plan:document.getElementById('researchPlan').value.trim(),next_review_date:document.getElementById('researchNextReview').value||null,updated_at:new Date().toISOString()};const {data,error}=await supabaseClient.from('stock_research_notes').upsert(payload).select().single();if(error){alert(`研究卡保存失败：${error.message}`);return}state.research[symbol]=data;state.researchReady=true;closeResearch();render();global.MAVInvestmentAssistant?.rescan?.();global.MAV?.toast(`${symbol} 研究卡已保存`,'good')}
  function rowHtml(item,index){
    const symbol=String(item.symbol).toUpperCase(),q=combined(symbol),price=num(q.price),chg=num(q.changePct),dd=num(q.ytdDrawdown),rsi=num(q.rsi),dist=num(q.dist200),[status,label]=statusOf(q,null);
    const tp=(global.MAV_TREND_PULSE||{})[symbol]||{},tpScore=Number.isFinite(Number(tp.score))?Number(tp.score):null,tpTone=tp.tone||'neutral';
    const pulseHtml=tpScore===null?'<b>—</b><small>数据不足</small>':`<b class="trend-score ${tpTone}">${tpScore>=0?'+':''}${tpScore.toFixed(0)}</b><small class="trend-zone-mini">${esc(trendZone(tpScore))}</small><small class="trend-stage-mini">${esc(trendStage(tp.state))}</small>`;
    const detailId=`stock-detail-${symbol}`;
    const detailPulse=tpScore===null?'数据不足':`${tpScore>=0?'+':''}${tpScore.toFixed(0)} · ${esc(trendZone(tpScore))} · ${esc(trendStage(tp.state))}`;
    return `<tr data-stock-row data-symbol="${esc(symbol)}" data-detail-id="${detailId}" data-status="${status}" data-target-distance="999" data-drawdown="${dd===null?0:Math.abs(dd)}" data-rsi="${rsi===null?999:rsi}" data-dist200="${dist===null?0:dist}" data-pulse="${tpScore===null?-999:tpScore}" data-default-order="${index}"><td class="stock-identity"><div class="stock-name-line"><span class="stock-name">${esc(item.display_name||symbol)}</span><span class="stock-symbol">${esc(symbol)}</span><button type="button" class="stock-mobile-menu" aria-label="${esc(symbol)} 操作菜单" onclick="StockDecision.openContextMenuForSymbol('${esc(symbol)}', this)">⋯</button></div></td><td data-label="最新价 / 涨跌"><b id="close-${esc(symbol)}">${money(price)}</b><small id="chg-${esc(symbol)}" class="${chg!==null&&chg>=0?'pos-text':'neg-text'}">${pct(chg)}</small></td><td data-label="Trend Pulse">${pulseHtml}</td><td data-label="YTD回撤" class="neg-text fw-bold">${pct(dd)}</td><td data-label="RSI">${rsi===null?'—':rsi.toFixed(2)}</td><td data-label="距200MA" class="${dist!==null&&dist<0?'neg-text':''}">${pct(dist)}</td><td data-label="策略价 / 距离" id="target-cell-${esc(symbol)}"><b id="target-${esc(symbol)}">—</b><small id="target-gap-${esc(symbol)}">等待策略数据</small></td><td data-label="状态"><span id="stock-status-${esc(symbol)}" class="stock-status ${status}">${label}</span><span id="action-${esc(symbol)}"></span></td></tr><tr id="${detailId}" class="stock-detail-row" data-detail-for="${esc(symbol)}" hidden><td colspan="8"><div class="stock-detail-panel"><div><span>当日区间</span><b>开 ${money(q.open)} · 高 ${money(q.high)} · 低 ${money(q.low)}</b></div><div><span>YTD高点</span><b>${money(q.ytdHigh)}</b></div><div><span>完整日线</span><b>${esc(q.dailyAsOf||'等待数据')}</b></div><div><span>Trend Pulse</span><b>${detailPulse}</b></div>${researchHtml(symbol,q,tp)}</div></td></tr>`;
  }

  function render(){
    const body=document.getElementById('stocksTableBody');if(!body)return;
    body.innerHTML=state.items.length?state.items.map(rowHtml).join(''):'<tr><td colspan="8" class="stock-watch-empty">观察池为空，点击“新增个股”开始添加。</td></tr>';
    global.StockDecision?.sort('priority');
    global.fetchAndRenderTargets?.();
    const count=state.items.length;
    const chip=document.getElementById('stockCountChip');if(chip)chip.textContent=`${count}只`;
    const stamp=document.getElementById('stockWatchStatus');
    if(stamp)stamp.textContent=`${count}只 · ${sessionOpen()?'普通观察股盘中10分钟更新':'休市保留最近报价'} · 指标${Object.keys(state.daily).length?'按完整收盘日线':'等待日线'} · ${new Date().toLocaleTimeString()}`;
  }
  async function load(){
    if(state.loading)return;state.loading=true;
    try{
      const {data:{session}}=await supabaseClient.auth.getSession();if(!session)return;
      const {data,error}=await supabaseClient.from('stock_watchlist').select('*').order('sort_order').order('symbol');if(error)throw error;
      state.items=data||[];
      loadDailyCache();
      const symbols=state.items.map(x=>x.symbol);
      const [quotes]=await Promise.all([fetchMarket(symbols,'quote'),ensureDaily(symbols),loadResearch(symbols)]);
      state.quotes=quotes;
      render();global.MAVInvestmentAssistant?.rescan?.();schedule();
    }catch(error){global.MAV?.toast(`观察池读取失败：${error.message}。请确认已执行V3.4迁移并部署stock-market。`,'bad')}
    finally{state.loading=false}
  }
  async function refresh(){
    if(!state.items.length)return;
    try{
      const symbols=state.items.map(x=>x.symbol);
      const [quotes]=await Promise.all([fetchMarket(symbols,'quote'),ensureDaily(symbols),loadResearch(symbols)]);
      state.quotes={...state.quotes,...quotes};render();global.MAVInvestmentAssistant?.rescan?.();
    }catch(error){global.MAV?.toast(`个股行情刷新失败：${error.message}`,'warn')}
    finally{schedule()}
  }
  function schedule(){clearTimeout(state.timer);state.timer=setTimeout(()=>{if(document.visibilityState==='visible')refresh();else schedule()},sessionOpen()?600000:1800000)}

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

  function assistantStatus(){
    const rows=state.items.map(item=>{const symbol=String(item.symbol).toUpperCase(),tp=(global.MAV_TREND_PULSE||{})[symbol]||{},r=state.research[symbol]||{};return {symbol,score:num(tp.score),stage:tp.state||'',hasThesis:Boolean((r.thesis||'').trim())};});
    const risk=rows.filter(x=>/趋势恶化|趋势退潮/.test(x.stage)||(x.score!==null&&x.score<=-60)).sort((a,b)=>(a.score??0)-(b.score??0)).slice(0,3);
    const improving=rows.filter(x=>/二次启动|趋势启动|趋势延续|修复中/.test(x.stage)).sort((a,b)=>(b.score??-999)-(a.score??-999)).slice(0,3);
    const hot=rows.filter(x=>x.score!==null&&x.score>=75&&!/趋势退潮/.test(x.stage)).sort((a,b)=>b.score-a.score).slice(0,3);
    return {count:state.items.length,researchCount:rows.filter(x=>x.hasThesis).length,risk,improving,hot,loaded:Boolean(state.items.length)};
  }

  function assistantCandidates(mode='fear'){return state.items.map(item=>{const symbol=String(item.symbol).toUpperCase(),tp=(global.MAV_TREND_PULSE||{})[symbol]||{},r=state.research[symbol]||{},q=combined(symbol);const score=num(tp.score),stage=tp.state||'',hasThesis=Boolean((r.thesis||'').trim());let eligible=false,why='';if(mode==='fear'){eligible=!['趋势恶化','趋势退潮'].includes(stage)&&(score===null||score>-20);why=stage?trendStage(stage):'等待趋势确认';}else{eligible=score!==null&&score>=75;why=stage?trendStage(stage):trendZone(score);}return {symbol,name:item.display_name||symbol,score,stage,zone:trendZone(score),hasThesis,eligible,why,changePct:num(q.changePct)};}).filter(x=>x.eligible).sort((a,b)=>(b.hasThesis-a.hasThesis)||((b.score??-999)-(a.score??-999))).slice(0,6)}
  global.StockWatchlist={load,refresh,openAdd,openEdit,close,save,remove,openResearch,closeResearch,saveResearch,assistantCandidates,assistantStatus};
  document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&state.items.length)refresh()});
})(window);
