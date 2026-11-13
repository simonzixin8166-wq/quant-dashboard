(function(){
'use strict';
// 突发事件：只读 research/shock_events.json；近 7 天没有事件时整行隐藏。研究提示，不是买卖指令。
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct=v=>Number.isFinite(Number(v))?`${Number(v)>=0?'+':''}${(Number(v)*100).toFixed(1)}%`:'—';
const SESSION={pre:'盘前',post:'盘后',regular:'盘中'};
function card(e){
  const q=e.quote||{};
  const head=e.kind==='market'?`市场波动：${esc((e.market_movers||[]).join('、')||'VIX')}`:`${esc(e.subject)} ${q.move_total==null?'':pct(q.move_total)}`;
  const news=(e.headlines||[]).slice(0,2).map(h=>`<li><a href="${esc(h.url||'#')}" target="_blank" rel="noopener noreferrer">${esc(h.title)}</a><small>${esc(h.publisher)} · ${esc(String(h.published_at||'').slice(0,16).replace('T',' '))} UTC</small></li>`).join('');
  const outs=(e.outcomes||[]).map(o=>`${o.n} 日后 ${e.kind==='company'?`${esc(e.subject)} ${pct(o[e.subject])}，`:''}QQQ ${pct(o.QQQ)}`).join('；');
  return `<article class="shock-card shock-${esc(e.severity)}"><header><b>${head}</b><span>${e.severity==='high'?'价格+新闻':'需关注'} · ${esc(SESSION[q.session]||'')} · 首次发现 ${esc(String(e.first_seen||'').slice(0,16).replace('T',' '))} UTC</span></header>${news?`<ul class="shock-news">${news}</ul><p class="shock-muted">以上为媒体报道，未经核实。</p>`:''}<ul class="shock-advice">${(e.advice||[]).map(t=>`<li>${esc(t)}</li>`).join('')}</ul>${outs?`<p class="shock-muted">事后跟踪：${outs}</p>`:''}${(e.corrections||[]).map(c=>`<p class="shock-muted">更正：${esc(c.reason_zh)}</p>`).join('')}</article>`;
}
function render(root,d){
  const cutoff=Date.now()-7*864e5;
  const rows=(d.events||[]).filter(e=>!e.retracted&&Date.parse(e.first_seen)>=cutoff);
  if(!rows.length){root.hidden=true;return}
  root.hidden=false;
  root.innerHTML=`<div class="shock-head"><h2>突发事件</h2><p>每天两次自动检查（美股开盘前、收盘后）；只记录与分析，不下单。</p></div>${rows.slice(0,3).map(card).join('')}`;
}
function load(){
  const root=document.getElementById('shockEventRoot');if(!root)return;
  fetch('research/shock_events.json?v='+Date.now(),{cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(r.status)).then(d=>render(root,d)).catch(()=>{root.hidden=true});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',load);else load();
})();
