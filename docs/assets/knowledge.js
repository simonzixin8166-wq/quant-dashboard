(function(){
'use strict';
const root=document.getElementById('knowledgeRoot');if(!root)return;
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const link=(url,title)=>{try{const u=new URL(url);return /^https?:$/.test(u.protocol)?`<a href="${esc(u.href)}" target="_blank" rel="noopener noreferrer">${esc(title)}</a>`:esc(title)}catch{return esc(title)}};
let learning=false,section='etf',notes=[],methodMemory=null,sourceReading=null,sourceRuleLifecycle=null;
const tabs={etf:'核心ETF',process:'决策流程',methods:'方法库',research:'研究卡',events:'事件学习',review:'历史复盘',entry:'入仓检查'};
const etfs=[['QQQM','核心指数研究','跟踪纳斯达克100；不是全市场分散组合。','长期投入须接受成长股波动。回撤档位仅提示价格条件，还需核对投入期限和现金预算。','与VGT可能重叠，不能用“持有两只”推断已分散；精确重叠需同日持仓权重。','https://www.invesco.com/us/en/financial-products/etfs/invesco-nasdaq-100-etf.html'],['VGT','行业配置研究','美国信息技术行业ETF，行业集中度值得单独管理。','长期持有的前提是认可行业集中风险；并非科技相关公司都会纳入信息技术行业。','持有QQQM、VGT及科技个股时，应穿透检查同一公司的合计暴露。','https://investor.vanguard.com/investment-products/etfs/profile/vgt'],['QLD','杠杆卫星研究','目标是纳指100每日收益的2倍，长期收益并非固定2倍。','每日重置产生路径依赖；震荡与持续下跌可能放大损失，年度再平衡不能替代期间风险监控。','教学示例：指数先涨10%再跌9.09%，约回到原点；忽略费用的每日2倍组合约亏1.82%。','https://www.proshares.com/our-etfs/leveraged-and-inverse/qld']];
function detail(text){return `<details ${learning?'open':''}><summary>为什么 · 进一步学习</summary><p>${text}</p></details>`}
function methodEvidenceHtml(){
  const rows=(methodMemory?.methods||[]);
  if(!rows.length)return '<div class="kh-box"><h3>方法验证状态</h3><p class="kh-muted">等待 Method Memory 数据。</p></div>';
  const labels={context_only:'仅上下文',direct_early:'直接证据·早期',direct_developing:'直接证据·发展中',outcome_supportive:'结果支持',outcome_mixed:'结果混合',outcome_challenging:'结果挑战'};
  const cards=rows.map(m=>{
    const ev=m.evidence_maturity||{},p=m.performance||{},h20=p['20']||{},h60=p['60']||{};
    return `<article><span class="kh-tag">${esc(labels[ev.state||m.status]||ev.state||m.status||'待验证')}</span><h3>${esc(m.method||'方法')}</h3><p>Direct ${esc(m.direct_validated_events||0)} · Context ${esc(m.context_validated_events||0)}</p><p>20日成熟 ${esc(h20.n||0)} · 60日成熟 ${esc(h60.n||0)}</p><p class="kh-muted">Research Only · 状态由 Method Memory 自动更新，不自动修改正式交易规则。</p></article>`;
  }).join('');
  return `<div class="kh-box"><h2>方法验证状态 · 自动学习</h2><p>这是当前 Method Memory 的动态证据状态。文章主题只算 Context；只有明确操作语义和成熟结果才进入 Direct 验证。</p><p class="kh-muted">更新时间：${esc(methodMemory.generated_at||'—')} · Direct links ${esc(methodMemory.counts?.direct_method_links??0)}</p></div><div class="kh-grid">${cards}</div>`;
}
async function loadMethodMemory(){
  try{
    const r=await fetch('research/method_memory.json?v='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(10000)});
    if(!r.ok)throw Error();
    methodMemory=await r.json();
  }catch{methodMemory=null}
  if(section==='methods')render();
}
function sourceReadingRecordHtml(r){
  const props=Array.isArray(r?.propositions)?r.propositions:[];
  const order={testable_rule:0,trigger:1,invalidation:2,fact:3,author_view:4,non_testable_view:5};
  const selected=[...props].sort((a,b)=>(order[a.kind]??9)-(order[b.kind]??9)).slice(0,6);
  const labels={fact:'Fact',author_view:'Author View',trigger:'Trigger',invalidation:'Invalidation',testable_rule:'Testable Rule',non_testable_view:'Non-testable View'};
  const chips=selected.map(p=>`<p><span class="kh-tag">${esc(labels[p.kind]||p.kind||'Context')}</span> ${esc(p.text||'')}</p>`).join('');
  const meta=[r.author,r.source,r.published_at].filter(Boolean).map(esc).join(' · ');
  const state=r.testable_rule_count>0?'含可验证规则':'上下文记忆';
  return `<article class="kh-box"><p class="kh-muted">${meta||'来源信息不足'} · ${esc(state)}</p><h3>${r.url?link(r.url,r.title||'未命名来源'):esc(r.title||'未命名来源')}</h3>${chips||'<p class="kh-muted">暂无可展示命题。</p>'}</article>`;
}
function sourceReadingHtml(){
  const d=sourceReading||{},c=d.counts||{},k=c.by_kind||{};
  const lc=sourceRuleLifecycle||{},ls=lc.counts?.by_state||{};
  if(!d.version)return '<div class="kh-box"><h3>来源阅读记忆</h3><p class="kh-muted">等待 Source Reading Memory 数据。</p></div>';
  const lifecycle=lc.version?`<p><strong>规则生命周期：</strong>等待触发 ${esc(ls.awaiting_trigger??0)} · 已触发待成熟 ${esc(ls.triggered_pending??0)} · 5/20/60日成熟 ${esc((ls.mature_5??0)+(ls.mature_20??0)+(ls.mature_60??0))} · 期权不可评分 ${esc(ls.option_outcome_unscored??0)} · 映射异常 ${esc(ls.mapping_missing??0)}</p>`:'<p class="kh-muted">规则生命周期等待生成。</p>';
  const records=Array.isArray(d.records)?[...d.records]:[];
  records.sort((a,b)=>(b.testable_rule_count||0)-(a.testable_rule_count||0)||String(b.published_at||'').localeCompare(String(a.published_at||'')));
  const preview=records.slice(0,6).map(sourceReadingRecordHtml).join('');
  return `<div class="kh-box"><h2>来源阅读记忆 · V${esc(d.version)}</h2>
    <p>系统把已采集来源拆成事实、作者观点、触发条件、失效条件、可验证规则与不可验证观点；只有结构足够明确的规则才进入后续结果验证。</p>
    <p><strong>来源 ${esc(c.source_records??0)}</strong> · 命题 ${esc(c.propositions??0)} · 可验证规则 ${esc(c.testable_rules??0)} · 含规则来源 ${esc(c.records_with_testable_rules??0)}</p>
    ${lifecycle}
    <p class="kh-muted">Fact ${esc(k.fact??0)} · Author View ${esc(k.author_view??0)} · Trigger ${esc(k.trigger??0)} · Invalidation ${esc(k.invalidation??0)} · Testable Rule ${esc(k.testable_rule??0)} · Non-testable View ${esc(k.non_testable_view??0)}。Sell Put 触及行权价只算基础标的上下文，不等于期权盈利。Research Only，不自动改变交易规则。</p>
  </div>
  <div class="kh-box"><h3>来源拆解预览</h3><p class="kh-muted">优先展示含可验证规则的来源，其次按发布日期；每条来源最多展示6个命题，原文链接保留用于人工复核。</p></div>
  ${preview||'<div class="kh-box"><p class="kh-muted">暂无来源阅读记录。</p></div>'}`;
}
async function loadSourceReading(){
  try{
    const r=await fetch('research/source_reading_memory.json?v='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(10000)});
    if(!r.ok)throw Error();
    sourceReading=await r.json();
  }catch{sourceReading=null}
  if(section==='methods')render();
}
async function loadSourceRuleLifecycle(){
  try{
    const r=await fetch('research/source_rule_lifecycle.json?v='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(10000)});
    if(!r.ok)throw Error();
    sourceRuleLifecycle=await r.json();
  }catch{sourceRuleLifecycle=null}
  if(section==='methods')render();
}
function render(){const appVersion=document.body?.dataset?.appVersion||'5.1.1';root.innerHTML=`<header class="kh-head"><div><span class="kh-tag">MYALPHA VIEW / KNOWLEDGE / V${appVersion}</span><h1>先理解，再寻找机会</h1><p>指数为核心，个股与期权为辅助。每个判断都要有来源、条件与复盘。</p></div><button id="khMode" aria-pressed="${learning}">${learning?'知识模式':'简洁模式'} · 切换</button></header><nav class="kh-tabs" aria-label="学习栏目">${Object.entries(tabs).map(([k,v])=>`<button data-kh-tab="${k}" aria-selected="${k===section}">${v}</button>`).join('')}</nav><div id="khContent"></div>`;
root.querySelector('#khMode').onclick=()=>{learning=!learning;render()};root.querySelectorAll('[data-kh-tab]').forEach(b=>b.onclick=()=>{section=b.dataset.khTab;render()});const body=root.querySelector('#khContent');

if(section==='process')body.innerHTML=`<div class="kh-box"><h2>普通投资者的决策流程</h2><p>借鉴 BrightLine 反复强调的“先研究、先求生存、按概率和证据复盘”，但不复制个人仓位比例。本站把它压缩为 5 个可执行步骤。</p></div><div class="kh-grid"><article><span class="kh-tag">01 · CORE</span><h3>核心ETF先行</h3><p>QQQM / VGT / QLD 的长期规则与个股择时分开。市场没有触发额外回撤档位时，不因为一条新闻改变核心计划。</p><button data-go="tab-engine">查看核心ETF状态</button></article><article><span class="kh-tag">02 · THESIS</span><h3>个股先写论点</h3><p>为什么关注、催化剂是什么、最脆弱假设是什么、什么证据出现就说明判断错了。</p><button data-go="tab-stocks">查看观察池</button></article><article><span class="kh-tag">03 · CONFIRM</span><h3>趋势只做确认</h3><p>Trend Pulse 负责告诉你价格行为是否支持研究论点，而不是替代基本面，也不作为单独的机械买卖信号。</p><button data-go="tab-trend-pulse">查看趋势</button></article><article><span class="kh-tag">04 · LEVERAGE</span><h3>杠杆最后讨论</h3><p>没有建立论点，不使用 LEAP / Sell Put 放大方向判断。先知道最大损失、到期日、IV和事件风险。</p><button data-go="tab-options">查看期权风险</button></article><article><span class="kh-tag">05 · REVIEW</span><h3>结果必须进入复盘</h3><p>比较5/10/20/60日表现、最大回撤和QQQM基准。成功和失败都保留，避免只记住赚钱案例。</p><button data-go="tab-archive">查看历史归档</button></article></div>`;
if(section==='etf')body.innerHTML=`<div class="kh-grid">${etfs.map(([symbol,role,what,rule,risk,url])=>`<article><span class="kh-tag">${role}</span><h2>${symbol}</h2><p>${what}</p><p>${rule}</p>${detail(esc(risk))}<p>${link(url,'发行方资料 ↗')}</p></article>`).join('')}</div><p class="kh-muted">资料核对：2026-09-28。此处为产品机制学习，不提供实时持仓重叠率、估值或买入建议。</p>`;
if(section==='methods'){body.innerHTML=methodEvidenceHtml()+sourceReadingHtml()+`<div class="kh-box"><h2>从博主经验到本站规则</h2><p>来源 → 明确规则 → 找到边界 → 历史验证 → 模拟观察 → 决定是否采用。BrightLine 的公开文章用于启发研究框架，不会自动修改本站交易阈值。</p>${detail('验证至少包括：样本区间、信号次日可成交价格、交易成本、最大回撤、相对QQQM基准的超额收益；区分样本内与样本外，保留失败案例。')}</div><div class="kh-grid"><article><span class="kh-tag">已采用 · 核心层</span><h3>指数核心与个股辅助分层</h3><p>与“没有持续研究优势时指数优先”的思路一致。本站继续把QQQM/VGT/QLD和个股择时规则分开。</p><button data-go="tab-engine">核心ETF状态</button></article><article><span class="kh-tag">已采用 · 确认层</span><h3>Trend Pulse只做第二层证据</h3><p>价格趋势帮助确认或否定研究论点，但不会替代基本面与仓位纪律。</p><button data-go="tab-trend-pulse">趋势与验证</button></article><article><span class="kh-tag">增强中 · 个股层</span><h3>Thesis → 催化剂 → 失效条件</h3><p>个股研究卡必须说明“为什么、等什么、错在哪里”，避免亏损后把短线临时改成长线。</p><button data-go="tab-stocks">观察池</button></article><article><span class="kh-tag">增强中 · 风险层</span><h3>Survival Check</h3><p>检查杠杆、重大事件、失效条件和最坏结果；不复制任何博主的固定仓位比例。</p><button data-go="tab-options">期权风险</button></article><article><span class="kh-tag">已有数据 · 待丰富</span><h3>概率与复盘</h3><p>历史验证已经记录5/10/20/60日表现；后续统一增加最大回撤和相对QQQM表现。</p><button data-go="tab-archive">历史归档</button></article><article><span class="kh-tag">来源层</span><h3>BrightLine方法地图</h3><p>文学城模块已按“方法、边界、本站对应、待补能力”整理公开文章。</p><button data-go="tab-wenxuecity">打开文学城</button></article></div>`+form('method');wireForm(body,'method')}
if(section==='research'){body.innerHTML=`<div class="kh-box"><h2>个股研究卡</h2><p>先写可证伪的投资逻辑，再看技术信号。价格下跌本身不是估值便宜的证据。</p>${detail('催化剂必须区分已发生事实和预期。失效条件可包括订单取消、盈利指引下修、现金流持续恶化；具体阈值由研究证据决定。')}<button data-go="tab-stocks">查看观察池价格条件</button></div>`+form('research');wireForm(body,'research')}
if(section==='entry'){body.innerHTML=`<div class="kh-box"><h2>从“值得关注”到“可以评估入仓”</h2><p>检查表只检查准备程度，不预测上涨概率，也不会下单。</p><form id="khChecklist">${['行情时间与来源已核对','符合核心/卫星定位，不挤占核心ETF纪律','已写明投资论点（thesis）和主要催化剂','已写明什么证据出现就说明判断失效','已检查未来重大事件与跳空风险','若使用期权/杠杆，已明确到期、IV与最坏结果'].map(x=>`<label><input type="checkbox" style="display:inline;width:auto"> ${x}</label>`).join('')}<output aria-live="polite">准备项 0/6 · 继续研究</output></form>${detail('期权还需检查到期日、隐含波动率、买卖价差、最大损失、指派义务与退出规则。QLD单独检查杠杆暴露，不把核心ETF的回撤规则机械复制给杠杆产品。')}<div class="kh-actions"><button data-go="tab-engine">回撤策略</button><button data-go="tab-options">期权风险</button></div></div>`;body.querySelector('form').onchange=()=>{const n=body.querySelectorAll('input:checked').length;body.querySelector('output').textContent=`准备项 ${n}/6 · ${n===6?'可进一步评估，不代表买入信号':'继续研究'}`}}
if(section==='events'){body.innerHTML=`<div class="kh-grid"><article><h3>FOMC</h3><p>利率路径和政策表态影响折现率与风险偏好。决议与市场预期的差异，比单纯加息或降息更重要。</p>${detail('科技股并不对每次加息作相同反应；需要分开观察政策决定、声明与发布会。')}</article><article><h3>CPI</h3><p>通胀意外可能改变利率预期。方向不预设，重点比较实际值、预期值与结构。</p></article><article><h3>财报 / 公司事件</h3><p>利润、指引与市场预期共同影响股价。期权隐含波动率可能在事件后下降，即使看对方向仍可能亏损。</p><p class="kh-muted">公司事件尚未接入统一日历，请核对公司IR公告。</p></article></div><div class="kh-box"><h2>未来30天 · 北京时间</h2><div id="khEvents">读取现有事件数据…</div></div>`;loadEvents(body)}
if(section==='review')body.innerHTML=`<div class="kh-box"><h2>历史信号 ≠ 历史收益</h2><p>当前归档记录了信号日期、价格与回撤，但没有完整的5 / 10 / 20 / 60交易日后收益序列。这些结果暂不显示胜率。</p><div class="kh-table"><table><thead><tr><th>观察窗口</th><th>当前状态</th><th>下一步</th></tr></thead><tbody>${[5,10,20,60].map(n=>`<tr><td>${n}交易日</td><td>待补齐数据</td><td>次日入场基准、复权价格、成本与同周期基准</td></tr>`).join('')}</tbody></table></div>${detail('信号后的收益不能使用当日已知收盘信号假设成交于同一收盘价。未来窗口未结束标记“未成熟”，数据缺失不能记作0；同一轮连续信号应去重或单独说明样本相关性。')}<button data-go="tab-archive">打开现有历史归档</button></div>`;
body.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>window.openDashboardTab?.(b.dataset.go));}
const fields={method:[['name','方法名称'],['source','原始来源URL'],['date','原文发布日期'],['thesis','核心规则 / 触发条件'],['catalyst','适用市场'],['risk','不适用情况 / 风险'],['invalid','失效条件'],['validation','回测证据 / 未回测原因']],research:[['name','股票代码 / 名称'],['source','研究来源URL'],['date','研究日期'],['thesis','为什么关注'],['catalyst','主要催化剂及预计日期'],['risk','最大风险'],['invalid','判断失效条件'],['validation','下次核验内容']]};
function form(kind){return `<div class="kh-box"><h3>${kind==='method'?'新增待验证方法':'新增研究记录'}</h3><p class="kh-muted">记录仅在当前页面内存中，刷新或退出登录将清除；请导出备份。导入可恢复记录，不上传服务器。</p><form id="khForm">${fields[kind].map(([k,t])=>`<label>${t}<${['thesis','risk','invalid','validation','catalyst'].includes(k)?`textarea name="${k}" maxlength="3000" required></textarea>`:`input name="${k}" maxlength="500" type="${k==='date'?'date':k==='source'?'url':'text'}" required>`}</label>`).join('')}<button type="submit">保存到本次会话</button></form><div class="kh-actions"><button id="khExport">导出全部记录</button><label>导入JSON <input id="khImport" type="file" accept="application/json"></label></div><p id="khNotice" role="status"></p><div id="khNotes"></div></div>`}
function wireForm(body,kind){const show=()=>{body.querySelector('#khNotes').innerHTML=notes.filter(n=>n.kind===kind).map(n=>`<article><span class="kh-tag">用户研究记录 · 未经网站验证 / 未自动采用</span><h3>${esc(n.name)}</h3>${fields[kind].filter(([k])=>k!=='name').map(([k,t])=>`<p><b>${t}：</b>${k==='source'?link(n[k],n[k]):esc(n[k])}</p>`).join('')}</article>`).join('')};show();body.querySelector('#khForm').onsubmit=e=>{e.preventDefault();notes.push({kind,...Object.fromEntries(new FormData(e.target))});e.target.reset();show()};body.querySelector('#khExport').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify({version:1,notes},null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='myalpha-research.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};body.querySelector('#khImport').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>2000000)throw Error('文件超过2MB');const data=JSON.parse(await file.text());if(data.version!==1||!Array.isArray(data.notes)||data.notes.length>500)throw Error('格式或条目数量不符合要求');const clean=data.notes.map(n=>{if(!fields[n.kind])throw Error('未知记录类型');const out={kind:n.kind};for(const[k]of fields[n.kind]){if(typeof n[k]!=='string'||n[k].length>3000)throw Error('记录字段不合法');out[k]=n[k]}return out});notes=notes.concat(clean);show();body.querySelector('#khNotice').textContent=`已导入 ${clean.length} 条记录`}catch(err){body.querySelector('#khNotice').textContent='未导入：'+err.message}}}
async function loadEvents(body){const target=body.querySelector('#khEvents');try{const r=await fetch('data/market_events.json',{signal:AbortSignal.timeout(10000)});if(!r.ok)throw Error();const data=await r.json();const now=Date.now(),end=now+30*86400000;const rows=(data.events||[]).filter(e=>{const t=Date.parse(e.datetime);return t>=now&&t<=end}).sort((a,b)=>Date.parse(a.datetime)-Date.parse(b.datetime));target.innerHTML=`<p class="kh-muted">数据更新时间：${esc(data.updated_at||'未知')} · 来源状态：${esc(JSON.stringify(data.source_status||{}))}。日期请再次核对官方公告。</p>`+(rows.length?rows.map(e=>`<p><b>${esc(new Date(e.datetime).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'}))}</b> · ${link(e.source_url,e.title)}</p>`).join(''):'未来30天没有可用记录，不代表没有事件。')}catch{target.textContent='事件数据读取失败，请到官方日历核对。'}}
new MutationObserver(()=>{if(!document.body.classList.contains('private-mode')){notes=[];render()}}).observe(document.body,{attributes:true,attributeFilter:['class']});
render();loadMethodMemory();loadSourceReading();loadSourceRuleLifecycle();
})();
