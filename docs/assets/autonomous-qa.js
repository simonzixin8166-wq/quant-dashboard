(function(global){
'use strict';
const APP_VERSION=document.body?.dataset?.appVersion||document.querySelector('meta[name="application-version"]')?.content||'—';
const state={last:null,running:false,lastRunAt:0};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const now=()=>new Date().toLocaleString([],{hour12:false});
const item=(name,status,detail='')=>({name,status,detail});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function jfetch(url,timeout=12000){const c=new AbortController();const id=setTimeout(()=>c.abort(),timeout);try{const r=await fetch(`${url}${url.includes('?')?'&':'?'}qa=${Date.now()}`,{cache:'no-store',signal:c.signal});if(!r.ok)throw new Error(`HTTP ${r.status}`);return await r.json()}finally{clearTimeout(id)}}
function noNegativeZero(){const txt=document.body?.innerText||'';return !/(^|[^\d])-0(?:\.0+)?(?=\s|%|$|｜|·)/m.test(txt)}
function versionAligned(){const meta=document.querySelector('meta[name="application-version"]')?.content;return meta===APP_VERSION&&String(APP_VERSION).startsWith('5.3.0')}
async function assistantHealth(){
  // The real assistant root is marketOptionAlert.  Give async market/auth scripts
  // time to initialize before deciding anything is broken.
  for(let i=0;i<6;i++){
    const root=document.getElementById('marketOptionAlert'),api=global.MAVInvestmentAssistant;
    if(root&&api){
      const scan=api.state?.lastScanAt;
      if(scan)return item('AI 投资助手','pass',`最近扫描 ${new Date(scan).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}`);
      if(i<5){await sleep(800);continue}
      return item('AI 投资助手','info','模块已加载，等待第一份市场快照；不影响其他数据');
    }
    await sleep(600);
  }
  return item('AI 投资助手','fail','助手脚本或页面容器未加载');
}
async function privateHealth(){
  const out=[];const privateMode=document.body.classList.contains('private-mode');
  out.push(item('登录状态',privateMode?'pass':'info',privateMode?'私有模式已解锁':'当前为访客模式；登录后自动补充私有检查'));
  if(!privateMode)return out;
  let sb=global.mavSupabase||global.supabaseClient;
  for(let i=0;i<6&&!sb?.auth?.getSession;i++){await sleep(500);sb=global.mavSupabase||global.supabaseClient}
  if(!sb?.auth?.getSession){out.push(item('Supabase Session','warn','登录组件仍在初始化，将在下次自检重试'));return out}
  try{const {data:{session}}=await sb.auth.getSession();out.push(item('Supabase Session',session?'pass':'fail',session?'会话有效':'会话缺失'))}catch(e){out.push(item('Supabase Session','fail',e.message))}
  for(const [label,table] of [['观察池','stock_watchlist'],['策略价','stock_targets'],['研究卡','stock_research_notes'],['期权持仓','options_positions']]){
    try{const {error}=await sb.from(table).select('*',{head:true,count:'exact'}).limit(1);out.push(item(label,error?'warn':'pass',error?`权限/连接异常：${error.message}`:'RLS读取正常'))}catch(e){out.push(item(label,'warn',e.message))}
  }
  return out;
}
async function run({silent=false}={}){
  if(state.running)return state.last;state.running=true;
  const checks=[];let manifest=null,data=null;
  try{manifest=await jfetch('build-manifest.json');checks.push(item('线上构建指纹','pass',`${manifest.app_version||'—'} · ${manifest.build_id||'—'}`))}catch(e){checks.push(item('线上构建指纹','warn',e.message))}
  try{data=await jfetch('data.json');checks.push(item('核心数据文件','pass',`生成 ${data.gen_time||data.updated||'—'} · 美股日线 ${data.spy_date||'—'}`))}catch(e){checks.push(item('核心数据文件','fail',e.message))}
  checks.push(item('版本一致性',versionAligned()?'pass':'fail',`页面 ${APP_VERSION}${manifest?.app_version?` · 构建 ${manifest.app_version}`:''}`));
  checks.push(item('Trend Pulse -0',noNegativeZero()?'pass':'warn',noNegativeZero()?'未发现 -0 展示':'发现疑似 -0，请检查显示口径'));
  checks.push(await assistantHealth());
  checks.push(item('Decision Journal',document.getElementById('decisionJournalRoot')&&global.MAVDecisionJournal?'pass':'fail','实时日志 + STOOQ历史学习 + 20/60/120交易日验证'));
  try{const h=await jfetch('research/historical_journal.json');checks.push(item('本地历史学习','pass',`${h.summary?.symbols??'—'} 个标的 · ${h.summary?.events??'—'} 个状态事件 · 60日成熟 ${h.summary?.mature_60??'—'}`))}catch(e){checks.push(item('本地历史学习','warn','历史报告等待 Daily Dashboard Update 生成'))}
  try{const ev=await jfetch('data/market_events.json');checks.push(item('宏观事件数据','pass',Array.isArray(ev?.events)?`${ev.events.length} 条事件`:'已读取'))}catch(e){checks.push(item('宏观事件数据','warn',e.message))}
  try{const w=await jfetch('data/wenxuecity.json');checks.push(item('方法研究数据','pass',`资料 ${Array.isArray(w?.items)?w.items.length:'已读取'} · 抓取失败不影响行情`))}catch(e){checks.push(item('方法研究数据','warn',`${e.message} · 不影响主行情`))}
  try{const v=await jfetch('research/assistant_rule_validation.json');checks.push(item('历史市场规则验证','pass',`最近生成 ${v.generated_at||v.as_of||'可用'}`))}catch(e){checks.push(item('历史市场规则验证','info','等待 Daily Dashboard Update 生成/更新'))}
  checks.push(...await privateHealth());
  const hardFail=checks.filter(x=>x.status==='fail').length,warn=checks.filter(x=>x.status==='warn').length;
  const report={version:APP_VERSION,checked_at:new Date().toISOString(),overall:hardFail?'FAIL':warn?'WARNING':'PASS',hard_failures:hardFail,warnings:warn,checks,manifest_build_id:manifest?.build_id||null,data_gen_time:data?.gen_time||null};
  state.last=report;state.lastRunAt=Date.now();state.running=false;try{localStorage.setItem('mavAutonomousQA',JSON.stringify(report))}catch{}
  render();if(!silent)global.MAV?.toast?.(`系统自检：${report.overall}${warn?` · ${warn}项提醒`:''}`,hardFail?'bad':warn?'warn':'good');return report;
}
function badge(s){return `<span class="qa-badge ${s}">${s==='pass'?'PASS':s==='fail'?'FAIL':s==='warn'?'WARN':'INFO'}</span>`}
function render(){const root=document.getElementById('systemHealthRoot');if(!root)return;const r=state.last;if(!r){root.innerHTML='<div class="qa-empty">系统正在自动检查…</div>';return}
 root.innerHTML=`<section class="hero compact-hero"><div><h1>Autonomous QA · 系统自检</h1><p>自动确认“代码已部署、数据仍新鲜、核心模块可用”。短暂初始化只记 INFO/WARN，不会误判整站失败。</p></div><div class="qa-overall ${r.overall.toLowerCase()}"><b>${r.overall}</b><small>${esc(now())}</small></div></section><section class="qa-grid">${r.checks.map(c=>`<article><div>${badge(c.status)}<b>${esc(c.name)}</b></div><p>${esc(c.detail||'')}</p></article>`).join('')}</section><section class="qa-note"><b>自动化原则</b><p>发现异常先报警和重试，不自动修改投资规则或切换数据源。核心行情抓取路径与盘中刷新频率保持原样。</p><button type="button" onclick="MAVAutonomousQA.run()">立即重新自检</button></section>`;
}
function init(){render();setTimeout(()=>run({silent:true}),4500);setInterval(()=>run({silent:true}),15*60*1000);global.addEventListener('focus',()=>{if(Date.now()-state.lastRunAt>10*60*1000)run({silent:true})})}
global.MAVAutonomousQA={run,render,state};if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})(window);
