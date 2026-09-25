const CACHE_PREFIX='mav-shell-';
const CACHE_NAME=`${CACHE_PREFIX}3.9.0`;
const OFFLINE_URL='./offline.html';
const SHELL=[
  './','./index.html','./manifest.webmanifest',OFFLINE_URL,
  './assets/dashboard-v2.2.css?v=3.9.0','./assets/options-v2.css?v=3.9.0',
  './assets/roll-manager.css?v=3.9.0','./assets/finance-tools.css?v=3.9.0',
  './assets/opportunity-radar.css?v=3.9.0','./assets/pwa.css?v=3.9.0',
  './assets/dashboard-v2.2.js?v=3.9.0','./assets/options-v2.js?v=3.9.0',
  './assets/roll-manager.js?v=3.9.0','./assets/stock-watchlist.js?v=3.9.0',
  './assets/finance-tools.js?v=3.9.0','./assets/opportunity-radar.js?v=3.9.0',
  './assets/site-analytics.js?v=3.9.0','./assets/market-live.js?v=3.9.0',
  './assets/pwa.js?v=3.9.0','./icons/icon-192.png','./icons/icon-512.png','./icons/icon-maskable-512.png'
];

self.addEventListener('install',event=>{
  event.waitUntil(caches.open(CACHE_NAME).then(async cache=>{
    await Promise.allSettled(SHELL.map(url=>cache.add(new Request(url,{cache:'reload'}))));
  }));
});
self.addEventListener('message',event=>{if(event.data?.type==='SKIP_WAITING')self.skipWaiting();});
self.addEventListener('activate',event=>{
  event.waitUntil(Promise.all([
    caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith(CACHE_PREFIX)&&key!==CACHE_NAME).map(key=>caches.delete(key)))),
    self.clients.claim()
  ]));
});
self.addEventListener('fetch',event=>{
  const request=event.request;
  if(request.method!=='GET')return;
  const url=new URL(request.url);
  if(url.origin!==self.location.origin)return;
  if(url.pathname.includes('/rest/v1/')||url.pathname.includes('/functions/v1/')||url.pathname.includes('/auth/v1/'))return;
  if(request.mode==='navigate'){
    event.respondWith(fetch(request).catch(()=>caches.match(OFFLINE_URL)));
    return;
  }
  const staticAsset=/\.(?:css|js|png|svg|webmanifest)$/i.test(url.pathname);
  if(!staticAsset)return;
  event.respondWith(caches.match(request).then(cached=>{
    const network=fetch(request).then(response=>{
      if(response.ok)caches.open(CACHE_NAME).then(cache=>cache.put(request,response.clone()));
      return response;
    });
    return cached||network;
  }));
});
