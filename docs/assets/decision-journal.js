(function(global){
'use strict';
const KEY='mavDecisionJournalV56', OPERATOR_KEY='mavOperatorDecisionsV615', OLD_KEYS=['mavDecisionJournalV53','mavDecisionJournalV52','mavDecisionJournalV51'];
const endpoint='https://rhielbkvhgqbthcgztci.supabase.co/functions/v1/stock-market';
const H=[20,60,120];
const state={history:null,historyLoaded:false,lastAuthError:'',refreshing:false};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=v=>Number.isFinite(Number(v))?Number(v):null;
const pct=v=>num(v)===null?'—':`${Number(v)>=0?'+':''}${(Number(v)*100).toFixed(1)}%`;
const dateOnly=s=>String(s||'').slice(0,10);
const isWeekendDate=s=>{const d=Date.parse(`${dateOnly(s)}T12:00:00Z`);if(!Number.isFinite(d))return false;const w=new Date(d).getUTCDay();return w===0||w===6};
function latestCompleteMarketDate(candidates=[]){
  const dates=(candidates||[]).map(c=>dateOnly(c?.dailyAsOf)).filter(x=>/^\d{4}-\d{2}-\d{2}$/.test(x)&&!isWeekendDate(x));
  return dates.length?[...dates].sort().at(-1):null;
}
function mergeCandidate(dst,src){
  const out={...(dst||{}),...(src||{})};
  out.price=num(dst?.price)!==null?num(dst.price):num(src?.price);
  out.firstSeenAt=dst?.firstSeenAt||src?.firstSeenAt||src?.at||null;
  out.lastSeenAt=src?.lastSeenAt||src?.at||dst?.lastSeenAt||null;
  out.outcomes={...(dst?.outcomes||{}),...(src?.outcomes||{})};
  const transitions=[...(dst?.transitions||[]),...(src?.transitions||[])];
  const seen=new Set();out.transitions=transitions.filter(t=>{const k=`${t.at||''}|${t.fromDecision||''}|${t.toDecision||''}|${t.fromStage||''}|${t.toStage||''}`;if(seen.has(k))return false;seen.add(k);return true}).slice(-40);
  return out;
}
function consolidate(rows){
  const byDay=new Map();
  for(const row of Array.isArray(rows)?rows:[]){
    const day=dateOnly(row.date||row.at);if(!day)continue;
    let d=byDay.get(day);
    if(!d){d={...row,key:`${day}|daily`,date:day,candidates:[],scanCount:0};byDay.set(day,d)}
    d.scanCount=(d.scanCount||0)+Math.max(1,Number(row.scanCount)||1);
    d.at=row.at||d.at;d.level=row.level||d.level;d.mode=row.mode||d.mode;d.title=row.title||d.title;
    d.spx=num(row.spx)??d.spx;d.ixic=num(row.ixic)??d.ixic;d.vix=num(row.vix)??d.vix;
    const map=new Map((d.candidates||[]).map(x=>[x.symbol,x]));
    for(const cand of row.candidates||[])if(cand?.symbol)map.set(cand.symbol,mergeCandidate(map.get(cand.symbol),cand));
    d.candidates=[...map.values()];
    d.optionIdeas=[...(d.optionIdeas||[]),...(row.optionIdeas||[])].slice(-16);
  }
  return [...byDay.values()].sort((a,b)=>String(a.date).localeCompare(String(b.date)));
}
function read(){
  try{
    let rows=JSON.parse(localStorage.getItem(KEY)||'null');
    if(!Array.isArray(rows)){
      rows=[];
      for(const k of OLD_KEYS){const old=JSON.parse(localStorage.getItem(k)||'[]');if(Array.isArray(old)&&old.length){rows=old.map(x=>({...x,version:x.version||'migrated'}));break}}
    }
    const cleaned=rows.filter(x=>!isWeekendDate(x?.date||x?.at));
    if(cleaned.length!==rows.length||!localStorage.getItem(KEY))localStorage.setItem(KEY,JSON.stringify(cleaned));
    return cleaned;
  }catch{return []}
}
function write(rows){try{localStorage.setItem(KEY,JSON.stringify(consolidate(rows).slice(-300)))}catch{}}
function candidateDecision(c,classification){
  const stage=String(c.stage||'');
  if(/退潮|恶化/.test(stage))return '等待修复';
  if(/二次启动|启动|重新|修复中/.test(stage))return '修复候选';
  if(classification.mode==='fear')return '大跌机会候选';
  if(/钝化|高位/.test(stage))return '高位观察';
  return '继续观察';
}
function recordAssistantEvent({snapshot,classification,candidates=[],optionIdeas=[]}){
  const now=new Date().toISOString(),day=latestCompleteMarketDate(candidates);
  if(!day)return; // No confirmed new trading-day close: weekend/holiday/incomplete daily data must not create a sample.
  const eligible=(candidates||[]).filter(c=>dateOnly(c?.dailyAsOf)===day&&num(c?.dailyClose)!==null);
  if(!eligible.length)return;
  const rows=read();
  let daily=rows.find(x=>x.date===day);
  if(!daily){daily={key:`${day}|daily`,at:now,date:day,marketDateSource:'complete_daily_close',level:classification.level,mode:classification.mode,title:classification.title||'常态监测',spx:num(snapshot.spx),ixic:num(snapshot.ixic),vix:num(snapshot.vix),candidates:[],optionIdeas:[],source:'automatic-scan-v5.6',version:'5.6',scanCount:0};rows.push(daily)}
  daily.scanCount=(daily.scanCount||0)+1;daily.at=now;daily.level=classification.level;daily.mode=classification.mode;daily.title=classification.title||daily.title;daily.spx=num(snapshot.spx);daily.ixic=num(snapshot.ixic);daily.vix=num(snapshot.vix);daily.marketDateSource='complete_daily_close';
  const map=new Map((daily.candidates||[]).map(x=>[x.symbol,x]));
  for(const c of eligible.slice(0,8)){
    if(!c?.symbol)continue;
    const decision=candidateDecision(c,classification),prev=map.get(c.symbol),entry=num(c.dailyClose);
    if(!prev){
      map.set(c.symbol,{symbol:c.symbol,name:c.name||c.symbol,price:entry,latestPrice:num(c.price),priceSource:'complete_daily_close',dailyAsOf:day,score:num(c.score),stage:c.stage||'',zone:c.zone||'',hasThesis:Boolean(c.hasThesis),decision,outcomes:{},firstSeenAt:now,lastSeenAt:now,transitions:[]});
      continue;
    }
    const changed=prev.decision!==decision||String(prev.stage||'')!==String(c.stage||'');
    const transitions=[...(prev.transitions||[])];
    if(changed)transitions.push({at:now,fromDecision:prev.decision||'',toDecision:decision,fromStage:prev.stage||'',toStage:c.stage||''});
    map.set(c.symbol,{...prev,name:c.name||prev.name||c.symbol,price:prev.price??entry,latestPrice:num(c.price),priceSource:'complete_daily_close',dailyAsOf:day,score:num(c.score),stage:c.stage||'',zone:c.zone||'',hasThesis:Boolean(c.hasThesis),decision,lastSeenAt:now,transitions:transitions.slice(-40)});
  }
  daily.candidates=[...map.values()];
  daily.optionIdeas=(optionIdeas||[]).slice(0,8);
  write(rows);render();
}

function readOperatorDecisions(){
  try{
    const rows=JSON.parse(localStorage.getItem(OPERATOR_KEY)||'[]');
    return Array.isArray(rows)?rows:[];
  }catch{return []}
}
function recordOperatorDecision(entry={}){
  const now=new Date().toISOString(),date=dateOnly(entry.date||now);
  const row={
    at:now,last_seen_at:now,count:1,date,
    decision:String(entry.decision||'unknown'),
    source:String(entry.source||'daily_action_engine'),
    reason:String(entry.reason||''),
    data_state:String(entry.dataState||'unknown'),
    evidence_state:String(entry.evidenceState||'unknown'),
    fingerprint:String(entry.fingerprint||''),
    user_action:String(entry.userAction||'unrecorded'),
    attribution:String(entry.attribution||'pending'),
  };
  const rows=readOperatorDecisions();
  const key=[row.date,row.decision,row.source,row.fingerprint].join('|');
  const idx=rows.findIndex(x=>[x.date,x.decision,x.source,x.fingerprint].join('|')===key);
  if(idx>=0){
    rows[idx]={...rows[idx],last_seen_at:now,count:Math.max(1,Number(rows[idx].count)||1)+1,reason:row.reason||rows[idx].reason,data_state:row.data_state,evidence_state:row.evidence_state};
    try{localStorage.setItem(OPERATOR_KEY,JSON.stringify(rows.slice(-180)))}catch{}
    return rows[idx];
  }
  rows.push(row);
  try{localStorage.setItem(OPERATOR_KEY,JSON.stringify(rows.slice(-180)))}catch{}
  return row;
}

function updateOperatorDecision(fingerprint,userAction,attribution,note=''){
  const rows=readOperatorDecisions();
  const idx=rows.findIndex(x=>String(x.fingerprint||'')===String(fingerprint||''));
  if(idx<0)return false;
  const allowedActions=new Set(['executed','no_action','watch','deferred','unrecorded']);
  const allowedAttribution=new Set(['pending','system_error','user_decision_error','data_error','market_randomness','correct_process']);
  rows[idx]={...rows[idx],user_action:allowedActions.has(userAction)?userAction:'unrecorded',attribution:allowedAttribution.has(attribution)?attribution:'pending',operator_note:String(note||'').slice(0,300),operator_updated_at:new Date().toISOString()};
  try{localStorage.setItem(OPERATOR_KEY,JSON.stringify(rows.slice(-180)))}catch{}
  render();return true;
}
function operatorDecisionHtml(){
  const rows=readOperatorDecisions().slice(-12).reverse();
  if(!rows.length)return '<div class="journal-empty"><b>还没有操作决策记录</b><p>服务端 Action Engine 产生 action / no-action / cannot-judge 后会自动留下快照。</p></div>';
  const actionLabel={executed:'已执行',no_action:'决定不操作',watch:'继续观察',deferred:'推迟处理',unrecorded:'未记录'};
  const attrLabel={pending:'待归因',system_error:'系统判断错误',user_decision_error:'人工决策错误',data_error:'数据错误',market_randomness:'市场随机性',correct_process:'流程正确'};
  return '<div class="operator-decision-list">'+rows.map(x=>{
    const actionOptions=Object.entries(actionLabel).map(([k,v])=>'<option value="'+k+'" '+(x.user_action===k?'selected':'')+'>'+v+'</option>').join('');
    const attrOptions=Object.entries(attrLabel).map(([k,v])=>'<option value="'+k+'" '+(x.attribution===k?'selected':'')+'>'+v+'</option>').join('');
    return '<article class="operator-decision-card"><div><b>'+esc(x.date)+' · '+esc(x.decision)+'</b><span>'+esc(x.data_state)+' / '+esc(x.evidence_state)+'</span></div><p>'+esc(x.reason||'—')+'</p><div class="operator-decision-controls"><select data-operator-action="'+esc(x.fingerprint)+'">'+actionOptions+'</select><select data-operator-attr="'+esc(x.fingerprint)+'">'+attrOptions+'</select><button type="button" data-operator-save="'+esc(x.fingerprint)+'">保存</button></div>'+(x.operator_note?'<small>'+esc(x.operator_note)+'</small>':'')+'</article>';
  }).join('')+'</div>';
}
function bindOperatorDecisionControls(root){
  root.querySelectorAll('[data-operator-save]').forEach(btn=>btn.addEventListener('click',()=>{
    const fp=btn.dataset.operatorSave;
    const action=root.querySelector('[data-operator-action="'+CSS.escape(fp)+'"]')?.value||'unrecorded';
    const attr=root.querySelector('[data-operator-attr="'+CSS.escape(fp)+'"]')?.value||'pending';
    updateOperatorDecision(fp,action,attr);
    global.MAV?.toast?.('实际操作 / 归因已记录','good');
  }));
}

function supabase(){return global.mavSupabase||global.supabaseClient||null}
async function waitForAuth(timeout=10000){
  const start=Date.now();let sb=null;
  while(Date.now()-start<timeout){
    sb=supabase();if(sb?.auth?.getSession)return sb;
    await new Promise(r=>setTimeout(r,350));
  }
  throw new Error('登录组件初始化超时');
}
async function authHeaders(){
  const sb=await waitForAuth();
  const {data:{session}}=await sb.auth.getSession();
  if(!session)throw new Error('登录后才能补齐实时日志的个股结果');
  return {Authorization:`Bearer ${session.access_token}`,apikey:global.SUPABASE_ANON_KEY};
}
async function fetchHistory(symbols){
  if(!symbols.length)return {};
  const headers=await authHeaders(),out={};
  for(let i=0;i<symbols.length;i+=25){
    const chunk=symbols.slice(i,i+25);
    const r=await fetch(`${endpoint}?symbols=${encodeURIComponent(chunk.join(','))}&scope=history&t=${Date.now()}`,{headers,cache:'no-store',signal:AbortSignal.timeout(20000)});
    const b=await r.json();if(!r.ok||b.s!=='ok')throw new Error(b.error||`HTTP ${r.status}`);
    Object.assign(out,b.rows||{});
  }
  return out;
}
function outcomeFor(bars,eventDate,entryPrice){
  if(!Array.isArray(bars)||!bars.length||num(entryPrice)===null)return {};
  const start=bars.findIndex(x=>String(x.d)>=eventDate);if(start<0)return {};
  const res={};
  for(const h of H){const row=bars[start+h];if(row&&num(row.c)!==null)res[h]={date:row.d,price:num(row.c),return:num(row.c)/Number(entryPrice)-1};}
  const first20=bars.slice(start+1,start+21).map(x=>num(x.c)).filter(x=>x!==null);
  if(first20.length)res.mae20=Math.min(...first20)/Number(entryPrice)-1;
  return res;
}
function tradingProgress(bars,eventDate){
  if(!Array.isArray(bars)||!bars.length)return null;
  const start=bars.findIndex(x=>String(x.d)>=eventDate);if(start<0)return null;
  const last=bars.length-1;
  const elapsed=Math.max(0,last-start);
  return {elapsed,lastMarketDate:String(bars[last]?.d||'')};
}
function pendingCount(rows){let n=0;for(const e of rows)for(const c of(e.candidates||[]))if(num(c.price)!==null&&(!c.outcomes||!c.outcomes[120]))n++;return n}
async function refreshOutcomes({silent=false}={}){
  if(state.refreshing)return;state.refreshing=true;
  const rows=read(),pending=[];
  for(const e of rows)for(const c of(e.candidates||[]))if(num(c.price)!==null&&(!c.outcomes||!c.outcomes[120]))pending.push(c.symbol);
  const symbols=[...new Set(pending)];
  if(!symbols.length){state.refreshing=false;if(!silent)global.MAV?.toast?.('当前没有等待补齐的实时结果','good');render();return}
  try{
    const history=await fetchHistory(symbols);state.lastAuthError='';
    for(const e of rows)for(const c of(e.candidates||[])){const bars=history[c.symbol]?.bars;if(!bars)continue;c.outcomes={...(c.outcomes||{}),...outcomeFor(bars,e.date,c.price)};c.maturityProgress=tradingProgress(bars,e.date);c.lastValidatedAt=new Date().toISOString();}
    write(rows);if(!silent)global.MAV?.toast?.('实时 Journal 已补齐当前已成熟的结果','good');
  }catch(err){state.lastAuthError=String(err.message||err);if(!silent)global.MAV?.toast?.(`实时结果补齐暂不可用：${state.lastAuthError}`,'warn')}
  finally{state.refreshing=false;render()}
}
function matureStats(rows,h=20){
  const vals=[];for(const e of rows)for(const c of(e.candidates||[])){const r=c.outcomes?.[h]?.return;if(num(r)!==null)vals.push(num(r));}
  if(!vals.length)return {n:0,avg:null,positive:null};return {n:vals.length,avg:vals.reduce((a,b)=>a+b,0)/vals.length,positive:vals.filter(x=>x>0).length/vals.length};
}
function errorMemory(rows){
  const out=[];
  for(const e of rows)for(const c of(e.candidates||[])){
    const r20=num(c.outcomes?.[20]?.return),mae=num(c.outcomes?.mae20);if(r20===null)continue;
    const d=String(c.decision||'');
    if(/修复候选|大跌机会候选/.test(d)&&r20<=-0.08)out.push({type:'false-positive',symbol:c.symbol,date:e.date,decision:d,return20:r20,note:'候选升级后20日表现明显为负，后续应检查当时支持证据是否过弱。'});
    else if(/高位观察|等待修复|继续观察/.test(d)&&r20>=0.12)out.push({type:'missed-upside',symbol:c.symbol,date:e.date,decision:d,return20:r20,note:'谨慎判断后出现明显上涨，后续应检查是否缺少二次启动识别。'});
    else if(mae!==null&&mae<=-0.12)out.push({type:'large-adverse-move',symbol:c.symbol,date:e.date,decision:d,return20:r20,note:'入档后出现较大不利波动，作为风险识别样本保留。'});
  }
  return out.slice(-30).reverse();
}
function weeklySelfReview(rows){
  const matured=[];
  for(const e of rows)for(const c of(e.candidates||[])){
    const r20=num(c.outcomes?.[20]?.return);if(r20===null)continue;
    matured.push({date:e.date,symbol:c.symbol,decision:String(c.decision||''),stage:String(c.stage||''),return20:r20,mae20:num(c.outcomes?.mae20),transitions:(c.transitions||[]).length});
  }
  const recent=matured.slice(-40),errors=errorMemory(rows);
  let effective=0,noisy=0,missed=0;
  for(const x of recent){
    if(/修复候选|大跌机会候选/.test(x.decision)&&x.return20>=0.05)effective++;
    else if(/高位观察|等待修复|继续观察/.test(x.decision)&&x.return20<=0.03)effective++;
    if(x.transitions>=3&&Math.abs(x.return20)<0.03)noisy++;
    if(/高位观察|等待修复|继续观察/.test(x.decision)&&x.return20>=0.12)missed++;
  }
  const lessons=[];
  if(noisy>=2)lessons.push('同一标的频繁切换但20日结果变化有限：降低无新证据时的重复提醒优先级。');
  if(missed>=2)lessons.push('谨慎判断后仍出现明显上涨：加强“二次启动 / 成交量恢复 / 周趋势未破坏”的复核。');
  const falsePos=errors.filter(x=>x.type==='false-positive').length;
  if(falsePos>=2)lessons.push('候选升级后的无效样本偏多：后续提高支持证据门槛并增加反证检查。');
  if(!lessons.length&&recent.length)lessons.push('当前成熟样本尚未形成稳定偏差，继续收集，不主动改权重。');
  return{sample:recent.length,effective,noisy,missed,errorCount:errors.length,lessons,updatedAt:new Date().toISOString(),scope:'research-priority-only'};
}
function selfReviewHtml(rows){
  const r=weeklySelfReview(rows);
  if(!r.sample)return '<div class="journal-empty"><b>Weekly Self Review 等待成熟样本</b><p>至少需要20日结果成熟后，系统才会评价自己的判断，不会用未成熟结果提前“学习”。</p></div>';
  return `<div class="learning-summary"><article><span>成熟样本</span><b>${r.sample}</b><small>最近40条20日样本</small></article><article><span>判断有效</span><b>${r.effective}</b><small>符合当时判断方向</small></article><article><span>噪音候选</span><b>${r.noisy}</b><small>频繁变化但结果有限</small></article><article><span>错过上涨</span><b>${r.missed}</b><small>谨慎后20日涨幅≥12%</small></article></div><div class="learning-grid">${r.lessons.map((x,i)=>`<article class="learning-card"><div><b>What I learned #${i+1}</b><span>自动复盘</span></div><p>${esc(x)}</p><small>只影响研究优先级与提醒权重；不会自动改变核心ETF规则或下单。</small></article>`).join('')}</div>`;
}
function marketLabel(e){return e.level==='panic'?'极端':e.level==='fear'?'大跌':e.level==='watch'?'观察':e.mode==='greed'?'强势高位':'正常'}
function candidateRows(rows){const out=[];for(const e of[...rows].reverse())for(const c of(e.candidates||[]))out.push({e,c});return out.slice(0,40)}
async function loadJson(url){try{const r=await fetch(`${url}?v=${Date.now()}`,{cache:'no-store'});if(!r.ok)return null;return await r.json()}catch{return null}}
async function ensureHistory(){if(state.historyLoaded)return state.history;state.historyLoaded=true;state.history=await loadJson('research/historical_journal.json');setTimeout(()=>global.MAVInvestmentAssistant?.rescan?.(),0);return state.history}
function maturityHint(c,h){
  const elapsed=Math.max(0,Number(c?.maturityProgress?.elapsed)||0);
  const remaining=Math.max(0,h-elapsed);
  if(remaining===0)return `等待最新收盘结果入库`;
  const asOf=c?.maturityProgress?.lastMarketDate;
  return `还剩${remaining}个交易日${asOf?` · 已计至 ${asOf}`:''}`;
}
function outcomeCell(c,e,h){const r=c.outcomes?.[h];if(r)return `<span class="${num(r.return)>0?'pos-text':num(r.return)<0?'neg-text':''}">${pct(r.return)}</span><small>${esc(r.date||'')}</small>`;return `<span class="journal-pending">未成熟</span><small>${esc(maturityHint(c,h))}</small>`}
function validationHtml(data){
  if(!data)return `<div class="journal-empty"><b>历史市场规则验证等待生成</b><p>Daily Dashboard Update 会尝试运行市场提醒规则事件研究。期权 Delta/DTE 的真实历史收益不会用正股走势替代。</p></div>`;
  const groups=data.groups||[];
  return `<div class="journal-validation-grid">${groups.map(g=>`<article><div><b>${esc(g.label)}</b><span>${g.events}次事件</span></div><p>QQQ 20日平均 ${pct(g.forward?.['20']?.avg)} · 正收益 ${g.forward?.['20']?.positive_rate==null?'—':(g.forward['20'].positive_rate*100).toFixed(0)+'%'}</p><small>60日 ${pct(g.forward?.['60']?.avg)} · 20日最大不利波动均值 ${pct(g.mae20_avg)}</small></article>`).join('')}</div><p class="journal-method-note">这一块验证“市场级触发”；下面的本地历史学习则验证观察股 Trend Pulse / 动态阶段。二者分开，避免混淆。</p>`;
}
function stageProfileHtml(history){
  if(!history)return `<div class="journal-empty"><b>本地历史学习等待生成</b><p>把 STOOQ 历史包放入仓库后，Daily Dashboard Update 会自动生成 5 年状态样本并每天续写。</p></div>`;
  const profiles=history.profiles||{};const order=['二次启动','趋势启动','趋势延续','修复中','高位钝化','趋势退潮','趋势恶化'];
  return `<div class="learning-summary"><article><span>历史标的</span><b>${history.summary?.symbols??'—'}</b><small>本地 STOOQ 库</small></article><article><span>状态事件</span><b>${history.summary?.events??'—'}</b><small>5年因果回放</small></article><article><span>60日成熟</span><b>${history.summary?.mature_60??'—'}</b><small>可立即学习</small></article><article><span>120日成熟</span><b>${history.summary?.mature_120??'—'}</b><small>长期验证</small></article></div><div class="learning-grid">${order.map(stage=>{const p=profiles[stage]||{},s=p.horizons?.['60']||{},ev=p.evidence||{};return `<article class="learning-card ${esc(ev.level||'insufficient')}"><div><b>${esc(stage)}</b><span>${esc(ev.label||'样本不足')}</span></div><strong>${s.n||0} 个60日成熟样本</strong><p>平均 ${pct(s.avg)} · 中位 ${pct(s.median)} · 正收益 ${s.positive_rate==null?'—':(s.positive_rate*100).toFixed(0)+'%'}</p><small>平均MAE ${pct(s.mae_avg)} · MFE ${pct(s.mfe_avg)} · 相对QQQ ${pct(s.excess_vs_qqq_avg)} · 仅用于研究优先级</small></article>`}).join('')}</div>`;
}
function recentHistoryHtml(history){const rows=(history?.recent_events||[]).slice(0,18);if(!rows.length)return '';return `<details class="journal-history-details"><summary>查看最近历史状态样本</summary><div class="journal-table-wrap"><table class="journal-table"><thead><tr><th>日期</th><th>标的</th><th>状态</th><th>Pulse</th><th>20日</th><th>60日</th><th>120日</th></tr></thead><tbody>${rows.map(e=>`<tr><td>${esc(e.date)}</td><td><b>${esc(e.symbol)}</b><small>$${Number(e.price).toFixed(2)}</small></td><td>${esc(e.stage)}<small>${esc(e.zone||'')}</small></td><td>${Number(e.score)>0?'+':''}${Number(e.score).toFixed(0)}</td>${H.map(h=>`<td>${pct(e.outcomes?.[h]?.return)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></details>`}
let backtestCache=null;
async function render(error=''){
  const root=document.getElementById('decisionJournalRoot');if(!root)return;
  const rows=read(),candidateCount=rows.reduce((n,e)=>n+(e.candidates||[]).length,0),s20=matureStats(rows,20),s60=matureStats(rows,60),recent=candidateRows(rows),pending=pendingCount(rows);
  if(backtestCache===null)backtestCache=await loadJson('research/assistant_rule_validation.json');
  const history=await ensureHistory();
  root.innerHTML=`<section class="hero compact-hero"><div><h1>Decision Journal · 决策复盘</h1><p>两条证据链：历史回填立即学习 + 从今天起实时留痕。系统负责记录、验证和排序；投资者负责最终操作。</p></div><div class="journal-actions"><button type="button" onclick="MAVDecisionJournal.refreshOutcomes()">↻ 补齐实时成熟结果</button></div></section>
  <section class="journal-summary"><article><span>决策日</span><b>${rows.length}</b><small>同日同标的只保留一条主记录</small></article><article><span>等待成熟</span><b>${pending}</b><small>每条从首次入档日起算</small></article><article><span>实时20日成熟</span><b>${s20.n}</b><small>平均 ${pct(s20.avg)}</small></article><article><span>实时60日成熟</span><b>${s60.n}</b><small>平均 ${pct(s60.avg)}</small></article></section>
  ${error||state.lastAuthError?`<div class="journal-warning">${esc(error||state.lastAuthError)}。历史学习不依赖登录，仍可正常使用。</div>`:''}
  <section class="journal-panel"><div class="journal-head"><div><h2>自主学习 · 历史回填</h2><p>使用你提供的 STOOQ OHLCV，本地因果重放 Trend Pulse；不重复下载多年历史，也不使用未来数据。</p></div></div>${stageProfileHtml(history)}${recentHistoryHtml(history)}</section>
  <section class="journal-panel"><div class="journal-head"><div><h2>实时决策日志</h2><p>保存系统当时真实看到的环境和候选，防止事后改写。20 / 60 / 120均按各自入档交易日起算。</p></div><small>当前可补齐 ${pending===0?0:'部分'} 条</small></div>${recent.length?`<div class="journal-table-wrap"><table class="journal-table"><thead><tr><th>交易日</th><th>环境</th><th>标的 / 当时判断</th><th>收盘入档价</th><th>20日</th><th>60日</th><th>120日</th></tr></thead><tbody>${recent.map(({e,c})=>`<tr><td>${esc(e.date)}</td><td>${esc(marketLabel(e))}<small>VIX ${e.vix==null?'—':Number(e.vix).toFixed(1)}</small></td><td><b>${esc(c.symbol)}</b><small>${esc(c.decision)} · ${esc(c.stage||c.zone||'')}${(c.transitions||[]).length?` · 日内变化 ${(c.transitions||[]).length}次`:''}</small></td><td>${c.price==null?'—':'$'+Number(c.price).toFixed(2)}</td>${H.map(h=>`<td>${outcomeCell(c,e,h)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`:`<div class="journal-empty"><b>还没有实时记录</b><p>市场状态或候选发生有意义变化后会自动留下快照，不需要手工记录。</p></div>`}</section>
  <section class="journal-panel"><div class="journal-head"><div><h2>历史市场规则验证</h2><p>单独检查观察 / 大跌 / 极端市场触发，不与个股 Trend Pulse 样本混在一起。</p></div></div>${validationHtml(backtestCache)}</section>
  <section class="journal-panel"><div class="journal-head"><div><h2>Weekly Self Review · 每周自主复盘</h2><p>系统评价自己的历史判断、重复提醒和漏掉的行情，并把结论用于后续研究优先级。</p></div></div>${selfReviewHtml(rows)}</section>
  <section class="journal-panel"><div class="journal-head"><div><h2>Agent Error Memory · 错误记忆</h2><p>只记录已经有成熟结果的误报、漏掉上涨和大幅不利波动；它只调整研究权重，不自动修改核心策略。</p></div></div>${(()=>{const errs=errorMemory(rows);return errs.length?`<div class="learning-grid">${errs.slice(0,8).map(x=>`<article class="learning-card"><div><b>${esc(x.symbol)} · ${esc(x.type)}</b><span>${esc(x.date)}</span></div><strong>20日 ${pct(x.return20)}</strong><p>${esc(x.note)}</p><small>当时判断：${esc(x.decision)}</small></article>`).join('')}</div>`:'<div class="journal-empty"><b>暂无成熟错误样本</b><p>待20日结果成熟后自动归类，不会用未成熟样本提前“学习”。</p></div>'})()}</section>
  <section class="journal-panel"><div class="journal-head"><div><h2>实际操作与错误归因</h2><p>系统建议与最终人工决定分开保存；错误只能归为系统、人工、数据或市场随机性，不用结果好坏反推当时过程。</p></div></div>${operatorDecisionHtml()}</section>
  <section class="journal-panel journal-boundary"><h2>AI Agent 学习边界</h2><div><b>自动完成</b><p>历史回填、每日增量、结果成熟、样本统计、研究优先级、异常提醒和 QA。</p></div><div><b>必须由投资者决定</b><p>买卖、仓位、核心ETF阈值变更、把博主经验升级成正式规则。AI不会自动下单。</p></div></section>`;
  bindOperatorDecisionControls(root);
}
function learningForStage(stage){const p=state.history?.profiles?.[stage];if(!p)return null;return {...p.evidence,stats:p.horizons?.['60']||null}}
async function init(){render();setTimeout(()=>refreshOutcomes({silent:true}),4500)}
global.MAVDecisionJournal={recordAssistantEvent,recordOperatorDecision,updateOperatorDecision,refreshOutcomes,render,getJournal:read,getOperatorDecisions:readOperatorDecisions,getHistorical:()=>state.history,learningForStage,getErrorMemory:()=>errorMemory(read()),getSelfReview:()=>weeklySelfReview(read()),state};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})(window);
