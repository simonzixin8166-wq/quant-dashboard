(function(){
'use strict';
// 学习进度：章程四项衡量，全部带分母；只读 research/learning_progress.json，不在浏览器里计算或升级状态。
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const frac=r=>r&&r.n?`${r.k}/${r.n} = ${Number(r.value).toFixed(2)}`:'不可用';
const ci=r=>r&&r.ci95?`<small>95% 区间 [${r.ci95[0].toFixed(2)}, ${r.ci95[1].toFixed(2)}]</small>`:'';
const ROLE={production:'生产',shadow:'影子',challenger:'对照',forum_shadow:'论坛影子'};
const STATUS={complete:'已测完',partial:'进行中'};
const CAT_STATUS={INSUFFICIENT:'样本不足',reportable_minimum_only:'达到最低报告门槛'};

function tile(label,value,sub){return `<article><span>${esc(label)}</span><b>${value}</b><small>${sub}</small></article>`}

function understanding(u){
  if(!u||u.status!=='ok')return `<p class="lp-unavailable">不可用</p>`;
  const rows=u.rows.map(r=>`<tr><td><b>${esc(r.extractor)}</b><small>${esc(ROLE[r.role]||r.role)}</small></td><td>${esc(r.set_label_zh||r.set)}<small>${esc(STATUS[r.status]||r.status)}${r.answered_posts?` · 已答 ${r.answered_posts} 篇`:''}</small></td><td>${frac(r.precision)}${ci(r.precision)}</td><td>${frac(r.recall)}${ci(r.recall)}</td><td>${esc(r.measured_at||'')}${r.note_zh?`<small>${esc(r.note_zh)}</small>`:''}</td></tr>`).join('');
  const dev=(u.dev_only||[]).map(d=>`<li>${esc(d.extractor)}（${esc(d.set)}）：精确率 ${d.precision}，召回率 ${d.recall}。${esc(d.note_zh||'')}</li>`).join('');
  return `<div class="journal-table-wrap"><table class="journal-table lp-table"><thead><tr><th>抽取器</th><th>测试集</th><th>精确率</th><th>召回率</th><th>测量日期</th></tr></thead><tbody>${rows}</tbody></table></div>${dev?`<p class="lp-note">只在开发集上测过（不作证据）：</p><ul class="lp-list">${dev}</ul>`:''}<p class="lp-note">${esc(u.note_zh||'')}</p>`;
}

function experience(e){
  if(!e||e.status!=='ok')return `<p class="lp-unavailable">不可用</p>`;
  const cats=(e.categories||[]).map(c=>`<tr><td>${esc(c.decision)}<small>${c.eligible?'符合入选条件':'不符合入选条件'}</small></td><td>${c.scored?`${c.hits}/${c.scored}`:(c.abstain?`弃权 ${c.abstain}，不计分`:'—')}</td><td>${esc(CAT_STATUS[c.status]||c.status)}</td></tr>`).join('');
  const hz=Object.entries(e.horizons||{}).map(([h,v])=>`<li>${h} 日：已到期 ${v.matured??'—'}${v.matured?'':`，最早 ${esc(v.earliest_maturity||'—')} 到期`}</li>`).join('');
  const p=e.promoted_separate||{};
  return `<ul class="lp-list">${hz}</ul><div class="journal-table-wrap"><table class="journal-table lp-table"><thead><tr><th>判断类别（20 日）</th><th>命中 / 已计分</th><th>状态</th></tr></thead><tbody>${cats}</tbody></table></div><p class="lp-note">${esc(e.note_zh||'')} 历史重建样本单独统计：命中 ${p.hits??'—'}/${p.scored??'—'}，不并入真实前瞻。</p>`;
}

function reliability(r){
  if(!r||r.status!=='ok')return `<p class="lp-unavailable">不可用</p>`;
  const rows=(r.series||[]).slice(-12).reverse().map(x=>`<tr><td>${esc(x.session)}</td><td>${x.observations??'—'}</td><td>${x.matured_20??'—'}</td><td>${x.scored_20??'—'}</td><td>${x.hits_20??'—'}</td><td>${x.production_recall==null?'—':Number(x.production_recall).toFixed(2)}</td></tr>`).join('');
  const a=r.attribution;
  const att=a?`<p class="lp-note">错误归因（${esc((a.sessions||[]).join('、'))} 入场）：已计分 ${a.scored}，未命中 ${a.misses}，归因覆盖 ${Math.round((a.coverage||0)*100)}%；主因 ${esc(Object.entries(a.misses_by_primary||{}).map(([k,v])=>`${k}×${v}`).join('，'))}。有效性：${a.investment_validity==='INSUFFICIENT'?'样本不足':esc(a.investment_validity)}。</p>`:'';
  const verdict=r.trend_state==='INSUFFICIENT'?`趋势：样本不足（已记录 ${r.weeks_recorded} 周，至少需要 ${r.min_weeks} 周）`:'趋势：只做描述，不作结论';
  return `<p><b>${verdict}</b></p><div class="journal-table-wrap"><table class="journal-table lp-table"><thead><tr><th>交易日</th><th>累计判断</th><th>20 日已到期</th><th>已计分</th><th>命中</th><th>生产召回率</th></tr></thead><tbody>${rows}</tbody></table></div>${att}<p class="lp-note">${esc(r.note_zh||'')}</p>`;
}

function render(root,d){
  const m=d.measures||{},u=m.understanding||{},j=m.judgments||{},e=m.experience||{},r=m.reliability||{};
  const prod=u.production;const h=e.h20||{};
  const tiles=[
    tile('1 · 理解是否正确',prod?frac(prod.recall).split(' = ')[1]:'不可用',prod?`生产 ${esc(prod.extractor)} 召回率（${prod.recall.k}/${prod.recall.n}），精确率 ${prod.precision.value.toFixed(2)}`:'没有冻结测试成绩'),
    tile('2 · 独立判断',j.observations??'不可用',j.status==='ok'?`${j.sessions} 个交易日；20 日到期 ${j.matured_20}，其中弃权 ${j.abstain_20}`:'不可用'),
    tile('3 · 已验证经验',h.scored??'不可用',e.status==='ok'?`20 日已计分（命中 ${h.hits}）；可报告类别 ${e.categories_reportable}/${e.categories_total}`:'不可用'),
    tile('4 · 是否更可靠',r.trend_state==='INSUFFICIENT'?'样本不足':'只描述',`已记录 ${r.weeks_recorded??0}/${r.min_weeks??4} 周`),
  ].join('');
  root.innerHTML=`<section class="hero compact-hero"><div><h1>学习进度 · 四项衡量</h1><p>每天收盘后自动更新，全部带分母。学习状态：<b>${esc(d.learning_state||'UNPROVEN')} / FINAL=${esc(d.final||'NO')}</b>。更新于 ${esc(String(d.generated_at||'').slice(0,16).replace('T',' '))} UTC。</p></div></section>
  <div class="journal-summary lp-summary">${tiles}</div>
  <section class="journal-panel"><div class="journal-head"><div><h2>1 · 理解是否正确</h2><p>冻结、未见过的测试集；单位：${esc(u.unit_zh||'帖子 × 股票代码')}；每个版本只测一次。</p></div></div>${understanding(u)}</section>
  <section class="journal-panel"><div class="journal-head"><div><h2>2 · 独立判断</h2><p>${esc(j.note_zh||'')}</p></div></div>${j.status==='ok'?`<ul class="lp-list"><li>${esc(j.first_session)} 至 ${esc(j.latest_session)}，${j.sessions} 个交易日，共 ${j.observations} 条判断；连续性 ${j.continuity==='ok'?'正常':esc(j.continuity)}，缺口 ${j.gaps} 个。</li><li>20 日已到期 ${j.matured_20} 条，弃权 ${j.abstain_20} 条，独立样本 ${j.independent_episodes_20} 个。</li></ul>`:'<p class="lp-unavailable">不可用</p>'}</section>
  <section class="journal-panel"><div class="journal-head"><div><h2>3 · 已验证经验</h2><p>只算真实前瞻且已到期的结果；截至 ${esc(e.as_of_session||'—')}。</p></div></div>${experience(e)}</section>
  <section class="journal-panel"><div class="journal-head"><div><h2>4 · 是否越来越可靠</h2><p>每个交易日一行，只追加；生产召回率只在冻结测试后才有。</p></div></div>${reliability(r)}</section>`;
}

function load(){
  const root=document.getElementById('learningProgressRoot');if(!root)return;
  fetch('research/learning_progress.json?v='+Date.now(),{cache:'no-store'})
    .then(r=>r.ok?r.json():Promise.reject(r.status))
    .then(d=>render(root,d))
    .catch(()=>{root.innerHTML='<section class="journal-panel"><h2>学习进度</h2><p class="lp-unavailable">数据不可用（不以旧数据代替）。</p></section>'});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',load);else load();
})();
