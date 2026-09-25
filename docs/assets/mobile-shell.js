(function(global){
  'use strict';
  const PRIMARY=[
    {id:'tab-overview',label:'总览',icon:'◆'},
    {id:'tab-engine',label:'策略',icon:'◒'},
    {id:'tab-stocks',label:'观察',icon:'⌁'},
    {id:'tab-options',label:'期权',icon:'⚑'}
  ];
  const state={current:'tab-overview'};
  const byId=id=>document.getElementById(id);
  const originalItem=id=>[...document.querySelectorAll('.sidebar .nav-menu li')].find(item=>(item.getAttribute('onclick')||'').includes(`'${id}'`));
  const tabId=item=>((item.getAttribute('onclick')||'').match(/switchTab\('([^']+)'/)||[])[1];
  const labelFor=item=>item.textContent.replace('NEW','').replace(/^[◆◒◫◇⌁⚑◎🧮📜]/u,'').trim();
  function allowed(id){return id==='tab-overview'||document.body.classList.contains('private-mode');}
  function close(){byId('mobileNavSheet')?.classList.remove('open');byId('mobileNavBackdrop')?.classList.remove('open');document.body.classList.remove('mobile-drawer-open');byId('mobileNavSheet')?.setAttribute('aria-hidden','true');}
  function open(){byId('mobileNavSheet')?.classList.add('open');byId('mobileNavBackdrop')?.classList.add('open');document.body.classList.add('mobile-drawer-open');byId('mobileNavSheet')?.setAttribute('aria-hidden','false');}
  function sync(id){
    state.current=id||state.current;
    document.querySelectorAll('[data-mobile-tab]').forEach(button=>button.classList.toggle('active',button.dataset.mobileTab===state.current));
    const more=byId('mobileMoreButton');if(more)more.classList.toggle('active',!PRIMARY.some(item=>item.id===state.current));
  }
  function navigate(id){
    const source=originalItem(id);if(!source)return;
    global.switchTab(id,source);
    if(allowed(id)){state.current=id;sync(id);close();}
  }
  function action(kind){
    if(kind==='theme')byId('themeToggle')?.click();
    if(kind==='auth')global.handleAuth?.();
    if(kind==='install')byId('pwaInstallButton')?.click();
    close();
  }
  function build(){
    const bottom=byId('mobileBottomNav'),list=byId('mobileNavList');if(!bottom||!list)return;
    bottom.innerHTML=PRIMARY.map(item=>`<button type="button" data-mobile-tab="${item.id}" aria-label="${item.label}"><span class="mobile-nav-icon">${item.icon}</span><span>${item.label}</span></button>`).join('')+'<button id="mobileMoreButton" type="button" aria-label="全部模块"><span class="mobile-nav-icon">☰</span><span>更多</span></button>';
    bottom.querySelectorAll('[data-mobile-tab]').forEach(button=>button.addEventListener('click',()=>navigate(button.dataset.mobileTab)));
    byId('mobileMoreButton').addEventListener('click',open);
    list.innerHTML=[...document.querySelectorAll('.sidebar .nav-menu li')].map(item=>{const id=tabId(item);if(!id)return'';const icon=item.querySelector('.nav-icon')?.textContent||'•';return`<button type="button" data-mobile-tab="${id}" class="${item.hasAttribute('data-auth-required')?'locked':''}"><span>${icon}</span>${labelFor(item)}</button>`}).join('');
    list.querySelectorAll('[data-mobile-tab]').forEach(button=>button.addEventListener('click',()=>navigate(button.dataset.mobileTab)));
    byId('mobileNavBackdrop')?.addEventListener('click',close);
    byId('mobileNavClose')?.addEventListener('click',close);
    byId('mobileThemeAction')?.addEventListener('click',()=>action('theme'));
    byId('mobileAuthAction')?.addEventListener('click',()=>action('auth'));
    byId('mobileInstallAction')?.addEventListener('click',()=>action('install'));
    document.addEventListener('keydown',event=>{if(event.key==='Escape')close();});
    new MutationObserver(()=>{
      document.querySelectorAll('#mobileNavList button[data-mobile-tab]').forEach(button=>button.classList.toggle('locked',button.dataset.mobileTab!=='tab-overview'&&!document.body.classList.contains('private-mode')));
      const auth=byId('mobileAuthAction');if(auth)auth.textContent=document.body.classList.contains('private-mode')?'退出账号':'登录';
    }).observe(document.body,{attributes:true,attributeFilter:['class']});
    sync(state.current);
  }
  global.MobileShell={open,close,navigate,sync,action};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',build);else build();
})(window);
