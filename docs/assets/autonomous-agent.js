(function(global){
  'use strict';
  const $=id=>document.getElementById(id);
  const state={publicData:null,lastRender:0};

  function n(v){const x=Number(v);return Number.isFinite(x)?x:null}
  function pct(v,d=0){return Number.isFinite(Number(v))?(Number(v)*100).toFixed(d)+'%':'—'}
  function money(v){return Number.isFinite(Number(v))?'$'+Number(v).toFixed(2):'—'}
  function esc(v){return String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
  function rank(level){return({quiet:0,watch:1,review:2,action:3})[level]??0}
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

  function optionAdvice(position,quote){
    const m=optionMetrics(position,quote),side=String(position.side||'').toLowerCase(),type=String(position.opt_type||'').toLowerCase();
    const short=side==='short',absDelta=m.delta===null?null:Math.abs(m.delta),strike=n(position.strike),events=global.OptionV2?.getEvents?.()||[];
    const upcoming=events.filter(e=>{const d=new Date(e.datetime);return d>=new Date()&&d<=new Date(position.expiry+'T23:59:59Z')});
    let level='quiet',timing='无需处理',action='继续持有并自动监控。',reasons=[];

    if(position.status==='pending_settlement'){
      return{level:'action',timing:'今天',action:'今天完成到期结算检查；确认是否作废、被行权或需要补录结算。',reasons:['该仓位已到期并处于待结算状态'],metrics:m};
    }

    if(short&&type==='put'){
      const nearStrike=m.spot!==null&&strike?m.spot/strike-1:null;
      if(m.dte<=7&&(nearStrike===null||nearStrike<=0.03||(absDelta!==null&&absDelta>=0.35))){
        level='action';timing='今天';action='今天优先决定平仓、展期或接受行权，不建议拖到临近到期后再处理。';
        reasons.push(`仅剩 ${m.dte} DTE，且行权风险已进入重点检查区`);
      }else if(m.pnlPct!==null&&m.pnlPct>=0.80&&m.spread!==null&&m.spread<=0.20){
        level='action';timing='今天';action='当前方案：今天优先平仓锁定大部分权利金收益；若实际买回价差异常扩大，则不追价并转为明日复查。';
        reasons.push(`已获得约 ${pct(m.pnlPct,0)} 建仓权利金收益`);
        if(absDelta!==null)reasons.push(`|Delta| 已降至 ${absDelta.toFixed(2)}`);
      }else if(m.pnlPct!==null&&m.pnlPct>=0.65&&(absDelta===null||absDelta<=0.18)){
        level='review';
        if(m.spread!==null&&m.spread<=0.12){timing='今天';action='今天评估平仓：剩余权利金相对已获利润偏少，若买回报价正常可优先锁定；否则明天再看。'}
        else{timing='明日复查';action='今天不追价，明天重新比较剩余权利金、Delta 与买卖价差后再决定是否平仓。'}
        reasons.push(`已获得约 ${pct(m.pnlPct,0)} 建仓权利金收益`);
      }else if(m.dte<=14){
        level='review';timing='今天';action='今天复查是否继续持有到期；重点看正股距行权价、Delta、流动性和到期前事件。';
        reasons.push(`进入 ${m.dte} DTE 临期区`);
      }
    }else if(short&&type==='call'){
      if(m.dte<=7||(m.spot!==null&&strike&&m.spot>=strike*0.98)){
        level='action';timing='今天';action='今天优先检查是否需要平仓或展期，避免在临近到期时被动处理行权风险。';
        reasons.push('Short Call 已进入临期/近平值重点检查区');
      }else if(m.pnlPct!==null&&m.pnlPct>=0.80){
        level='review';timing='今天';action='今天评估是否提前锁定大部分权利金收益，并重新比较继续占用标的/保证金的价值。';
        reasons.push(`已获得约 ${pct(m.pnlPct,0)} 建仓权利金收益`);
      }
    }else{
      if(m.dte<=21){
        level='review';timing='今天';action='今天复查 Long 期权：时间价值损耗已进入敏感区，需要重新确认方向、催化剂与剩余期限是否匹配。';
        reasons.push(`仅剩 ${m.dte} DTE`);
      }
      if(m.pnlPct!==null&&m.pnlPct>=1.0){
        level='review';timing='今天';action='今天评估是否锁定部分或全部利润，并比较继续持有的事件/波动率风险。';
        reasons.push(`当前浮盈约 ${pct(m.pnlPct,0)}`);
      }
    }

    if(upcoming.length){
      if(rank(level)<2)level='review';
      if(timing==='无需处理')timing='今天';
      reasons.push(`到期前存在 ${[...new Set(upcoming.map(x=>x.type))].join('/')} 事件`);
      if(action==='继续持有并自动监控。')action='今天复查到期前事件风险；确认事件是否改变原始建仓逻辑。';
    }
    if(m.spread!==null&&m.spread>0.20){
      if(rank(level)<2)level='review';
      reasons.push(`买卖价差约 ${pct(m.spread,0)}，执行成本偏高`);
      if(timing==='今天')action+=' 当前价差偏宽时不建议追价。';
    }

    return{level,timing,action,reasons,metrics:m};
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
      ?[`P/L ${m.pnlPct===null?'—':pct(m.pnlPct,0)}`,`DTE ${m.dte??'—'}`,`Δ ${m.delta===null?'—':Number(m.delta).toFixed(2)}`,`IV ${m.iv===null?'—':pct(m.iv,0)}`]
      :[`当日 ${m.day_change===null||m.day_change===undefined?'—':pct(m.day_change,1)}`,`研究优先级 ${m.research_priority??'—'}`];
    return `<article class="agent-card agent-${esc(item.level)}"><div class="agent-card-head"><div><span>${item.kind==='option'?'PRIVATE POSITION':'WATCHLIST'}</span><h3>${esc(item.symbol)} · ${esc(item.label)}</h3></div><b>${esc(levelLabel(item.level))} · ${esc(item.timing)}</b></div><div class="agent-metrics">${metrics.map(x=>`<span>${esc(x)}</span>`).join('')}</div><p><strong>当前方案：</strong>${esc(item.action)}</p>${item.reasons?.length?`<ul>${item.reasons.slice(0,4).map(r=>`<li>${esc(r)}</li>`).join('')}</ul>`:''}${item.kind==='option'?'<small>不会自动下单；执行前仍需以券商实时报价、保证金与事件信息确认。</small>':''}</article>`;
  }

  function render(){
    const host=$('agentAttentionRoot');if(!host)return;
    const pub=publicAttention(),priv=privateAttention(),all=[...priv,...pub].sort((a,b)=>rank(b.level)-rank(a.level));
    const attention=all.filter(x=>x.level!=='quiet');
    const counts={action:attention.filter(x=>x.level==='action').length,review:attention.filter(x=>x.level==='review').length,watch:attention.filter(x=>x.level==='watch').length};
    const discovery=state.publicData?.discovery_queue||[];
    host.innerHTML=`<div class="agent-attention-head"><div><span class="agent-kicker">MYALPHA AUTONOMOUS AGENT · V5.5</span><h2>自主研究助手</h2><p>系统已经主动扫描持仓、关注池和异常变化；只有值得你注意的事项才会浮到这里。</p></div><div class="agent-counts"><span class="action">需处理 <b>${counts.action}</b></span><span class="review">需复查 <b>${counts.review}</b></span><span>观察 <b>${counts.watch}</b></span></div></div>
      ${attention.length?`<div class="agent-grid">${attention.slice(0,8).map(card).join('')}</div>`:'<div class="agent-empty">当前没有需要打扰你的重大变化；系统仍在后台记录和学习。</div>'}
      ${discovery.length?`<details class="agent-discovery"><summary>自主发现 · 异常机会 ${discovery.length}</summary><div>${discovery.slice(0,8).map(x=>`<p><b>${esc(x.symbol)}</b> · ${pct(x.price_change,1)} · ${esc(x.event_strength)}<br><small>${esc(x.next_step)} ${esc(x.guardrail)}</small></p>`).join('')}</div></details>`:''}
      <div class="agent-foot">自主研究 ≠ 自动交易。系统负责主动发现、解释、排序和提出方案；最终交易仍由投资者确认。</div>`;
    state.lastRender=Date.now();
  }

  async function init(){await loadPublic();render();setTimeout(render,2500);setTimeout(render,7000)}
  global.MAVAutonomousAgent={render,loadPublic,optionAdvice,privateAttention,state};
  if(typeof document!=='undefined'){
    window.addEventListener('mav:options-updated',()=>render());
    document.addEventListener('DOMContentLoaded',init);
  }
})(typeof window!=='undefined'?window:globalThis);
