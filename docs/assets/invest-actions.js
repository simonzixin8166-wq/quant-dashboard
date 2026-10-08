/* V6.11 投资行动速览 · 黄金分阶段建仓 + 月度 ETF 定投（仅提醒，不自动下单） */
(function(global){
'use strict';
const OZ_G=31.1034768;
const STATUS_URL='research/investment_actions_status.json';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=v=>{const n=Number(v);return Number.isFinite(n)?n:null};
const usd=(v,d=0)=>num(v)===null?'—':'$'+Number(v).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
const cny=(v,d=0)=>num(v)===null?'—':'¥'+Number(v).toLocaleString('zh-CN',{minimumFractionDigits:d,maximumFractionDigits:d});
const pct=(v,d=1)=>num(v)===null?'—':`${v>0?'+':''}${Number(v).toFixed(d)}%`;
const state={status:null,live:null,liveFx:null,session:null,settings:null,plan:null,plans:[],execs:[],drawer:null,loaded:false,privateError:null};

/* ---------- pure helpers (mirrored by tests/invest_actions.test.js) ---------- */
function etParts(at){
 const p=Object.fromEntries(new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',weekday:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(at).map(x=>[x.type,x.value]));
 return{wd:p.weekday,min:Number(p.hour)*60+Number(p.minute)};
}
function goldMarketOpen(at=new Date()){
 const {wd,min}=etParts(at);
 if(wd==='Sat')return false;
 if(wd==='Sun')return min>=18*60;
 if(wd==='Fri'&&min>=17*60)return false;
 return !(min>=17*60&&min<18*60);
}
function quoteFreshness(quoteAtMs,nowMs,realtime,fr={}){
 if(!Number.isFinite(quoteAtMs))return'STALE';
 const age=(nowMs-quoteAtMs)/60000;
 if(age<-5)return'STALE';
 if(goldMarketOpen(new Date(nowMs))){
  if(age<=(fr.live_max_age_minutes||20))return realtime?'LIVE':'DELAYED';
  return age<=(fr.delayed_max_age_minutes||90)?'DELAYED':'STALE';
 }
 // Closed: a quote from the last 3.5 days (weekend) is the last close, not live.
 return age<=84*60?'CLOSED':'STALE';
}
function stageFor(price,stages){
 return (stages||[]).find(s=>(price>=s.min&&price<s.max)||(s.stage===1&&price===s.max))||null;
}
function zoneFor(price,status){
 const g=status?.gold||{},stages=g.stages||[],core=g.core_watch_zone||{min:3950,max:4050};
 if(!Number.isFinite(price)||!stages.length)return'unknown';
 const lo=Math.min(...stages.map(s=>s.min)),hi=Math.max(...stages.map(s=>s.max));
 if(price>4275)return'breakout';
 if(price>hi)return'above_plan';
 if(price<lo)return'below_plan';
 return price>=core.min&&price<=core.max?'core_watch':'deep_plan';
}
/** Final displayed gold view. Server rules decide BUY/PAUSE/REVIEW; a fresher live
 *  quote can only move the zone (WAIT↔WATCH) or downgrade, never create a BUY. */
function goldView(status,live,nowMs=Date.now()){
 const g=status?.gold;if(!g)return{state:'LOADING'};
 const fr=status?.freshness||{};
 const sQ=g.quote||{},sAt=Date.parse(sQ.as_of||'');
 const lAt=live?.updated?Number(live.updated)*1000:NaN;
 const useLive=live&&!live.error&&Number.isFinite(Number(live.price))&&Number.isFinite(lAt)&&(!Number.isFinite(sAt)||lAt>=sAt);
 const price=useLive?Number(live.price):num(sQ.price);
 const basis=useLive?live.basis:sQ.basis,source=useLive?live.source:sQ.source;
 const asOf=useLive?lAt:sAt;
 const fresh=quoteFreshness(asOf,nowMs,useLive?!!live.realtime:sQ.freshness==='LIVE',fr);
 const stage=Number.isFinite(price)?stageFor(price,g.stages):null;
 const zone=zoneFor(price,status);
 const serverAgeH=(nowMs-Date.parse(status.generated_at||''))/36e5;
 const base={price,basis,source,asOf,fresh,stage,zone,serverAgeH,reasons:g.reasons||[],blockers:g.blockers||[]};
 if(price===null||fresh==='STALE')return{...base,state:'DATA_STALE',reasons:['黄金报价过期或缺失：停止生成新的 BUY 建议']};
 if(g.state==='PAUSE'||(g.state==='REVIEW'&&g.review_kind==='DEEP_REVIEW'))return{...base,state:g.state,review_kind:g.review_kind};
 if(zone==='breakout')return{...base,state:'REVIEW',review_kind:'BREAKOUT_REVIEW',reasons:['突破 $4,275：趋势复核，不追高']};
 if(zone==='below_plan')return{...base,state:'REVIEW',review_kind:'BELOW_PLAN',reasons:['跌破全部计划档位：不机械越跌越买，等待复核']};
 if(zone==='above_plan')return{...base,state:'WAIT'};
 const serverBuy=g.state==='BUY'&&g.stage===stage?.stage&&serverAgeH<=2&&basis==='spot'&&['LIVE','DELAYED'].includes(fresh);
 if(serverBuy)return{...base,state:'BUY'};
 const blockers=g.state==='WATCH'&&g.stage===stage?.stage?g.blockers:['等待服务端按最新日线/宏观数据确认'];
 return{...base,state:'WATCH',blockers};
}
function cnyPerGram(usdOz,fx){return num(usdOz)!==null&&num(fx)!==null?usdOz*fx/OZ_G:null}
function dcaSplit(amount,weights){
 const items=Object.entries(weights||{}),total=items.reduce((a,[,w])=>a+Number(w||0),0)||1;let acc=0;
 return items.map(([symbol,w],i)=>{const amt=i<items.length-1?Math.round(amount*Number(w)/total*100)/100:Math.round((amount-acc)*100)/100;acc+=amt;return{symbol,weight:Number(w)/total,amount_cny:amt}});
}
function shanghaiDate(at=new Date()){return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(at)}
function dcaPhase(today,win){if(!win)return'unknown';if(today<win.due_date)return'upcoming';if(today<=win.window_end)return'due';return'after'}
function dcaLabel(plan,win,today){
 const s=plan?.status||'pending';
 if(s==='completed')return{key:'completed',text:'本月已完成',tone:'done'};
 if(s==='skipped')return{key:'skipped',text:'本月已跳过',tone:'done'};
 const ph=dcaPhase(today,win);
 if(s==='partial')return{key:'partial',text:'部分完成',tone:ph==='upcoming'?'idle':'due'};
 if(ph==='upcoming')return{key:'upcoming',text:windowText(win),tone:'idle'};
 if(ph==='due')return{key:'due',text:'待执行',tone:'due'};
 return{key:'overdue',text:'逾期待执行',tone:'due'};
}
function windowText(win){
 if(!win)return'每月 7–10 日';
 const m=Number(win.due_date.slice(5,7)),a=Number(win.due_date.slice(8,10)),b=Number(win.window_end.slice(8,10)),bm=Number(win.window_end.slice(5,7));
 return bm===m?`${m}月${a}–${b}日`:`${m}月${a}日–${bm}月${b}日`;
}
const STATE_LABEL={WAIT:'WAIT',WATCH:'已进入观察区',BUY:'BUY',PAUSE:'PAUSE · 风险升高',REVIEW:'REVIEW',DATA_STALE:'DATA STALE',LOADING:'读取中'};

/* ---------- data ---------- */
async function loadStatus(){
 try{const r=await fetch(STATUS_URL+'?v='+Date.now(),{cache:'no-store'});state.status=r.ok?await r.json():null}catch{state.status=null}
 state.loaded=true;
}
function sb(){return typeof supabaseClient!=='undefined'?supabaseClient:null}
function currentWindow(){
 const today=shanghaiDate(),months=state.status?.dca_calendar?.months||[];
 return months.find(m=>m.month===today.slice(0,7))||null;
}
async function loadPrivate(){
 const client=sb();if(!client)return;
 try{
  const {data:{session}}=await client.auth.getSession();state.session=session||null;
  if(!session){state.settings=null;state.plans=[];state.execs=[];return}
  const [st,pl,ex]=await Promise.all([
   client.from('investment_plan_settings').select('*').maybeSingle(),
   client.from('dca_monthly_plans').select('*').order('plan_month',{ascending:false}).limit(24),
   client.from('investment_executions').select('*').order('executed_at',{ascending:false}).limit(500)
  ]);
  if(st.error)throw st.error;
  state.settings=st.data||null;state.plans=pl.data||[];state.execs=ex.data||[];state.privateError=null;
  await ensureMonthPlan();
 }catch(e){state.privateError=String(e?.message||e)}
}
async function ensureMonthPlan(){
 const client=sb(),s=state.settings,win=currentWindow();
 if(!client||!state.session||!s?.dca_monthly_cny||s.dca_enabled===false||!win)return;
 const month=win.month+'-01';
 state.plan=state.plans.find(p=>p.plan_month===month)||null;
 if(state.plan)return;
 // One plan per user per month: the (user_id, plan_month) unique key makes this idempotent.
 const {error}=await client.from('dca_monthly_plans').upsert({user_id:state.session.user.id,plan_month:month,amount_cny:s.dca_monthly_cny,weights:s.dca_weights,due_date:win.due_date,window_end:win.window_end},{onConflict:'user_id,plan_month',ignoreDuplicates:true});
 if(error){state.privateError=error.message;return}
 const {data}=await client.from('dca_monthly_plans').select('*').eq('plan_month',month).maybeSingle();
 if(data){state.plan=data;state.plans=[data,...state.plans.filter(p=>p.id!==data.id)]}
}
function goldExecuted(){
 const out={spent:0,stages:new Set()};
 state.execs.filter(x=>x.program==='gold').forEach(x=>{out.spent+=Number(x.shares)*Number(x.price_usd)+Number(x.fee_usd||0);if(x.gold_stage)out.stages.add(Number(x.gold_stage))});
 return out;
}

/* ---------- homepage strip (header + gold + DCA = max 3 rows) ---------- */
function goldRow(v){
 const g=state.status?.gold||{},core=g.core_watch_zone||{min:3950,max:4050};
 const zone=`观察区 ${usd(core.min)}–${Number(core.max).toLocaleString('en-US')}`;
 const time=Number.isFinite(v.asOf)?new Date(v.asOf).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',hour12:false}):'';
 const fresh=v.fresh&&v.fresh!=='LIVE'?`<em class="ias-fresh ${esc(v.fresh.toLowerCase())}">${esc(v.fresh==='CLOSED'?'休市':v.fresh)}</em>`:'';
 let cls='normal',icon='◆',mid=`<span class="ias-wide">${esc(zone)}</span><span class="ias-narrow">${esc(v.stage?'观察区':'未到观察区')}</span>`,badge=`<b class="ias-badge">WAIT</b>`,cta='';
 if(v.state==='WATCH'){cls='watch';icon='⚠';mid=`<strong>已进入观察区</strong><span class="ias-wide"> · 第${esc(v.stage?.stage)}档 · ${esc(time)}</span>`;badge='';cta='<span class="ias-cta">查看建仓建议</span>'}
 else if(v.state==='BUY'){cls='buy';icon='▲';mid=`<strong>BUY · 第${esc(v.stage?.stage)}阶段 ${esc(v.stage?.budget_pct)}%</strong><span class="ias-wide"> · ${esc(time)}</span>`;badge='';cta='<span class="ias-cta">查看建议</span>'}
 else if(v.state==='PAUSE'){cls='pause';icon='⛔';mid=`<strong>PAUSE · 风险升高</strong><span class="ias-wide"> · ${esc((v.reasons[0]||'').replace(/^风险升高，暂停新买入：/,'').slice(0,40))}</span>`;badge=''}
 else if(v.state==='REVIEW'){cls='pause';icon='◎';mid=`<strong>${esc(v.review_kind==='BREAKOUT_REVIEW'?'突破复核':v.review_kind==='DEEP_REVIEW'?'深度复核':'风险复核')}</strong><span class="ias-wide"> · 暂不按档买入</span>`;badge=''}
 else if(v.state==='DATA_STALE'){cls='stale';icon='◌';mid='<strong>DATA STALE</strong><span class="ias-wide"> · 停止生成 BUY</span>';badge=''}
 else if(v.state==='LOADING'){cls='stale';mid='<span>读取黄金行情…</span>';badge=''}
 const price=v.price!=null?usd(v.price,0):'—';
 return `<button type="button" class="ias-row ias-gold ${cls}" data-ias-open="gold" aria-label="黄金 ${esc(price)} ${esc(STATE_LABEL[v.state]||v.state)}，查看详情"><i class="ias-icon">${icon}</i><span class="ias-name">黄金</span><span class="ias-val">${esc(price)}${fresh}</span><span class="ias-sep">｜</span><span class="ias-mid">${mid}</span><span class="ias-end">${badge}${cta}<i class="ias-chev">›</i></span></button>`;
}
function dcaRow(){
 const cfgW=state.settings?.dca_weights||{QQQM:.4,QLD:.2,VGT:.4};
 const mix=Object.entries(cfgW).map(([k,w])=>`${k} ${Math.round(Number(w)*100)}%`).join(' / ');
 const win=currentWindow(),today=shanghaiDate();
 const amount=num(state.plan?.amount_cny??state.settings?.dca_monthly_cny);
 let val='—',lab={key:'idle',text:windowText(win),tone:'idle'},cls='normal';
 if(!state.session){val='登录查看'}
 else if(amount===null){val='未设置';lab={key:'setup',text:'设置月度金额',tone:'idle'}}
 else{val=cny(amount);lab=dcaLabel(state.plan,win,today)}
 if(lab.tone==='due')cls='due';else if(lab.tone==='done')cls='done';
 const badge=lab.tone==='idle'?`<span class="ias-soft">${esc(lab.text)}</span>`:`<b class="ias-badge">${esc(lab.text)}</b>`;
 return `<button type="button" class="ias-row ias-dca ${cls}" data-ias-open="dca" aria-label="月度定投 ${esc(val)} ${esc(lab.text)}，查看详情"><i class="ias-icon">◷</i><span class="ias-name"><span class="ias-wide">月度</span>定投</span><span class="ias-val">${esc(val)}</span><span class="ias-sep">｜</span><span class="ias-mid"><span class="ias-wide">${esc(mix)}</span><span class="ias-narrow">${esc(lab.text)}</span></span><span class="ias-end"><span class="ias-wide">${badge}</span><i class="ias-chev">›</i></span></button>`;
}
function render(){
 const root=document.getElementById('investActionStrip');if(!root)return;
 const v=goldView(state.status,state.live);
 const gen=state.status?.generated_at?new Date(state.status.generated_at).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}):'';
 const src=v.basis==='futures_proxy'?'期货代理':v.basis==='spot'?'现货':'';
 root.innerHTML=`<div class="ias-head"><span class="ias-title">投资行动速览</span><span class="ias-meta">${esc(src)}${src&&gen?' · ':''}${gen?'规则 '+esc(gen):''}</span></div>${goldRow(v)}${dcaRow()}`;
 root.dataset.goldState=v.state;
 root.querySelectorAll('[data-ias-open]').forEach(b=>b.addEventListener('click',()=>openDrawer(b.dataset.iasOpen)));
 if(state.drawer)renderDrawer();
}

/* ---------- drawer ---------- */
function drawerEl(){
 let el=document.getElementById('iasDrawer');
 if(!el){el=document.createElement('div');el.id='iasDrawer';el.className='ias-drawer-wrap';el.innerHTML='<div class="ias-backdrop" data-ias-close></div><aside class="ias-drawer" role="dialog" aria-modal="true" aria-labelledby="iasDrawerTitle"><div class="ias-drawer-body"></div></aside>';document.body.appendChild(el);
  el.addEventListener('click',e=>{if(e.target.closest('[data-ias-close]'))closeDrawer()});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&state.drawer)closeDrawer()});}
 return el;
}
function openDrawer(kind){state.drawer=kind;const el=drawerEl();renderDrawer();el.classList.add('open');document.body.classList.add('ias-lock');setTimeout(()=>el.querySelector('.ias-close')?.focus(),30)}
function closeDrawer(){state.drawer=null;document.getElementById('iasDrawer')?.classList.remove('open');document.body.classList.remove('ias-lock')}
function kv(label,value,sub=''){return `<div class="ias-kv"><span>${esc(label)}</span><b>${value}</b>${sub?`<small>${sub}</small>`:''}</div>`}
function goldDrawer(){
 const s=state.status,g=s?.gold||{},v=goldView(s,state.live),fx=num(state.liveFx?.price)??num(g.fx?.usdcny);
 const fmtT=x=>{const d=new Date(x);return Number.isFinite(d.getTime())?d.toLocaleString('zh-CN',{hour12:false}):(x||'—')};
 const fxAt=state.liveFx?.updated?fmtT(state.liveFx.updated*1000):fmtT(g.fx?.as_of);
 const ys=g.year_stats||{},hi=ys.high,lo=ys.low,budget=num(state.settings?.gold_budget_usd),ex=goldExecuted();
 const t=Number.isFinite(v.asOf)?fmtT(v.asOf):'—';
 const ladder=(g.stages||[]).map(st=>{
  const cur=v.stage?.stage===st.stage,done=ex.stages.has(st.stage);
  const amt=budget!==null?usd(budget*st.budget_pct/100):'—';
  return `<tr class="${cur?'cur':''}"><td>${st.stage}${done?' <i class="ias-pill done">已执行</i>':cur?' <i class="ias-pill cur">当前</i>':''}</td><td>${usd(st.max)}–${Number(st.min).toLocaleString('en-US')}</td><td>${st.budget_pct}%</td><td>${amt}</td><td class="ias-hide-sm">${fx?`${cny(cnyPerGram(st.max,fx))}–${Number(cnyPerGram(st.min,fx)).toFixed(0)}`:'—'}</td></tr>`}).join('')+`<tr><td>—</td><td>预留资金</td><td>${esc(g.reserved_pct??20)}%</td><td>${budget!==null?usd(budget*(g.reserved_pct??20)/100):'—'}</td><td class="ias-hide-sm"></td></tr>`;
 const pc=g.rules?.pause?.checks||[];
 const flag=m=>m===true?'<i class="ias-pill bad">触发</i>':m===false?'<i class="ias-pill ok">未触发</i>':'<i class="ias-pill na">数据缺失</i>';
 const checkRows=pc.map(c=>`<li>${flag(c.met)}<span>${esc(c.rule)}${c.value_bp!=null?` · 实际 ${c.value_bp}bp`:''}${c.value_pct!=null?` · 实际 ${c.value_pct}%`:''}</span></li>`).join('');
 const conf=g.rules?.confirmation||{},dr=g.rules?.deep_review||{};
 let advice='';
 if(v.state==='BUY'){
  const st=v.stage,amt=budget!==null?budget*st.budget_pct/100:null,nb=(g.stages||[]).find(x=>x.stage===st.stage+1);
  const etf=Object.entries(g.etf_quotes||{}).filter(([,q])=>q.price).map(([k,q])=>`${k} ${q.price} ${q.currency||''}`).join(' · ');
  advice=`<section class="ias-advice buy"><h4>BUY · 第${st.stage}阶段</h4><p>黄金现货 ${usd(v.price,2)}；第${st.stage}档条件已确认。建议投入黄金预算的 <b>${st.budget_pct}%</b>${amt!==null?`，约 <b>${usd(amt)}</b>`:'（未设置黄金预算，不输出金额）'}${ex.stages.has(st.stage)?'；<b>本档已记录执行，不重复扣减</b>':''}。</p><p>理由：${esc(v.reasons.join('；'))}</p><p>ETF 最新有效报价：${esc(etf||'暂缺')}</p><p>${nb?`下一档观察：${usd(nb.max)}–${Number(nb.min).toLocaleString('en-US')}`:'已是最后一档'} · 数据时间 ${esc(t)}</p></section>`;
 }else if(v.state==='WATCH'){
  advice=`<section class="ias-advice watch"><h4>已进入观察区 · 第${esc(v.stage?.stage)}档（计划 ${esc(v.stage?.budget_pct)}%）</h4><p>尚未满足 BUY：${esc((v.blockers||[]).join('；')||'等待确认')}</p><p>此时不建议仅凭到价买入；条件确认后首页会升级为 BUY。</p></section>`;
 }else if(v.state==='PAUSE'||v.state==='REVIEW'){
  advice=`<section class="ias-advice pause"><h4>${esc(STATE_LABEL[v.state])}${v.review_kind?' · '+esc(v.review_kind):''}</h4><p>${esc(v.reasons.join('；'))}</p><p>风险暂停优先于价格买入信号，直到风险重新评估通过。</p></section>`;
 }else if(v.state==='DATA_STALE'){
  advice='<section class="ias-advice pause"><h4>DATA STALE</h4><p>行情过期、汇率缺失或风险数据异常：停止生成新的 BUY，不发送购买建议。</p></section>';
 }
 const etfList=Object.entries(g.etf_quotes||{}).map(([k,q])=>`<li><b>${esc(k)}</b><span>${q.price?esc(q.price+' '+(q.currency||'')):'暂缺'}</span><small>${esc(q.as_of?new Date(q.as_of).toLocaleString():(q.error||''))}</small></li>`).join('');
 const priv=!state.session?'<p class="ias-note">登录后可设置黄金总预算并记录每档实际买入（私有，仅本人可见）。</p>':`<form class="ias-form" data-ias-form="gold-budget"><label>黄金总预算（USD）<input name="gold_budget_usd" type="number" min="0" step="100" value="${budget??''}" placeholder="未设置"></label><button type="submit">保存预算</button></form>${budget!==null?`<p class="ias-note">已记录投入 ${usd(ex.spent)} · 剩余 ${usd(Math.max(0,budget-ex.spent))}</p>`:''}<details class="ias-details"><summary>记录一笔黄金 ETF 买入</summary><form class="ias-form grid" data-ias-form="gold-exec"><label>档位<select name="gold_stage">${(g.stages||[]).map(st=>`<option value="${st.stage}" ${v.stage?.stage===st.stage?'selected':''}>第${st.stage}档</option>`).join('')}</select></label><label>ETF<select name="symbol"><option>GLDM</option><option>IAU</option><option>GLD</option><option>SGLN</option></select></label><label>股数<input name="shares" type="number" step="0.0001" min="0" required></label><label>成交价 USD<input name="price_usd" type="number" step="0.0001" min="0" required></label><label>费用 USD<input name="fee_usd" type="number" step="0.01" min="0" value="0"></label><label>日期<input name="executed_at" type="date" value="${shanghaiDate()}"></label><button type="submit">保存记录</button></form></details>`;
 return `<header class="ias-dh gold"><div><span>GOLD · XAU/USD</span><h3 id="iasDrawerTitle">黄金分阶段建仓</h3></div><button class="ias-close" data-ias-close aria-label="关闭">×</button></header>
 <div class="ias-state ${esc(v.state.toLowerCase())}"><b>${esc(v.state==='BUY'?`BUY · 第${v.stage?.stage}阶段 ${v.stage?.budget_pct}%`:v.state==='WATCH'?`已进入观察区 · 第${v.stage?.stage}档`:(STATE_LABEL[v.state]||v.state))}</b><span>${usd(v.price,2)} · ${esc(v.source||'')} · ${esc(v.fresh||'')}</span><small>报价时间 ${esc(t)}${v.basis==='futures_proxy'?' · 期货代理价，非现货，不生成 BUY':''}</small></div>
 ${advice}
 <div class="ias-kvs">${kv('当前国际金价',usd(v.price,2),'美元/金衡盎司')}${kv('人民币/克',cny(cnyPerGram(v.price,fx),1),'理论折算，不含溢价与费用')}${kv('USD/CNY',fx?fx.toFixed(4):'—',esc(fxAt))}${kv(`${ys.year||''} 年内高点`,hi?usd(hi.value,2):'—',hi?`${esc(hi.date)} · ${hi.cny_per_gram?cny(hi.cny_per_gram)+'/克（当日汇率 '+hi.usdcny+'）':'当日汇率缺失'}`:'')}${kv(lo?.verified?'年中已核实低点':'截至目前低点',lo?usd(lo.value,2):'—',lo?`${esc(lo.date)} · ${lo.cny_per_gram?cny(lo.cny_per_gram)+'/克':'当日汇率缺失'} · 非全年最终低点`:'')}${ys.low_estimate_after_verified?kv('其后估算低点',usd(ys.low_estimate_after_verified.value,2),`${esc(ys.low_estimate_after_verified.date)} · 期货基差估算，未经核实`):''}${kv('距高点回撤',pct(hi&&v.price?(v.price/hi.value-1)*100:null),'')}${kv('高于年内低点',pct(lo&&v.price?(v.price/lo.value-1)*100:null),'')}</div>
 <h4 class="ias-h">分档计划</h4><div class="ias-table-wrap"><table class="ias-table"><thead><tr><th>档</th><th>现货区间</th><th>预算</th><th>金额</th><th class="ias-hide-sm">¥/克</th></tr></thead><tbody>${ladder}</tbody></table></div>
 <h4 class="ias-h">风险暂停（任两项触发 → PAUSE）</h4><ul class="ias-checks">${checkRows||'<li>等待服务端规则数据</li>'}</ul>
 <p class="ias-note">止跌/趋势：${esc(conf.detail||'—')}${conf.as_of?`（日线 ${esc(conf.as_of)}）`:''} · 深度复核：${dr.triggered?'已触发':'未触发'} · 全球黄金 ETF 资金流：无免费可靠数据源，暂不参与判断</p>
 <h4 class="ias-h">ETF / ETC 最新报价</h4><ul class="ias-etf">${etfList||'<li>暂缺</li>'}</ul>
 <h4 class="ias-h">我的执行</h4>${priv}
 <p class="ias-foot">数据：${esc(g.quote?.source||'')} / ${esc(g.inputs?.daily?.source||'')} / ${esc(g.inputs?.real_yield?.source||'')} / ${esc(g.inputs?.dxy?.source||'')} · 规则生成 ${esc(s?.generated_at?new Date(s.generated_at).toLocaleString():'—')}。档位为用户确认的初始资金规划，未经回测验证为支撑位；仅研究与购买提醒，绝不自动下单。</p>`;
}
function dcaDrawer(){
 const s=state.settings,plan=state.plan,win=currentWindow(),today=shanghaiDate(),q=state.status?.dca_calendar?.quotes||{};
 const fx=num(state.liveFx?.price)??num(state.status?.gold?.fx?.usdcny);
 const head=`<header class="ias-dh dca"><div><span>MONTHLY DCA · IBKR</span><h3 id="iasDrawerTitle">每月 ETF 定投</h3></div><button class="ias-close" data-ias-close aria-label="关闭">×</button></header>`;
 const cal=(state.status?.dca_calendar?.months||[]).map(m=>`<li><b>${esc(m.month)}</b><span>${esc(m.due_date)} ~ ${esc(m.window_end)}</span>${m.rolled?'<i class="ias-pill na">已顺延</i>':''}</li>`).join('');
 if(!state.session)return head+`<p class="ias-note">定投金额与执行记录属于私有数据，登录后显示。</p><h4 class="ias-h">提醒窗口（Asia/Shanghai，遇美股休市顺延）</h4><ul class="ias-cal">${cal}</ul>`;
 const amount=num(plan?.amount_cny??s?.dca_monthly_cny),weights=plan?.weights||s?.dca_weights||{QQQM:.4,QLD:.2,VGT:.4};
 const settings=`<form class="ias-form" data-ias-form="dca-settings"><label>每月金额（CNY）<input name="dca_monthly_cny" type="number" min="0" step="100" value="${amount??''}" placeholder="例如 5000"></label><button type="submit">保存</button></form><p class="ias-note">比例 ${esc(Object.entries(weights).map(([k,w])=>`${k} ${Math.round(w*100)}%`).join(' / '))} 由你设定，系统不会自动修改。QLD 为每日 2 倍杠杆 ETF，需定期评估波动与回撤。</p>`;
 if(amount===null)return head+'<p class="ias-note">尚未设置月度定投金额。</p>'+settings+`<h4 class="ias-h">提醒窗口</h4><ul class="ias-cal">${cal}</ul>`;
 const lab=dcaLabel(plan,win,today),split=dcaSplit(amount,weights);
 const done=sym=>state.execs.filter(x=>x.program==='dca'&&x.plan_id===plan?.id&&x.symbol===sym).reduce((a,x)=>a+Number(x.shares),0);
 const rows=split.map(x=>{const u=fx?x.amount_cny/fx:null,p=num(q[x.symbol]?.price),sh=u&&p?u/p:null;return `<tr><td><b>${esc(x.symbol)}</b></td><td>${Math.round(x.weight*100)}%</td><td>${cny(x.amount_cny)}</td><td>${u?usd(u,2):'—'}</td><td class="ias-hide-sm">${p?usd(p,2):'—'}</td><td>${sh?sh.toFixed(4):'—'}</td><td class="ias-hide-sm">${done(x.symbol)?Number(done(x.symbol)).toFixed(4):''}</td></tr>`}).join('');
 const cum={};let investedUsd=0,investedCny=0;
 state.execs.filter(x=>x.program==='dca').forEach(x=>{const c=Number(x.shares)*Number(x.price_usd)+Number(x.fee_usd||0);investedUsd+=c;investedCny+=x.usdcny?c*Number(x.usdcny):0;cum[x.symbol]=(cum[x.symbol]||0)+Number(x.shares)});
 const mv=Object.entries(cum).map(([k,sh])=>({k,sh,v:num(q[k]?.price)?sh*q[k].price:null})),mvTotal=mv.reduce((a,x)=>a+(x.v||0),0);
 const alloc=mv.map(x=>`<li><b>${esc(x.k)}</b><span>${x.sh.toFixed(4)} 股</span><small>${x.v!=null?usd(x.v,0)+' · '+(mvTotal?Math.round(x.v/mvTotal*100):0)+'%':'报价暂缺'}</small></li>`).join('');
 const hist=state.plans.map(p=>{const ex=state.execs.filter(x=>x.plan_id===p.id),c=ex.reduce((a,x)=>a+Number(x.shares)*Number(x.price_usd)+Number(x.fee_usd||0),0);return `<tr><td>${esc(String(p.plan_month).slice(0,7))}</td><td>${cny(p.amount_cny)}</td><td><i class="ias-pill ${p.status==='completed'?'ok':p.status==='skipped'?'na':p.status==='partial'?'cur':'bad'}">${esc({pending:'待执行',partial:'部分完成',completed:'已完成',skipped:'已跳过'}[p.status]||p.status)}</i></td><td>${ex.length?usd(c,2):'—'}</td></tr>`}).join('');
 return head+`<div class="ias-state dca-${esc(lab.key)}"><b>${esc(win?.month||'')} · ${esc(lab.text)}</b><span>${cny(amount)} · 窗口 ${esc(win?`${win.due_date} ~ ${win.window_end}`:'—')}</span><small>Asia/Shanghai；遇周末/美股休市顺延至下一交易日。按 USD/CNY ${fx?fx.toFixed(4):'—'} 换算美元，IBKR 支持碎股。</small></div>
 <div class="ias-table-wrap"><table class="ias-table"><thead><tr><th>ETF</th><th>比例</th><th>人民币</th><th>约美元</th><th class="ias-hide-sm">最新价</th><th>约股数</th><th class="ias-hide-sm">已买</th></tr></thead><tbody>${rows}</tbody></table></div>
 ${plan?`<div class="ias-actions"><button data-ias-plan="completed" class="${plan.status==='completed'?'on':''}">标记已完成</button><button data-ias-plan="partial" class="${plan.status==='partial'?'on':''}">部分完成</button><button data-ias-plan="skipped" class="${plan.status==='skipped'?'on':''}">跳过本月</button>${plan.status!=='pending'?'<button data-ias-plan="pending" class="ghost">恢复待执行</button>':''}</div>`:''}
 <details class="ias-details"><summary>录入实际成交（股数 / 成交价 / 费用）</summary><form class="ias-form grid" data-ias-form="dca-exec"><label>ETF<select name="symbol">${split.map(x=>`<option>${esc(x.symbol)}</option>`).join('')}</select></label><label>股数<input name="shares" type="number" step="0.0001" min="0" required></label><label>成交价 USD<input name="price_usd" type="number" step="0.0001" min="0" required></label><label>费用 USD<input name="fee_usd" type="number" step="0.01" min="0" value="0"></label><label>USD/CNY<input name="usdcny" type="number" step="0.0001" min="0" value="${fx?fx.toFixed(4):''}"></label><label>日期<input name="executed_at" type="date" value="${today}"></label><button type="submit">保存成交</button></form></details>
 <h4 class="ias-h">累计与当前配置</h4><div class="ias-kvs">${kv('累计投入（USD）',usd(investedUsd,2),'含费用')}${kv('累计投入（CNY）',investedCny?cny(investedCny):'—','按成交时录入汇率')}${kv('当前市值',mvTotal?usd(mvTotal,0):'—','按最新收盘报价')}</div><ul class="ias-etf">${alloc||'<li>尚无成交记录</li>'}</ul>
 <h4 class="ias-h">每月历史</h4><div class="ias-table-wrap"><table class="ias-table"><thead><tr><th>月份</th><th>计划</th><th>状态</th><th>实际</th></tr></thead><tbody>${hist||'<tr><td colspan="4">暂无</td></tr>'}</tbody></table></div>
 <h4 class="ias-h">设置</h4>${settings}<h4 class="ias-h">提醒窗口</h4><ul class="ias-cal">${cal}</ul>
 <p class="ias-foot">每月只生成一个计划；确认完成/跳过后本月停止提醒。仅提醒与记录，不自动下单。${state.privateError?' · 私有数据读取异常：'+esc(state.privateError):''}</p>`;
}
function renderDrawer(){
 const el=drawerEl(),body=el.querySelector('.ias-drawer-body');
 el.querySelector('.ias-drawer').dataset.kind=state.drawer;
 body.innerHTML=state.drawer==='gold'?goldDrawer():dcaDrawer();
 body.querySelectorAll('form[data-ias-form]').forEach(f=>f.addEventListener('submit',onSubmit));
 body.querySelectorAll('[data-ias-plan]').forEach(b=>b.addEventListener('click',()=>setPlanStatus(b.dataset.iasPlan)));
}
function toast(msg,tone='good'){global.MAV?.toast?.(msg,tone)}
async function onSubmit(ev){
 ev.preventDefault();const f=ev.currentTarget,kind=f.dataset.iasForm,client=sb(),fd=Object.fromEntries(new FormData(f).entries());
 if(!client||!state.session)return;
 const uid=state.session.user.id,n=k=>fd[k]===''||fd[k]==null?null:Number(fd[k]);
 let res;
 if(kind==='gold-budget')res=await client.from('investment_plan_settings').upsert({user_id:uid,gold_budget_usd:n('gold_budget_usd'),updated_at:new Date().toISOString()},{onConflict:'user_id'});
 else if(kind==='dca-settings')res=await client.from('investment_plan_settings').upsert({user_id:uid,dca_monthly_cny:n('dca_monthly_cny'),updated_at:new Date().toISOString()},{onConflict:'user_id'});
 else if(kind==='gold-exec')res=await client.from('investment_executions').insert({user_id:uid,program:'gold',gold_stage:n('gold_stage'),gold_signal_id:state.status?.gold?.signal_id||null,symbol:fd.symbol,shares:n('shares'),price_usd:n('price_usd'),fee_usd:n('fee_usd')||0,usdcny:num(state.status?.gold?.fx?.usdcny),executed_at:fd.executed_at||null});
 else if(kind==='dca-exec'){if(!state.plan){toast('本月计划尚未生成','warn');return}res=await client.from('investment_executions').insert({user_id:uid,program:'dca',plan_id:state.plan.id,symbol:fd.symbol,shares:n('shares'),price_usd:n('price_usd'),fee_usd:n('fee_usd')||0,usdcny:n('usdcny'),executed_at:fd.executed_at||null})}
 if(res?.error){toast('保存失败：'+res.error.message,'bad');return}
 toast('已保存');await loadPrivate();render();
}
async function setPlanStatus(status){
 const client=sb();if(!client||!state.plan)return;
 const {error}=await client.from('dca_monthly_plans').update({status,status_updated_at:new Date().toISOString()}).eq('id',state.plan.id);
 if(error){toast('更新失败：'+error.message,'bad');return}
 toast({completed:'本月定投已完成',partial:'已标记部分完成',skipped:'本月已跳过',pending:'已恢复待执行'}[status]);await loadPrivate();render();
}

/* ---------- wiring (reuses market-live polling; no extra timers for quotes) ---------- */
function updateFromMarket(body){
 if(body?.gold&&!body.gold.error)state.live=body.gold;
 if(body?.usdcny&&!body.usdcny.error)state.liveFx=body.usdcny;
 render();
}
async function init(){
 render();await loadStatus();render();await loadPrivate();render();
 if(sb()?.auth?.onAuthStateChange)sb().auth.onAuthStateChange(()=>{loadPrivate().then(render)});
 setInterval(()=>{if(document.visibilityState==='visible')loadStatus().then(render)},10*60*1000);
}
const api={render,updateFromMarket,goldView,quoteFreshness,goldMarketOpen,stageFor,zoneFor,dcaSplit,dcaLabel,dcaPhase,windowText,cnyPerGram,_state:state};
global.MAVInvestActions=api;
if(typeof module!=='undefined'&&module.exports)module.exports=api;
else if(typeof document!=='undefined'){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init()}
})(typeof window!=='undefined'?window:globalThis);
