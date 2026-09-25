(function(){
  'use strict';
  const installButton=document.getElementById('pwaInstallButton');
  const updateBanner=document.getElementById('pwaUpdateBanner');
  const updateNow=document.getElementById('pwaUpdateNow');
  const updateLater=document.getElementById('pwaUpdateLater');
  const networkBanner=document.getElementById('pwaNetworkBanner');
  let deferredInstall=null;
  let refreshing=false;

  function standalone(){return matchMedia('(display-mode: standalone)').matches||navigator.standalone===true;}
  function iosSafari(){return /iphone|ipad|ipod/i.test(navigator.userAgent)&&/safari/i.test(navigator.userAgent)&&!/crios|fxios|edgios/i.test(navigator.userAgent);}
  function showUpdate(registration){
    if(!registration?.waiting||!updateBanner)return;
    updateBanner.classList.add('visible');
    updateBanner.removeAttribute('hidden');
    updateNow.onclick=()=>registration.waiting.postMessage({type:'SKIP_WAITING'});
  }
  function showNetworkState(){
    if(!networkBanner)return;
    const offline=!navigator.onLine;
    networkBanner.classList.toggle('visible',offline);
    networkBanner.hidden=!offline;
  }

  window.addEventListener('beforeinstallprompt',event=>{
    event.preventDefault();deferredInstall=event;
    if(installButton&&!standalone())installButton.classList.add('available');
  });
  installButton?.addEventListener('click',async()=>{
    if(!deferredInstall&&iosSafari()){
      alert('在 Safari 底部点击“分享”，再选择“添加到主屏幕”。');
      return;
    }
    if(!deferredInstall)return;
    deferredInstall.prompt();
    await deferredInstall.userChoice;
    deferredInstall=null;installButton.classList.remove('available');
  });
  window.addEventListener('appinstalled',()=>{deferredInstall=null;installButton?.classList.remove('available');});
  window.addEventListener('online',showNetworkState);
  window.addEventListener('offline',showNetworkState);
  showNetworkState();
  if(installButton&&iosSafari()&&!standalone())installButton.classList.add('available');
  updateLater?.addEventListener('click',()=>{updateBanner.classList.remove('visible');updateBanner.hidden=true;});

  if(!('serviceWorker' in navigator))return;
  window.addEventListener('load',async()=>{
    try{
      const registration=await navigator.serviceWorker.register('./sw.js',{scope:'./'});
      if(registration.waiting)showUpdate(registration);
      registration.addEventListener('updatefound',()=>{
        const worker=registration.installing;
        worker?.addEventListener('statechange',()=>{
          if(worker.state==='installed'&&navigator.serviceWorker.controller)showUpdate(registration);
        });
      });
      document.addEventListener('visibilitychange',()=>{
        if(document.visibilityState==='visible')registration.update().catch(()=>{});
      });
      setInterval(()=>registration.update().catch(()=>{}),60*60*1000);
    }catch(error){console.warn('PWA registration unavailable',error);}
  });
  navigator.serviceWorker.addEventListener('controllerchange',()=>{
    if(refreshing)return;refreshing=true;location.reload();
  });
})();
