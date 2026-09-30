(function(global){
  'use strict';
  const $=id=>document.getElementById(id);
  const state={publicData:null,lastRender:0};
  const MEMORY_KEY='mavAgentDecisionMemoryV56';

  function n(v){const x=Number(v);return Number.isFinite(x)?x:null}
  function pct(v,d=0){return Number.isFinite(Number(v))?(Number(v)*100).toFixed(d)+'%':'—'}
  function money(v){return Number.isFinite(Number(v))?'$'+Number(v).toFixed(2):'—'}
  function esc(v){return String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
  function rank(level){return({quiet:0,watch:1,review:2,action:3})[level]??0}
  function readMemory(){try{return JSON.parse(localStorage.getItem(MEMORY_KEY)||'{}')||{}}catch{return {}}}
  function writeMemory(v){try{localStorage.setItem(MEMORY_KEY,JSON.stringify(v))}catch{}}
  function decisionSignature(item){return [item.kind,item.symbol,item.decision||'',item.level||'',item.timing||''].join('|')}
  function trackDecision(item){const mem=readMemory(),key=(item.kind==='option'?'option:':'stock:')+(item.id||item.symbol),prev=mem[key],sig=decisionSignature(item),changed=Boolean(prev&&prev.signature!==sig);mem[key]={signature:sig,decision:item.decision||'',level:item.level||'',timing:item.timing||'',at:new Date().toISOString()};writeMemory(mem);return{changed,previous:prev||null}}
  function levelLabel(level){return({quiet:'无需处理',watch:'观察',review:'需要复查',action:'需要处理'})[level]||level}

  async function loadPublic(){
    try{
      const r=await fetch('research/autonomous_agent.json?v='+Date.now(),{cache:'no-store'});
      state.publicData=r.ok?await r.json():null;
    }catch{state.publicData=null}
  }

  function optionMark(position,quote){
    const short=String(position.side||'').toLowerCase()==='short';
    const bid=n(quote?.bid),ask=n(quote?.ask),mid=n(quote?.mid),last=n(quote?.last);
    return short?(ask??mid??last):(bid??mid??last);
  }

  function optionMetrics(position,quote){
    const mark=optionMark(position,quote),cost=n(position.cost)||0,qty=Math.max(1,n(position.qty)||1),mult=Math.max(1,n(position.multiplier)||100);
    const short=String(position.side||'').toLowerCase()==='short';
    const pnl=mark===null?null:(short?cost-mark:mark-cost)*qty*mult;
    const base=cost*qty*mult;
    const pnlPct=pnl!==null&&base>0?pnl/base:null;
    const bid=n(quote?.bid),ask=n(quote?.ask),mid=n(quote?.mid);
    const spread=bid!==null&&ask!==null&&mid!==null&&mid>0?(ask-bid)/mid:null;
    const delta=n(quote?.delta),iv=n(quote?.iv),spot=n(quote?.underlyingPrice);
    const dte=Math.round((new Date(position.expiry+'T20:00:00Z')-new Date())/86400000);
    return{mark,pnl,pnlPct,spread,delta,iv,spot,dte};
  }

  function remainingEdge(position,m,nearEvents=[],immediateEvents=[]){
    const short=String(position.side||'').toLowerCase()==='short',type=String(position.opt_type||'').toLowerCase();
    const absDelta=m.delta===null?null:Math.abs(m.delta),capture=m.pnlPct,remaining=capture===null?null:Math.max(0,1-capture);
    const assignment=String(position.assignment_mode||'accept').toLowerCase();
    let score=50;const positives=[],risks=[];
    if(short&&remaining!==null){score+=Math.min(18,remaining*30);positives.push('剩余可赚约 '+pct(remaining,0)+' 原始权利金')}
    if(absDelta!==null){if(absDelta<=0.15){score+=12;positives.push('|Delta| '+absDelta.toFixed(2)+' 较低')}else if(absDelta>=0.35){score-=18;risks.push('|Delta| '+absDelta.toFixed(2)+' 较高')}}
    if(Number.isFinite(m.dte)){if(m.dte>=30){score+=8;positives.push('DTE '+m.dte+'，时间仍充足')}else if(m.dte<=7){score-=20;risks.push('仅剩 '+m.dte+' DTE')}else if(m.dte<=21){score-=8;risks.push('进入 '+m.dte+' DTE 临期区')}}
    if(m.spread!==null){if(m.spread<=0.12){score+=8;positives.push('价差约 '+pct(m.spread,0)+'，执行成本可控')}else if(m.spread>0.20){score-=12;risks.push('价差约 '+pct(m.spread,0)+' 偏宽')}}
    if(immediateEvents.length){score-=18;risks.push('未来2天存在事件风险')}else if(nearEvents.length){score-=10;risks.push('未来7天存在事件风险')}
    if(short&&type==='put'&&assignment==='avoid'&&absDelta!==null&&absDelta>=0.30){score-=12;risks.push('不愿接货且行权风险上升')}
    if(capture!==null&&capture>=0.80){score-=15;risks.push('主要权利金已兑现')}
    score=Math.max(0,Math.min(100,Math.round(score)));
    return{score,label:score>=75?'高':score>=55?'中高':score>=40?'中':score>=25?'偏低':'低',positives,risks,remainingPremiumRatio:remaining};
  }
  function daysUntilEvent(event){
    const d=new Date(event?.datetime);
    if(Number.isNaN(d.getTime()))return null;
    return Math.ceil((d-new Date())/86400000);
  }

  function optionAdvice(position,quote){
    const m=optionMetrics(position,quote),side=String(position.side||'').toLowerCase(),type=String(position.opt_type||'').toLowerCase();
    const short=side==='short',absDelta=m.delta===null?null:Math.abs(m.delta),strike=n(position.strike),events=global.OptionV2?.getEvents?.()||[];
    const eventRows=events.map(e=>({event:e,days:daysUntilEvent(e)})).filter(x=>x.days!==null&&x.days>=0&&x.days<=Math.max(0,m.dte));
    const nearEvents=eventRows.filter(x=>x.days<=7);
    const immediateEvents=eventRows.filter(x=>x.days<=2);
    const edgeScore=remainingEdge(position,m,nearEvents,immediateEvents);
    const assignment=String(position.assignment_mode||'accept').toLowerCase();
    const purpose=String(position.strategy_note||'').trim();
    const capture=m.pnlPct;
    const remaining=capture===null?null:Math.max(0,1-capture);
    const spreadGood=m.spread!==null&&m.spread<=0.12;
    const spreadWide=m.spread!==null&&m.spread>0.20;
    const deltaLow=absDelta!==null&&absDelta<=0.15;
    const deltaHigh=absDelta!==null&&absDelta>=0.35;
    const nearStrike=m.spot!==null&&strike?m.spot/strike-1:null;

    let level='quiet',timing='无需处理',decision='继续持有',action='继续持有并自动监控。',reasons=[],changeConditions=[],edge='';

    if(!quote){
      return{
        level:'review',timing:'今天',decision:'先刷新报价',
        action:'当前缺少有效期权报价，今天先刷新 Bid/Ask、Delta、IV 和正股价格，再做持有/平仓判断。',
        reasons:['没有可用实时/参考报价，不能可靠比较剩余收益与风险'],
        changeConditions:['取得有效报价后重新计算'],
        edge:'数据不足，暂不做方向性判断。',
        metrics:m
      };
    }

    if(position.status==='pending_settlement'){
      return{
        level:'action',timing:'今天',decision:'完成结算',
        action:'今天完成到期结算检查；确认作废、被行权或需要补录结算。',
        reasons:['该仓位已到期并处于待结算状态'],
        changeConditions:['结算状态确认后从开放仓位移除'],
        edge:'继续等待没有额外收益，优先完成账本与行权确认。',
        metrics:m
      };
    }

    if(short&&type==='put'){
      if(m.dte<=7&&(nearStrike===null||nearStrike<=0.03||deltaHigh)){
        level='action';timing='今天';
        if(assignment==='avoid'){
          decision='今天优先平仓/展期';
          action='今天优先在流动性正常时平仓或展期；当前已进入临期行权风险区，不建议把决定拖到最后几个交易日。';
        }else{
          decision='今天确认是否接受接货';
          action='今天明确二选一：若仍愿意按有效成本接货，可继续持有；若不愿接货，今天优先平仓或展期。';
        }
        reasons.push(`仅剩 ${m.dte} DTE，|Delta| ${absDelta===null?'—':absDelta.toFixed(2)}`);
        if(nearStrike!==null)reasons.push(`正股相对行权价 ${pct(nearStrike,1)}`);
        changeConditions.push('正股远离行权价且 Delta 明显下降','出现新的公司级事件或 Thesis 变化');
      }else if(capture!==null&&capture>=0.80&&deltaLow){
        if(spreadGood){
          level='action';timing='今天';decision='今天优先平仓';
          action='今天优先买回平仓，锁定大部分权利金收益；剩余收益已较少，而尾部风险和资金占用仍然存在。';
        }else{
          level='review';timing='明日复查';decision='今天不追价';
          action='利润已经高度兑现，但当前买卖价差不理想；今天不追价，挂合理限价，若未成交则明天重新评估。';
        }
        reasons.push(`已获取约 ${pct(capture,0)} 权利金收益，剩余约 ${pct(remaining,0)}`);
        reasons.push(`|Delta| 已降至 ${absDelta.toFixed(2)}，方向风险明显下降`);
        if(m.spread!==null)reasons.push(`Bid/Ask 相对价差约 ${pct(m.spread,0)}`);
        changeConditions.push('正股快速回落导致 Delta 重新升高','IV急升或出现新的重大公司事件');
        edge='主要收益已经实现；继续持有的边际收益低于开仓初期。';
      }else if(capture!==null&&capture>=0.60&&deltaLow&&m.dte>=21){
        level='review';timing='今天';
        if(spreadGood&&capture>=0.70){
          decision='今天可以平仓';
          action='当前更偏向今天平仓：已兑现较多收益、Delta较低且执行成本可控；若你仍希望继续赚剩余时间价值，也只建议保留到预设利润目标而不是机械持有到期。';
        }else{
          decision='继续持有，明日复查';
          action='今天继续持有，不急于平仓；目前仍有一定剩余权利金，且距离到期尚远。明天继续比较剩余收益、Delta 和价差。';
        }
        reasons.push(`当前已获取约 ${pct(capture,0)} 权利金收益`);
        reasons.push(`|Delta| ${absDelta.toFixed(2)}，DTE ${m.dte}`);
        if(m.spread!==null)reasons.push(`Bid/Ask 相对价差约 ${pct(m.spread,0)}`);
        changeConditions.push('利润捕获达到80%附近','Delta回升至0.20以上','出现7天内重大事件');
        edge=`剩余可赚约 ${pct(remaining,0)} 的原始权利金；是否继续持有取决于执行成本和尾部风险。`;
      }else if(capture!==null&&capture<0&&deltaHigh){
        level='review';timing='今天';
        if(assignment==='avoid'){
          decision='今天评估展期/减风险';
          action='当前亏损且 Delta 已进入较高风险区；今天优先评估展期或降低敞口，不建议只因还有时间就忽略风险。';
        }else{
          decision='继续持有，但确认接货逻辑';
          action='如果原计划就是愿意接货，今天可以继续持有；但必须重新确认有效接货成本、资金占用和公司 Thesis 是否仍成立。';
        }
        reasons.push(`当前 P/L ${pct(capture,0)}，|Delta| ${absDelta.toFixed(2)}`);
        changeConditions.push('Thesis失效','不再愿意接货','Delta进一步升高或进入21 DTE以内');
        edge='当前重点不是剩余权利金，而是接货风险与原始建仓逻辑是否仍成立。';
      }else{
        decision='继续持有';
        action='今天继续持有并自动监控；当前尚未达到利润锁定、临期或高Delta风险阈值。';
        reasons.push(`P/L ${capture===null?'—':pct(capture,0)} · |Delta| ${absDelta===null?'—':absDelta.toFixed(2)} · DTE ${m.dte}`);
        changeConditions.push('利润捕获进入70%–80%区间','Delta明显上升','进入21 DTE以内');
        edge='当前继续持有仍有合理的剩余时间价值，但需要等待更明确的退出触发条件。';
      }
    }else if(short&&type==='call'){
      if(m.dte<=7||(m.spot!==null&&strike&&m.spot>=strike*0.98)){
        level='action';timing='今天';decision='今天评估平仓/展期';
        action='今天优先检查平仓或展期，避免临近到期时被动处理指派风险；若本来就愿意在该行权价卖出正股，则可以保留到期方案。';
        reasons.push('Short Call 已进入临期或近平值风险区');
        changeConditions.push('正股回落远离行权价','确认愿意按行权价卖出正股');
      }else if(capture!==null&&capture>=0.80){
        level='review';timing='今天';decision=spreadGood?'今天优先平仓':'今天不追价';
        action=spreadGood?'今天优先买回平仓，锁定大部分权利金收益并恢复正股上涨空间。':'利润已高度兑现，但当前执行成本偏高；今天不追价，等待更合理买回报价。';
        reasons.push(`已获得约 ${pct(capture,0)} 权利金收益`);
        changeConditions.push('正股继续快速上涨接近行权价','价差收窄');
        edge='继续持有的剩余收益有限，但会继续占用正股上行空间。';
      }else{
        decision='继续持有';
        action='今天继续持有并监控正股距行权价、Delta 与剩余权利金。';
        reasons.push(`P/L ${capture===null?'—':pct(capture,0)} · |Delta| ${absDelta===null?'—':absDelta.toFixed(2)} · DTE ${m.dte}`);
        changeConditions.push('利润捕获进入80%附近','正股接近行权价','进入14 DTE以内');
        edge='当前仍有可赚时间价值，尚未出现必须提前处理的条件。';
      }
    }else{
      if(m.dte<=21){
        level='review';timing='今天';decision='今天重新评估是否继续持有';
        action='Long 期权已进入时间价值损耗敏感区；今天重新确认方向、催化剂和剩余期限是否仍匹配，若催化剂延后应优先处理。';
        reasons.push(`仅剩 ${m.dte} DTE`);
      }else if(capture!==null&&capture>=1.0){
        level='review';timing='今天';decision='今天评估锁定利润';
        action='当前浮盈已达到建仓成本的约1倍或以上；今天评估部分或全部锁定利润，并重新比较继续持有的波动率与回撤风险。';
        reasons.push(`当前浮盈约 ${pct(capture,0)}`);
      }else{
        decision='继续持有';
        action='今天继续持有；当前没有触发时间衰减、盈利锁定或临近事件的强制复查条件。';
        reasons.push(`P/L ${capture===null?'—':pct(capture,0)} · DTE ${m.dte}`);
      }
      changeConditions.push('进入21 DTE以内','核心催化剂变化','浮盈/亏损显著扩大');
      edge='Long仓位的核心判断仍然是方向、催化兑现时间与IV是否匹配。';
    }

    if(immediateEvents.length){
      if(rank(level)<3)level='action';
      timing='今天';
      reasons.push(`未来2天内存在 ${[...new Set(immediateEvents.map(x=>x.event.type))].join('/')} 事件`);
      action+=' 由于事件已非常接近，今天必须把事件风险纳入最终决定。';
    }else if(nearEvents.length){
      if(rank(level)<2)level='review';
      if(timing==='无需处理')timing='今天';
      reasons.push(`未来7天内存在 ${[...new Set(nearEvents.map(x=>x.event.type))].join('/')} 事件`);
      if(decision==='继续持有')action+=' 同时需要确认是否愿意跨越该事件继续持仓。';
    }

    if(spreadWide){
      if(rank(level)<2)level='review';
      reasons.push(`买卖价差约 ${pct(m.spread,0)}，执行成本偏高`);
      if(/平仓|展期/.test(decision))action+=' 当前价差偏宽，不建议用市价单追价。';
    }
    if(purpose)reasons.push(`策略备注：${purpose}`);

    return{level,timing,decision,action,reasons,changeConditions,edge,remainingEdge:edgeScore,metrics:m};
  }

  function privateAttention(){
    const positions=global.OptionV2?.getPositions?.()||[];
    return positions.map(p=>{
      const cached=global.OptionV2?.getCachedQuote?.(p.id);
      const quote=cached?.quote||null;
      const a=optionAdvice(p,quote);
      return{kind:'option',symbol:p.symbol,label:`${String(p.side).toLowerCase()==='short'?'Sell':'Buy'} ${String(p.opt_type).toLowerCase()==='call'?'Call':'Put'} $ ${Number(p.strike).toFixed(2)} · ${p.expiry}`,...a,id:p.id}
    }).sort((a,b)=>rank(b.level)-rank(a.level)||((a.metrics?.dte??999)-(b.metrics?.dte??999)));
  }

  function publicAttention(){
    const rows=state.publicData?.attention_summary?.top_attention||[];
    return rows.map(x=>({kind:'stock',symbol:x.symbol,label:x.stage||'Watchlist',level:x.level,timing:x.timing,action:x.action,reasons:x.reasons||[],metrics:{day_change:x.day_change,research_priority:x.research_priority}}));
  }

  function card(item){
    const m=item.metrics||{};
    const metrics=item.kind==='option'
      ?[`P/L ${m.pnlPct===null?'—':pct(m.pnlPct,0)}`,`DTE ${m.dte??'—'}`,`Δ ${m.delta===null?'—':Number(m.delta).toFixed(2)}`,`IV ${m.iv===null?'—':pct(m.iv,0)}`,`价差 ${m.spread===null?'—':pct(m.spread,0)}`]
      :[`当日 ${m.day_change===null||m.day_change===undefined?'—':pct(m.day_change,1)}`,`研究优先级 ${m.research_priority??'—'}`];
    const decision=item.decision||levelLabel(item.level);
    const change=item.changeConditions?.length?`<div class="agent-change"><b>改变判断的条件</b><span>${item.changeConditions.slice(0,4).map(esc).join(' · ')}</span></div>`:'';
    const edge=item.edge?`<div class="agent-edge"><b>剩余风险收益：</b>${esc(item.edge)}</div>`:'';
    const edgeScore=item.remainingEdge?'<div class="agent-edge"><b>Remaining Edge：</b>'+item.remainingEdge.score+'/100 · '+esc(item.remainingEdge.label)+(item.remainingEdge.positives?.length?'<br><span>支持：'+item.remainingEdge.positives.slice(0,3).map(esc).join(' · ')+'</span>':'')+(item.remainingEdge.risks?.length?'<br><span>风险：'+item.remainingEdge.risks.slice(0,3).map(esc).join(' · ')+'</span>':'')+'</div>':'';
    return `<article class="agent-card agent-${esc(item.level)}"><div class="agent-card-head"><div><span>${item.kind==='option'?'PRIVATE POSITION':'WATCHLIST'}</span><h3>${esc(item.symbol)} · ${esc(item.label)}</h3></div><b>${esc(levelLabel(item.level))} · ${esc(item.timing)}</b></div><div class="agent-decision">${esc(decision)}</div><div class="agent-metrics">${metrics.map(x=>`<span>${esc(x)}</span>`).join('')}</div><p><strong>当前方案：</strong>${esc(item.action)}</p>${edgeScore}${edge}${item.reasons?.length?`<ul>${item.reasons.slice(0,5).map(r=>`<li>${esc(r)}</li>`).join('')}</ul>`:''}${change}${item.kind==='option'?'<small>系统不会自动下单；若执行，请以券商实时报价、保证金与公司事件为最终确认。</small>':''}</article>`;
  }

  function render(){
    const host=$('agentAttentionRoot');if(!host)return;
    const pub=publicAttention(),priv=privateAttention();
    const optionAttention=priv.filter(x=>x.level!=='quiet').sort((a,b)=>rank(b.level)-rank(a.level)||((a.metrics?.dte??999)-(b.metrics?.dte??999)));
    const stockAttention=pub.filter(x=>x.level!=='quiet').sort((a,b)=>rank(b.level)-rank(a.level));
    const all=[...optionAttention,...stockAttention];
    const tracked=all.map(item=>({...item,_change:trackDecision(item)}));
    const changed=tracked.filter(x=>x._change.changed);
    const counts={action:tracked.filter(x=>x.level==='action').length,review:tracked.filter(x=>x.level==='review').length,watch:tracked.filter(x=>x.level==='watch').length};
    const discovery=state.publicData?.discovery_queue||[];
    const optionsHtml=optionAttention.length?`<div class="agent-section-title"><b>期权持仓决策</b><span>${optionAttention.length} 笔需要注意</span></div><div class="agent-grid">${optionAttention.map(card).join('')}</div>`:'<div class="agent-section-title"><b>期权持仓决策</b><span>当前无需要处理的异常</span></div>';
    const stocksHtml=stockAttention.length?`<div class="agent-section-title"><b>关注股与核心资产</b><span>${stockAttention.length} 项变化</span></div><div class="agent-grid">${stockAttention.map(card).join('')}</div>`:'<div class="agent-section-title"><b>关注股与核心资产</b><span>当前无重要变化</span></div>';
    host.innerHTML=`<div class="agent-attention-head"><div><span class="agent-kicker">MYALPHA AUTONOMOUS AGENT · V5.5</span><h2>自主研究助手</h2><p>不是只告诉你“需要复查”，而是明确说明今天做什么、为什么、什么条件会改变判断。</p></div><div class="agent-counts"><span class="action">需处理 <b>${counts.action}</b></span><span class="review">需复查 <b>${counts.review}</b></span><span>观察 <b>${counts.watch}</b></span></div></div>
      ${tracked.length?`<div class="agent-section-title"><b>Changed Since Last Decision</b><span>${changed.length} 项变化</span></div>${changed.length?`<div class="agent-grid">${changed.slice(0,6).map(card).join('')}</div>`:'<div class="agent-empty">当前判断与上次一致，不重复打扰。</div>'}`+optionsHtml+stocksHtml:'<div class="agent-empty">当前没有需要打扰你的重大变化；系统仍在后台记录和学习。</div>'}
      ${discovery.length?`<details class="agent-discovery"><summary>自主发现 · 异常机会 ${discovery.length}</summary><div>${discovery.slice(0,8).map(x=>`<p><b>${esc(x.symbol)}</b> · ${pct(x.price_change,1)} · ${esc(x.event_strength)}<br><small>${esc(x.next_step)} ${esc(x.guardrail)}</small></p>`).join('')}</div></details>`:''}
      <div class="agent-foot">自主研究 ≠ 自动交易。系统负责主动发现、解释、排序和提出方案；最终交易仍由投资者确认。</div>`;
    state.lastRender=Date.now();
  }

  async function init(){await loadPublic();render();setTimeout(render,2500);setTimeout(render,7000)}
  global.MAVAutonomousAgent={render,loadPublic,optionAdvice,privateAttention,remainingEdge,readMemory,state};
  if(typeof document!=='undefined'){
    window.addEventListener('mav:options-updated',()=>render());
    document.addEventListener('DOMContentLoaded',init);
  }
})(typeof window!=='undefined'?window:globalThis);
