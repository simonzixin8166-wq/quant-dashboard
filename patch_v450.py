from pathlib import Path
import re
root=Path('/mnt/data/v450_work')
p=root/'scripts/fetch_and_build.py'
s=p.read_text(encoding='utf-8')
s=s.replace('APP_VERSION = "4.4.0"','APP_VERSION = "4.5.0"').replace('ASSET_VERSION = "4.4.0"','ASSET_VERSION = "4.5.0"')
s=s.replace('assets/design-v4.4.css?v={ASSET_VERSION}','assets/design-v4.5.css?v={ASSET_VERSION}')

old='''    trend_cards=[]
    for sym,tp in trend_data.items():
        if not tp.get("available"): continue
        tone=tp.get("tone","neutral")
        integrity = tp.get("data_integrity") or {}
        isty = integrity.get("status","CHECK").lower()
        trend_cards.append(f\'\'\'<article class="trend-card" data-tone="{tone}"><div class="trend-card-top"><div><span>{html.escape(STOCK_META.get(sym,{}).get("name",sym))}</span><h3>{sym}</h3></div><div class="trend-score-xl {tone}">{tp.get("score",0):+.0f}</div></div><div class="trend-state {tone}">{html.escape(tp.get("state","-"))}</div><div class="trend-integrity integrity-{isty}">{html.escape(integrity.get("label","待校验"))} · {html.escape(str(integrity.get("as_of","-")))}</div><div class="trend-card-grid"><span>周线 <b>{html.escape(tp.get("weekly","-"))}</b></span><span>5日斜率 <b>{tp.get("slope5",0):+.1f}</b></span><span>Supertrend <b>{html.escape(tp.get("supertrend","-"))}</b></span><span>ADX <b>{fmt_num(tp.get("adx"),1)}</b></span><span>+DI / -DI <b>{fmt_num(tp.get("plus_di"),1)} / {fmt_num(tp.get("minus_di"),1)}</b></span><span>结构 <b>{html.escape(tp.get("structure","-"))}</b></span></div><p class="trend-analysis"><b>分析：</b>{html.escape(tp.get("analysis",""))}</p><p class="trend-guidance"><b>研究提示：</b>{html.escape(tp.get("guidance",""))}</p></article>\'\'\')
    trend_cards_html=''.join(trend_cards) or '<div class="trend-empty">等待趋势数据</div>'
'''
new='''    trend_action_map = {
        "趋势恶化": ("风险控制", "多周期同步转弱；优先控制风险，等待结构重新修复。", "risk"),
        "修复中": ("等待确认", "弱势正在改善，但尚未形成完整趋势确认；以观察为主。", "wait"),
        "趋势启动": ("重点观察", "趋势由弱转强，可进入重点观察区；等待持续性和回踩确认。", "watch"),
        "趋势延续": ("顺势跟踪", "主要趋势仍然延续；更适合跟踪趋势而非追逐单日波动。", "follow"),
        "二次启动": ("机会观察", "回踩后重新增强，属于再加速观察窗口；不等同于无条件追高。", "opportunity"),
        "高位钝化": ("避免追高", "趋势仍偏强，但边际动能下降；重点观察斜率是否重新上行。", "caution"),
        "趋势退潮": ("风险上升", "高位趋势开始明显转弱；应重新评估风险暴露和防守条件。", "risk"),
        "震荡观察": ("暂时等待", "多项趋势证据未形成一致方向；等待更明确的多周期共振。", "wait"),
    }
    trend_cards=[]
    for sym,tp in trend_data.items():
        if not tp.get("available"): continue
        tone=tp.get("tone","neutral")
        state_name=tp.get("state","震荡观察")
        action_label, action_desc, action_tone = trend_action_map.get(state_name,("暂时等待","当前趋势证据不足，继续观察。","wait"))
        integrity = tp.get("data_integrity") or {}
        isty = integrity.get("status","CHECK").lower()
        integrity_desc = "双源价格与关键日线数据一致，满足趋势计算要求；这只代表数据质量通过，不代表买入信号。" if isty == "pass" else "数据完整性尚未达到双源确认标准；趋势数值可参考，但不应据此形成操作结论。"
        trend_cards.append(f\'\'\'<article class="trend-card trend-card-v45" data-tone="{tone}"><div class="trend-card-top"><div><span>{html.escape(STOCK_META.get(sym,{}).get("name",sym))}</span><h3>{sym}</h3></div><div class="trend-score-xl {tone}">{tp.get("score",0):+.0f}</div></div><div class="trend-state-row"><span class="trend-state {tone}">{html.escape(state_name)}</span><span class="trend-action-chip {action_tone}" title="{html.escape(action_desc)}">{html.escape(action_label)}</span></div><div class="trend-card-grid"><span>周线 <b>{html.escape(tp.get("weekly","-"))}</b></span><span>5日斜率 <b>{tp.get("slope5",0):+.1f}</b></span><span>Supertrend <b>{html.escape(tp.get("supertrend","-"))}</b></span><span>ADX <b>{fmt_num(tp.get("adx"),1)}</b></span><span>+DI / -DI <b>{fmt_num(tp.get("plus_di"),1)} / {fmt_num(tp.get("minus_di"),1)}</b></span><span>结构 <b>{html.escape(tp.get("structure","-"))}</b></span></div><div class="trend-action-explain"><b>动作解释</b><span>{html.escape(action_desc)}</span></div><p class="trend-analysis"><b>分析：</b>{html.escape(tp.get("analysis",""))}</p><div class="trend-integrity integrity-{isty}" title="{html.escape(integrity_desc)}"><span>数据状态</span><strong>{html.escape(integrity.get("label","待校验"))}</strong><em>ⓘ</em><small>{html.escape(str(integrity.get("as_of","-")))}</small></div></article>\'\'\')
    trend_cards_html=''.join(trend_cards) or '<div class="trend-empty">等待趋势数据</div>'
'''
if old not in s: raise SystemExit('trend block not found')
s=s.replace(old,new)

old_stock='''<div id="tab-stocks" class="tab-pane"><section class="hero compact-hero"><div><h1>个股观察池</h1><p>按策略距离和风险状态自动排出关注顺序；登录后由Alpaca参考行情盘中更新，技术指标以最近完整收盘日线计算。</p></div><div class="stock-watch-actions"><span id="stockWatchStatus" class="stock-watch-status">公开版显示最近构建数据</span><button type="button" onclick="StockWatchlist.refresh()">↻ 刷新行情</button><button class="primary" type="button" onclick="StockWatchlist.openAdd()">＋ 新增个股</button></div></section>'''
new_stock='''<div id="tab-stocks" class="tab-pane"><section class="hero compact-hero stock-hero-v45"><div class="stock-hero-title"><h1>个股观察池</h1><p>按策略距离与趋势状态自动排序，盘中报价和完整收盘技术指标分开呈现。</p></div><div class="stock-hero-side"><div class="stock-hero-actions"><span class="stock-count-chip">{len([x for x in trend_data.values() if x.get("available")]) or len(STOCKS)}只</span><button type="button" onclick="StockWatchlist.refresh()">↻ 刷新行情</button><button class="primary" type="button" onclick="StockWatchlist.openAdd()">＋ 新增个股</button></div><span id="stockWatchStatus" class="stock-watch-status">公开版显示最近构建数据</span></div></section>'''
if old_stock not in s: raise SystemExit('stock block not found')
s=s.replace(old_stock,new_stock)

old_trend='''<div id="tab-trend-pulse" class="tab-pane"><section class="hero compact-hero"><div><h1>趋势脉冲</h1><p>跟踪“趋势正在变强还是变弱”，不预测明日价格。V1 使用价格结构、Supertrend、ADX/DI、MACD、RSI、量能与周线共振；与回撤加仓策略相互独立。</p></div></section><section class="section trend-feature"><div class="trend-feature-copy"><span class="trend-kicker">IREN · 重点跟踪</span><h2>多周期趋势状态</h2><p>{html.escape(iren_tp.get("analysis") or iren_tp.get("summary","等待趋势数据"))}</p><div class="trend-feature-advice"><b>研究提示</b><span>{html.escape(iren_tp.get("guidance","等待完整双源校验"))}</span></div><div class="trend-feature-metrics"><span>Pulse <b class="{iren_tp.get('tone','neutral')}">{iren_tp.get('score','—')}</b></span><span>状态 <b>{html.escape(iren_tp.get('state','—'))}</b></span><span>周线 <b>{html.escape(iren_tp.get('weekly','—'))}</b></span><span>结构 <b>{html.escape(iren_tp.get('structure','—'))}</b></span></div></div><div class="trend-chart-panel"><div class="trend-chart-head"><strong>IREN Trend Pulse</strong><span>-100 至 +100 · 最近90个交易日</span></div><canvas id="trendPulseChartIREN"></canvas></div></section>'''
new_trend='''<div id="tab-trend-pulse" class="tab-pane"><section class="hero compact-hero"><div><h1>趋势脉冲</h1><p>跟踪趋势强弱与变化速度，不预测明日价格。正式状态以最近完整收盘日线确认。</p></div></section><section class="section trend-feature trend-feature-v45"><div class="trend-chart-panel"><div class="trend-chart-head"><strong>IREN Trend Pulse</strong><span>-100 至 +100 · 最近90个交易日 · 柱状显示</span></div><canvas id="trendPulseChartIREN"></canvas></div><div class="trend-feature-copy"><span class="trend-kicker">IREN · 重点跟踪</span><h2>{html.escape(iren_tp.get('state','等待趋势数据'))}</h2><div class="trend-current-score"><span>当前 Pulse</span><strong class="{iren_tp.get('tone','neutral')}">{iren_tp.get('score','—')}</strong></div><div class="trend-feature-metrics"><span>5日斜率 <b>{iren_tp.get('slope5',0):+.1f}</b></span><span>20日斜率 <b>{iren_tp.get('slope20',0):+.1f}</b></span><span>周线 <b>{html.escape(iren_tp.get('weekly','—'))}</b></span><span>ADX <b>{fmt_num(iren_tp.get('adx'),1)}</b></span></div><div class="trend-feature-advice"><b>分析结果</b><span>{html.escape(iren_tp.get("analysis") or iren_tp.get("summary","等待趋势数据"))}</span></div><div class="trend-feature-advice secondary"><b>研究提示</b><span>{html.escape(iren_tp.get("guidance","等待完整双源校验"))}</span></div></div></section>'''
if old_trend not in s: raise SystemExit('trend feature block not found')
s=s.replace(old_trend,new_trend)

old_chart="""new Chart(canvas,{{type:'line',data:{{labels,datasets:[{{label:'Trend Pulse',data:values,borderColor:'#d71920',backgroundColor:'rgba(215,25,32,.07)',fill:true,borderWidth:2.4,pointRadius:0,tension:.28}}]}},options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},plugins:{{legend:{{display:false}}}},scales:{{x:{{grid:{{display:false}},ticks:{{maxTicksLimit:7}}}},y:{{min:-100,max:100,ticks:{{stepSize:50}},grid:{{color:'rgba(100,105,115,.12)'}}}}}}}}}});"""
new_chart="""new Chart(canvas,{{type:'bar',data:{{labels,datasets:[{{label:'Trend Pulse',data:values,backgroundColor:values.map(v=>v>10?'rgba(0,135,90,.78)':v<-10?'rgba(215,25,32,.76)':'rgba(104,112,123,.46)'),borderColor:values.map(v=>v>10?'#00875a':v<-10?'#d71920':'#68707b'),borderWidth:0,borderRadius:2,barPercentage:.82,categoryPercentage:.92}}]}},options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:(ctx)=>` Trend Pulse ${{Number(ctx.raw).toFixed(0)}}`}}}}}},scales:{{x:{{grid:{{display:false}},ticks:{{maxTicksLimit:7}}}},y:{{min:-100,max:100,ticks:{{stepSize:50}},grid:{{color:(ctx)=>ctx.tick&&ctx.tick.value===0?'rgba(21,23,26,.42)':'rgba(100,105,115,.12)',lineWidth:(ctx)=>ctx.tick&&ctx.tick.value===0?1.6:1}}}}}}}}}});"""
if old_chart not in s: raise SystemExit('chart line not found')
s=s.replace(old_chart,new_chart)

old_auth='''<div id="authOverlay" class="auth-overlay" hidden role="dialog" aria-modal="true" aria-labelledby="authDialogTitle" onclick="if(event.target===this)closeAuthModal()">
  <div class="auth-dialog">
    <button class="auth-close" type="button" onclick="closeAuthModal()" aria-label="关闭">×</button>
    <div class="auth-brand auth-brand-v44"><img src="assets/myalpha-logo-v44.png" alt="投资分析及策略 · Myalpha View"></div>
    <div class="auth-tabs"><button type="button" class="active" data-auth-tab="login" onclick="switchAuthTab('login')">登录</button><button type="button" data-auth-tab="register" onclick="switchAuthTab('register')">注册</button></div>
    <section id="authLoginPanel" class="auth-panel">
      <h2 id="authDialogTitle">欢迎回来</h2><p>使用已授权邮箱获取免密登录链接。私有策略、观察池和持仓继续由 Supabase RLS 保护。</p>
      <label class="auth-field"><span>邮箱地址</span><input id="authLoginEmail" type="email" autocomplete="email" placeholder="your@email.com" onkeydown="if(event.key==='Enter')submitAuthLogin()"></label>
      <button class="auth-primary" type="button" onclick="submitAuthLogin()">发送登录链接</button>
      <div id="authLoginStatus" class="auth-secondary-note">无需输入密码。登录链接仅发送到已授权账户。</div>
    </section>
    <section id="authRegisterPanel" class="auth-panel" hidden>
      <h2>申请访问</h2><p>目前私有功能仅开放授权账户。这里保留“注册”入口，但不会自动开放真实持仓或策略权限。</p>
      <label class="auth-field"><span>邮箱地址</span><input id="authRegisterEmail" type="email" autocomplete="email" placeholder="your@email.com"></label>
      <label class="auth-field"><span>用途 / 留言</span><input id="authRegisterNote" type="text" placeholder="例如：希望体验私有研究工具"></label>
      <button class="auth-primary" type="button" onclick="submitAccessRequest()">提交注册申请</button>
      <div id="authRegisterStatus" class="auth-secondary-note">点击后会打开你的邮件客户端，发送访问申请，不会自动授予私有权限。</div>
    </section>
    <div class="auth-contact">意见交流邮箱：<a href="mailto:xxj8166@gmail.com">xxj8166@gmail.com</a></div>
  </div>
</div>'''
new_auth='''<div id="authOverlay" class="auth-overlay" hidden role="dialog" aria-modal="true" aria-labelledby="authDialogTitle" onclick="if(event.target===this)closeAuthModal()">
  <div class="auth-dialog auth-dialog-v45">
    <aside class="auth-visual-v45">
      <div class="auth-brand auth-brand-v44"><img src="assets/myalpha-logo-v44.png" alt="投资分析及策略 · Myalpha View"></div>
      <div class="auth-visual-copy"><strong>私有研究工作区</strong><p>趋势、策略与持仓数据分层展示；真实持仓继续由 Supabase RLS 保护。</p></div>
      <div class="auth-trust-row"><span>收盘确认</span><span>双源校验</span><span>权限隔离</span></div>
      <div class="auth-contact">意见交流邮箱<br><a href="mailto:xxj8166@gmail.com">xxj8166@gmail.com</a></div>
    </aside>
    <div class="auth-form-v45">
      <button class="auth-close" type="button" onclick="closeAuthModal()" aria-label="关闭">×</button>
      <div class="auth-tabs"><button type="button" class="active" data-auth-tab="login" onclick="switchAuthTab('login')">登录</button><button type="button" data-auth-tab="register" onclick="switchAuthTab('register')">申请访问</button></div>
      <section id="authLoginPanel" class="auth-panel">
        <h2 id="authDialogTitle">欢迎回来</h2><p>使用已授权邮箱获取免密登录链接。</p>
        <label class="auth-field"><span>邮箱地址</span><input id="authLoginEmail" type="email" autocomplete="email" placeholder="your@email.com" onkeydown="if(event.key==='Enter')submitAuthLogin()"></label>
        <button class="auth-primary" type="button" onclick="submitAuthLogin()">发送登录链接</button>
        <div id="authLoginStatus" class="auth-secondary-note">无需密码；仅已授权账户可以进入私有模块。</div>
      </section>
      <section id="authRegisterPanel" class="auth-panel" hidden>
        <h2>申请访问</h2><p>提交邮箱和用途说明。申请不会自动获得真实持仓或策略权限。</p>
        <label class="auth-field"><span>邮箱地址</span><input id="authRegisterEmail" type="email" autocomplete="email" placeholder="your@email.com"></label>
        <label class="auth-field"><span>用途 / 留言</span><input id="authRegisterNote" type="text" placeholder="例如：希望体验研究工具"></label>
        <button class="auth-primary" type="button" onclick="submitAccessRequest()">提交申请</button>
        <div id="authRegisterStatus" class="auth-secondary-note">提交后打开邮件客户端，由主理人审核授权。</div>
      </section>
    </div>
  </div>
</div>'''
if old_auth not in s: raise SystemExit('auth block not found')
s=s.replace(old_auth,new_auth)
p.write_text(s,encoding='utf-8')

# Patch options row into compact card-in-row to avoid horizontal clipping.
op=root/'docs/assets/options-v2.js'
js=op.read_text(encoding='utf-8')
old_return=re.search(r"    return `<tr id=\"opt-row-\$\{x\.id\}\" class=\"option-position-row\">.*?</tr>`;",js)
if not old_return: raise SystemExit('options row return not found')
new_return='''    return `<tr id="opt-row-${x.id}" class="option-position-row option-position-card-row"><td colspan="9"><article class="option-position-card"><div class="option-card-main"><div class="option-contract"><strong>${x.symbol} $${Number(x.strike).toFixed(2)}</strong>${pending}<span>${strategy} · ${x.qty||1}张×${x.multiplier||100}</span></div><div class="option-expiry"><b>${x.expiry}</b><span>${dte} DTE · ${x.collateral_mode||'未标注担保'}</span></div><div class="option-pnl ${m?pnlClass:''}" title="${isReference?'基于上一有效报价，仅供参考':''}"><small>浮动盈亏</small><b>${m&&Number.isFinite(m.pnl)?pnlPrefix+money(m.pnl):'—'}</b><span>${m&&Number.isFinite(m.pnlPct)?pnlPrefix+pct(m.pnlPct):message}</span></div></div><div class="option-card-metrics"><div><small>建仓价</small><b>${money(Number(x.cost))}/股</b><span>总权利金 ${money(Number(x.cost)*(x.qty||1)*(x.multiplier||100))} · 费用 ${money(Number(x.open_fee||0))}</span></div><div><small>当前估值</small><b>${m&&Number.isFinite(m.mark)?money(m.mark):'—'}/股</b><span>${quoteDetail||message}</span>${quoteState}</div><div><small>Delta / IV</small><b>${Number.isFinite(shownDelta)?shownDelta.toFixed(3):'—'}</b><span>IV ${Number.isFinite(iv)?pct(iv):'—'}${!Number.isFinite(delta)&&Number.isFinite(manualDelta)?' · 手工收盘':''}</span></div><div><small>资金 / 有效价</small>${rocHtml}<span>平衡 ${money(m?.breakeven??(String(x.opt_type).toLowerCase()==='put'?Number(x.strike)-Number(x.cost):Number(x.strike)+Number(x.cost)))}${Number.isFinite(underlying)?` · 正股 ${money(underlying)}`:''}${Number.isFinite(distance)?` · ${pct(distance)}`:''}</span></div><div><small>风险状态</small><span class="risk-chip ${risk.level}${riskEscalationClass(x.id,risk.level)}" title="${eventText}">${risk.label}</span><span>${eventText}</span></div></div><div class="option-card-actions"><div class="position-inline-actions"><button type="button" onclick="OptionV2.editPosition('${x.id}')">编辑</button><button class="quick-delete-position" type="button" onclick="OptionV2.deletePosition('${x.id}')" title="仅用于删除重复或录入错误的持仓">删除</button></div><div><button onclick="OptionV2.refreshPosition('${x.id}')" title="刷新报价">↻ 刷新</button><button onclick="OptionV2.openPositionScenario('${x.id}')">推演</button>${rocButton}${rollButton}<button class="manage-option-btn" onclick="OptionV2.openLifecycle('${x.id}')">管理</button></div></div></article></td></tr>`;'''
js=js[:old_return.start()]+new_return+js[old_return.end():]
op.write_text(js,encoding='utf-8')

# New V4.5 stylesheet
css='''/* Myalpha View V4.5 — readability, decision semantics, compact research layout */
@import url('./design-v4.4.css?v=4.4.0');
:root{--action-watch:#2b5fb8;--action-wait:#697386;--action-opportunity:#00875a;--action-caution:#b66b00;--action-risk:#d71920}
/* Global rhythm: moderate headings, readable body */
.hero{padding:28px 30px!important;align-items:center!important}.hero h1{font-size:32px!important}.compact-hero h1{font-size:28px!important}.hero p{font-size:15.5px!important;line-height:1.65!important;margin-top:7px!important}.section{margin-top:26px!important}.section-head{margin-bottom:12px!important}.section-head h2{font-size:21px!important}.section-head p{font-size:13px!important}.table-container{max-width:100%;overflow-x:auto}
/* Stock header: two-row visual hierarchy */
.stock-hero-v45{display:grid!important;grid-template-columns:minmax(0,1fr) auto!important;gap:22px!important}.stock-hero-side{display:grid;justify-items:end;gap:10px}.stock-hero-actions{display:flex;align-items:center;gap:10px}.stock-count-chip{height:40px;display:inline-flex;align-items:center;padding:0 13px;border:1px solid var(--line);border-radius:999px;background:#f5f6f8;font-weight:750;color:#30343a}.stock-watch-actions button,.stock-hero-actions button{min-height:40px;padding:0 14px!important;border-radius:7px!important;font-size:14px!important}.stock-watch-status{font-size:13px!important;max-width:520px;text-align:right;line-height:1.45}
/* Trend cards: state first, data integrity last */
.trend-card-v45{padding:20px!important}.trend-card-top h3{font-size:23px!important}.trend-score-xl{font-size:38px!important}.trend-state-row{display:flex;align-items:center;gap:8px;margin:10px 0 14px;flex-wrap:wrap}.trend-state{margin:0!important}.trend-action-chip{display:inline-flex;align-items:center;min-height:30px;padding:0 10px;border-radius:5px;font-size:12px;font-weight:800;border:1px solid transparent}.trend-action-chip.watch{background:#edf3ff;color:var(--action-watch);border-color:#d4e2ff}.trend-action-chip.wait{background:#f2f4f6;color:var(--action-wait);border-color:#e1e5e9}.trend-action-chip.opportunity,.trend-action-chip.follow{background:#e8f6f0;color:var(--action-opportunity);border-color:#d1eadf}.trend-action-chip.caution{background:#fff3df;color:var(--action-caution);border-color:#f2dfba}.trend-action-chip.risk{background:#fff0f0;color:var(--action-risk);border-color:#f5d4d5}.trend-card-grid{grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:0!important;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}.trend-card-grid span{padding:10px 6px!important;font-size:13px!important}.trend-card-grid b{display:block;margin-top:3px;font-size:14px!important}.trend-action-explain{margin:14px 0 10px;padding:11px 12px;border-left:3px solid #2b5fb8;background:#f7f9fc;display:grid;gap:3px}.trend-action-explain b{font-size:12px}.trend-action-explain span{font-size:13px;line-height:1.55;color:#545b65}.trend-analysis{font-size:13.5px!important;line-height:1.65!important;margin-top:10px!important}.trend-guidance{display:none!important}.trend-integrity{margin-top:13px!important;padding-top:11px!important;border-top:1px solid var(--line);display:flex!important;align-items:center;gap:7px!important;font-size:12px!important}.trend-integrity span{color:var(--muted)}.trend-integrity strong{font-weight:800}.trend-integrity em{font-style:normal;color:#89919c;cursor:help}.trend-integrity small{margin-left:auto;color:var(--muted);font-size:11px}
/* Trend feature: chart dominant + compact context */
.trend-feature-v45{grid-template-columns:minmax(0,1.65fr) minmax(280px,.75fr)!important;gap:18px!important;align-items:stretch!important}.trend-chart-panel{min-height:390px!important;padding:22px!important}.trend-chart-panel canvas{max-height:315px!important}.trend-chart-head strong{font-size:18px!important}.trend-chart-head span{font-size:12px!important}.trend-feature-copy{padding:22px!important}.trend-feature-copy h2{font-size:25px!important;margin:6px 0 14px!important}.trend-current-score{display:flex;align-items:end;justify-content:space-between;padding:13px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}.trend-current-score span{font-size:13px;color:var(--muted)}.trend-current-score strong{font-size:36px;line-height:1}.trend-feature-metrics{grid-template-columns:1fr 1fr!important;gap:0!important;margin-top:8px!important}.trend-feature-metrics span{padding:10px 0;border-bottom:1px solid var(--line);font-size:12px!important}.trend-feature-metrics b{display:block;margin-top:3px;font-size:14px}.trend-feature-advice{margin-top:14px!important;padding:12px!important;border-radius:5px!important}.trend-feature-advice b{font-size:12px!important}.trend-feature-advice span{font-size:13px!important;line-height:1.55!important}.trend-feature-advice.secondary{background:#f5f6f8!important;border-color:#e2e5e9!important}
/* Options: no wide 9-column clipping */
.option-positions-table{overflow:visible!important;border:0!important;background:transparent!important}.option-positions-table table{min-width:0!important;width:100%!important}.option-positions-table thead{display:none}.option-position-card-row>td{padding:0 0 12px!important;border:0!important;min-width:0!important}.option-position-card{border:1px solid var(--line);border-radius:8px;background:#fff;overflow:hidden}.option-card-main{display:grid;grid-template-columns:minmax(210px,1.2fr) minmax(180px,.8fr) minmax(180px,.8fr);gap:18px;padding:17px 18px 13px;align-items:center}.option-contract,.option-expiry,.option-pnl{display:grid;gap:4px}.option-contract strong,.option-expiry b,.option-pnl b{font-size:18px!important}.option-contract span,.option-expiry span,.option-pnl span{font-size:12.5px;color:var(--muted)}.option-pnl small,.option-card-metrics small{font-size:11px;color:var(--muted);font-weight:700}.option-card-metrics{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));border-top:1px solid var(--line);border-bottom:1px solid var(--line);background:#fafbfc}.option-card-metrics>div{padding:12px 14px;min-width:0;border-right:1px solid var(--line);display:grid;align-content:start;gap:4px}.option-card-metrics>div:last-child{border-right:0}.option-card-metrics b,.option-card-metrics .roc-chip,.option-card-metrics .risk-chip{font-size:14px!important}.option-card-metrics span{font-size:11.5px!important;line-height:1.45;color:var(--muted);overflow-wrap:anywhere}.option-card-actions{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 16px}.option-card-actions>div{display:flex;gap:8px;flex-wrap:wrap}.option-card-actions button{min-height:32px;padding:0 9px!important;border-radius:5px!important}.option-account-group td{border-radius:7px!important;padding:10px 14px!important}.option-pnl-total{grid-template-columns:repeat(4,minmax(0,1fr))!important}.option-pnl-stat{padding:10px 12px!important}.option-pnl-stat strong{font-size:18px!important}
/* Auth: balanced 2-column brokerage-style workspace */
.auth-overlay{padding:24px!important;background:rgba(20,24,31,.42)!important;backdrop-filter:blur(6px)}.auth-dialog-v45{width:min(900px,calc(100vw - 48px))!important;display:grid;grid-template-columns:340px minmax(0,1fr);overflow:hidden;border:1px solid #d9dde2!important;border-radius:12px!important;background:#fff!important}.auth-visual-v45{padding:32px 28px;display:flex;flex-direction:column;background:linear-gradient(180deg,#fafbfc,#f4f6f8);border-right:1px solid #e1e4e8;min-height:500px}.auth-brand-v44{margin:0!important}.auth-brand-v44 img{width:100%!important;max-width:280px!important}.auth-visual-copy{margin-top:34px}.auth-visual-copy strong{font-size:21px}.auth-visual-copy p{margin-top:10px;font-size:14px;line-height:1.7;color:#646b75}.auth-trust-row{display:flex;flex-wrap:wrap;gap:7px;margin-top:20px}.auth-trust-row span{font-size:11.5px;font-weight:700;color:#5d6470;background:#fff;border:1px solid #dfe3e8;border-radius:999px;padding:6px 9px}.auth-visual-v45 .auth-contact{margin-top:auto;padding:22px 0 0!important;border-top:1px solid #dfe3e8!important;text-align:left!important;line-height:1.7}.auth-form-v45{position:relative;min-width:0}.auth-form-v45 .auth-tabs{padding:18px 58px 0 34px;border:0!important;gap:20px;justify-content:start;display:flex!important}.auth-form-v45 .auth-tabs button{height:48px!important;padding:0 3px!important;background:transparent!important;font-size:15px!important;border-bottom-width:2px!important}.auth-form-v45 .auth-panel{padding:28px 38px 38px!important}.auth-form-v45 .auth-panel h2{font-size:27px!important}.auth-form-v45 .auth-panel>p{font-size:14px!important;margin-bottom:18px!important}.auth-field{margin-top:16px!important}.auth-field span{font-size:13.5px!important}.auth-field input{height:50px!important;border-radius:6px!important}.auth-primary{height:50px!important;border-radius:6px!important;margin-top:20px!important}.auth-secondary-note{font-size:12.5px!important;padding:12px 13px!important;margin-top:14px!important}.auth-close{z-index:2;top:15px!important;right:15px!important}
@media(max-width:1050px){.trend-feature-v45{grid-template-columns:1fr!important}.trend-chart-panel{min-height:350px!important}.option-card-metrics{grid-template-columns:repeat(3,1fr)}.option-card-metrics>div:nth-child(3){border-right:0}.option-card-metrics>div:nth-child(-n+3){border-bottom:1px solid var(--line)}}
@media(max-width:760px){.hero{padding:22px 20px!important}.stock-hero-v45{grid-template-columns:1fr!important}.stock-hero-side{justify-items:start}.stock-hero-actions{flex-wrap:wrap}.stock-watch-status{text-align:left}.trend-card-grid{grid-template-columns:repeat(2,1fr)!important}.trend-chart-panel{min-height:320px!important;padding:16px!important}.option-card-main{grid-template-columns:1fr 1fr}.option-pnl{grid-column:1/-1;padding-top:10px;border-top:1px solid var(--line)}.option-card-metrics{grid-template-columns:1fr 1fr}.option-card-metrics>div{border-right:0!important;border-bottom:1px solid var(--line)}.option-card-actions{align-items:flex-start;flex-direction:column}.auth-overlay{padding:12px!important}.auth-dialog-v45{width:min(560px,100%)!important;grid-template-columns:1fr!important;max-height:calc(100vh - 24px);overflow:auto}.auth-visual-v45{min-height:auto;padding:22px;border-right:0;border-bottom:1px solid #e1e4e8}.auth-brand-v44 img{max-width:230px!important}.auth-visual-copy{display:none}.auth-trust-row{margin-top:14px}.auth-visual-v45 .auth-contact{display:none}.auth-form-v45 .auth-tabs{padding:10px 48px 0 22px}.auth-form-v45 .auth-panel{padding:22px!important}}
@media(max-width:520px){.hero h1{font-size:28px!important}.compact-hero h1{font-size:25px!important}.trend-card-grid{grid-template-columns:1fr 1fr!important}.option-card-main{grid-template-columns:1fr}.option-expiry,.option-pnl{grid-column:1}.option-card-metrics{grid-template-columns:1fr}.auth-trust-row{display:none}}
'''
(root/'docs/assets/design-v4.5.css').write_text(css,encoding='utf-8')

# update SW, manifest references/version
sw=root/'docs/sw.js'
if sw.exists():
    x=sw.read_text(encoding='utf-8').replace('4.4.0','4.5.0').replace('design-v4.4.css?v=4.5.0','design-v4.5.css?v=4.5.0')
    sw.write_text(x,encoding='utf-8')
man=root/'docs/manifest.webmanifest'
if man.exists():
    x=man.read_text(encoding='utf-8')
    man.write_text(x,encoding='utf-8')

# tests
bt=root/'tests/test_build_contract.py'
t=bt.read_text(encoding='utf-8').replace('"4.4.0"','"4.5.0"').replace('design-v4.4.css','design-v4.5.css')
bt.write_text(t,encoding='utf-8')

# Upgrade doc
(root/'UPGRADE_V4.5.md').write_text('''# myAlpha View V4.5.0\n\n## Focus\n- Rebalance typography and module density instead of simply enlarging fonts.\n- Stock watch header becomes two-level: title/actions first, update semantics second.\n- Trend Pulse line chart becomes signed bar chart around zero.\n- Every Trend Pulse state now has a fixed research-action interpretation.\n- Data integrity is visually separated from trend direction; PASS means data quality, not a buy signal.\n- Options open positions become responsive record cards so no right-side columns are clipped.\n- Login/Access request is rebuilt as a balanced two-column research-workspace modal.\n\n## Strategy safety\nTrend Pulse formula, ETF tier thresholds, backtest logic and data-integrity gate are unchanged.\n''',encoding='utf-8')
print('patched V4.5.0')
