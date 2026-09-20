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
  global.MAV={toast,applyTheme};
  document.addEventListener('DOMContentLoaded',()=>{initTheme();loadEvents()});
})(window);
