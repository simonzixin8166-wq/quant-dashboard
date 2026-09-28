(function(global){
  'use strict';
  const root=document.documentElement;
  function applyTheme(theme){root.dataset.theme=theme;localStorage.setItem('mavTheme',theme);const b=document.getElementById('themeToggle');if(b)b.textContent=theme==='dark'?'☀️ 浅色':'🌙 深色'}
  function initTheme(){const saved=localStorage.getItem('mavTheme'),preferred=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';applyTheme(saved||preferred);document.getElementById('themeToggle')?.addEventListener('click',()=>applyTheme(root.dataset.theme==='dark'?'light':'dark'))}
  function toast(message,tone='warn',timeout=5000){let wrap=document.querySelector('.mav-toast-wrap');if(!wrap){wrap=document.createElement('div');wrap.className='mav-toast-wrap';document.body.appendChild(wrap)}const item=document.createElement('div');item.className=`mav-toast ${tone}`;item.textContent=message;wrap.appendChild(item);setTimeout(()=>item.remove(),timeout)}
  async function loadEvents(){
    const host=document.getElementById('macroEventStrip');if(!host)return;
    try{const res=await fetch(`data/market_events.json?v=${Date.now()}`,{cache:'no-store'});if(!res.ok)throw new Error(`HTTP ${res.status}`);const data=await res.json(),events=(data.events||[]).filter(x=>new Date(x.datetime)>=new Date(Date.now()-86400000)).slice(0,5);global.MAV_EVENTS=data.events||[];host.innerHTML=events.length?events.map(x=>`<div class="event-item"><strong>${x.type}</strong> · ${new Date(x.datetime).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})}<br>${x.title}</div>`).join(''):'<div class="event-item">未来日历暂无已确认事件</div>';global.OptionV2?.setMarketEvents(global.MAV_EVENTS,data.updated_at)}catch(e){host.innerHTML='<div class="event-item">宏观日历暂不可用，不使用推测日期</div>';toast(`宏观日历读取失败：${e.message}`,'bad')}
  }
  const stockState={filter:'all'};
  function stockRows(){return [...document.querySelectorAll('#stocksTableBody tr[data-stock-row]')]}
  function detailRow(row){const id=row?.dataset?.detailId;return id?document.getElementById(id):null}
  function applyStockFilter(){stockRows().forEach(row=>{const hidden=stockState.filter!=='all'&&row.dataset.status!==stockState.filter;row.hidden=hidden;const d=detailRow(row);if(d&&hidden)d.hidden=true})}
  function filterStocks(button,status){stockState.filter=status;document.querySelectorAll('[data-stock-filter]').forEach(x=>x.classList.toggle('active',x===button));applyStockFilter()}
  function sortStocks(mode){
    const body=document.getElementById('stocksTableBody');if(!body)return;const rows=stockRows();
    const number=(row,key,fallback=999)=>{const n=Number(row.dataset[key]);return Number.isFinite(n)?n:fallback};
    const rank={triggered:0,near:1,oversold:2,weak:3,hot:4,normal:5};
    if(mode==='priority')rows.sort((a,b)=>(rank[a.dataset.status]??9)-(rank[b.dataset.status]??9)||number(a,'targetDistance')-number(b,'targetDistance'));
    if(mode==='target')rows.sort((a,b)=>number(a,'targetDistance')-number(b,'targetDistance'));
    if(mode==='drawdown')rows.sort((a,b)=>number(b,'drawdown',0)-number(a,'drawdown',0));
    if(mode==='rsi')rows.sort((a,b)=>number(a,'rsi')-number(b,'rsi'));
    if(mode==='default')rows.sort((a,b)=>number(a,'defaultOrder')-number(b,'defaultOrder'));
    rows.forEach(row=>{body.appendChild(row);const d=detailRow(row);if(d)body.appendChild(d)});applyStockFilter();
  }
  function updateTarget(symbol,target){
    const closeNode=document.getElementById(`close-${symbol}`),targetNode=document.getElementById(`target-${symbol}`),gapNode=document.getElementById(`target-gap-${symbol}`),statusNode=document.getElementById(`stock-status-${symbol}`),row=targetNode?.closest('tr');if(!closeNode||!targetNode||!gapNode||!statusNode||!row)return;
    const close=Number(closeNode.textContent.replace(/[$,]/g,'')),value=Number(target),hasValue=target!==null&&target!==''&&Number.isFinite(value)&&value>0,rsi=Number(row.dataset.rsi),dist=Number(row.dataset.dist200);targetNode.textContent=hasValue?`$${value.toFixed(2)}`:'—';
    let status='normal',label='正常观察',distance=999;if(hasValue&&Number.isFinite(close)){distance=Math.abs(value/close-1);if(close<=value){status='triggered';label='已触发';gapNode.textContent=`低于策略价 ${Math.abs((close/value-1)*100).toFixed(1)}%`}else{gapNode.textContent=`还需下跌 ${Math.abs((value/close-1)*100).toFixed(1)}%`;if(close/value-1<=.05){status='near';label='接近策略价'}}}else gapNode.textContent='未设置';
    if(status==='normal'&&rsi<35){status='oversold';label='超卖观察'}else if(status==='normal'&&dist<-.10){status='weak';label='趋势偏弱'}else if(status==='normal'&&(rsi>70||dist>.25)){status='hot';label='过热'}
    row.dataset.status=status;row.dataset.targetDistance=distance;statusNode.className=`stock-status ${status}`;statusNode.textContent=label;applyStockFilter();
  }
  function toggleDetails(symbol){const row=document.getElementById(`stock-detail-${symbol}`);if(!row)return;const shouldOpen=row.hidden;document.querySelectorAll('.stock-detail-row').forEach(x=>x.hidden=true);row.hidden=!shouldOpen}
  let stockContextMenu=null;
  function ensureContextMenu(){
    if(stockContextMenu)return stockContextMenu;
    stockContextMenu=document.createElement('div');stockContextMenu.id='stockContextMenu';stockContextMenu.className='stock-context-menu';stockContextMenu.hidden=true;stockContextMenu.setAttribute('role','menu');document.body.appendChild(stockContextMenu);return stockContextMenu;
  }
  function closeContextMenu(){if(stockContextMenu)stockContextMenu.hidden=true}
  function contextMenuHtml(symbol){
    const admin=Boolean(global.isAdmin ?? (typeof isAdmin!=='undefined'&&isAdmin));
    const parts=[`<button type="button" data-cmd="details">查看行情详情</button>`];
    if(admin){parts.push('<div class="stock-context-sep"></div>',`<button type="button" data-cmd="edit">修改个股</button>`,`<button type="button" data-cmd="target">设置 / 修改策略价</button>`,`<button type="button" data-cmd="delete-target">删除策略价</button>`,'<div class="stock-context-sep"></div>',`<button type="button" class="danger" data-cmd="delete-stock">删除个股</button>`)}
    return parts.join('');
  }
  function openContextMenu(symbol,x,y){
    const menu=ensureContextMenu();menu.dataset.symbol=symbol;menu.innerHTML=contextMenuHtml(symbol);menu.hidden=false;
    const w=220,h=Math.min(330,menu.scrollHeight||260),left=Math.max(8,Math.min(x,innerWidth-w-8)),top=Math.max(8,Math.min(y,innerHeight-h-8));menu.style.left=`${left}px`;menu.style.top=`${top}px`;
  }
  function openContextMenuForSymbol(symbol,anchor){const r=anchor.getBoundingClientRect();openContextMenu(symbol,Math.min(r.right,innerWidth-8),Math.min(r.bottom+6,innerHeight-8))}
  function handleContextAction(event){const btn=event.target.closest('button[data-cmd]');if(!btn||!stockContextMenu)return;const symbol=stockContextMenu.dataset.symbol,cmd=btn.dataset.cmd;closeContextMenu();if(cmd==='details')toggleDetails(symbol);if(cmd==='edit')global.StockWatchlist?.openEdit(symbol);if(cmd==='target'){const raw=document.getElementById(`target-${symbol}`)?.textContent?.replace(/[$,]/g,'');const current=raw&&raw!=='—'?Number(raw):null;global.editTarget?.(symbol,Number.isFinite(current)?current:null);}if(cmd==='delete-target')global.deleteTarget?.(symbol);if(cmd==='delete-stock')global.StockWatchlist?.remove(symbol)}
  function initStockContextMenu(){
    const menu=ensureContextMenu();menu.addEventListener('click',handleContextAction);
    document.addEventListener('contextmenu',event=>{const row=event.target.closest('#stocksTableBody tr[data-stock-row]');if(!row)return;event.preventDefault();openContextMenu(row.dataset.symbol||row.querySelector('.stock-symbol')?.textContent?.trim(),event.clientX,event.clientY)});
    document.addEventListener('click',event=>{if(!event.target.closest('#stockContextMenu')&&!event.target.closest('.stock-mobile-menu'))closeContextMenu()});
    window.addEventListener('resize',closeContextMenu);window.addEventListener('scroll',closeContextMenu,true);
  }
  function initStocks(){stockRows().forEach((row,i)=>{row.dataset.defaultOrder=String(i);if(!row.dataset.symbol)row.dataset.symbol=row.querySelector('.stock-symbol')?.textContent?.trim()||''});sortStocks('priority');initStockContextMenu()}
  global.StockDecision={filter:filterStocks,sort:sortStocks,updateTarget,toggleDetails,openContextMenuForSymbol};
  global.MAV={toast,applyTheme};
  document.addEventListener('DOMContentLoaded',()=>{initTheme();loadEvents();initStocks()});
})(window);
