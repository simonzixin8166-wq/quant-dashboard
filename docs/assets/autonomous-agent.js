(function(global){
  'use strict';
  const $=id=>document.getElementById(id);
  const state={publicData:null,evidenceData:null,systemStatus:null,plannerData:null,researchData:null,selfImproveData:null,learningEvalData:null,crossAssetData:null,breadthData:null,regimeData:null,rangeData:null,playbookData:null,ledgerAnchor:null,outcomeData:null,replayData:null,controlledPolicy:null,forwardFeedback:null,challengerExperiments:null,lastRender:0};
  const MEMORY_KEY='mavAgentDecisionMemoryV562', LEGACY_MEMORY_KEY='mavAgentDecisionMemoryV56', POLICY_KEY='mavLearningPolicyV1';

  function n(v){const x=Number(v);return Number.isFinite(x)?x:null}
  function pct(v,d=0){return Number.isFinite(Number(v))?(Number(v)*100).toFixed(d)+'%':'—'}
  function money(v){return Number.isFinite(Number(v))?'$'+Number(v).toFixed(2):'—'}
  function num(v,d=2){return Number.isFinite(Number(v))?Number(v).toFixed(d):'—'}
  function humanTime(v){if(!v)return'—';try{return new Intl.DateTimeFormat('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(v))}catch{return String(v)}}
  function kindLabel(v){return({regime_combination:'组合环境',breadth_intelligence:'市场宽度',cross_asset_divergence:'跨资产背离',market_anomaly:'个股异动',failure_review:'失败复盘',method_evidence_gap:'方法验证',method_validation:'方法证据',module_learning_review:'模块学习',architecture_gap:'架构检查',leverage_rebound:'杠杆回调',module_learning_design:'模块学习设计',research_process:'研究流程',playbook_validation:'剧本验证'})[v]||v||'研究'}
  function confidenceLabel(v){return({high:'高',medium:'中',low:'低'})[v]||v||'—'}
  function shadowChange(x){const p=x?.proposed_change||{};if(p.target_mode==='shadow_only')return '先建立结果标签，再进入影子学习';if(p.require_explicit_unknowns&&p.prioritize_missing_official_evidence)return '强制记录未知项，并优先补齐官方证据';if(Number.isFinite(Number(p.priority_weight_delta)))return '研究优先级权重 '+(Number(p.priority_weight_delta)>0?'+':'')+Number(p.priority_weight_delta);return Object.entries(p).map(([k,v])=>k+'='+String(v)).join(' · ')||'等待候选说明'}
  function esc(v){return String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
  function rank(level){return({quiet:0,watch:1,review:2,action:3})[level]??0}
  function readMemory(){
    try{
      let mem=JSON.parse(localStorage.getItem(MEMORY_KEY)||'null');
      if(!mem||typeof mem!=='object'){
        const old=JSON.parse(localStorage.getItem(LEGACY_MEMORY_KEY)||'{}')||{};
        mem={};
        for(const [key,value] of Object.entries(old))mem[key]={current:value,history:value?[value]:[]};
        localStorage.setItem(MEMORY_KEY,JSON.stringify(mem));
      }
      return mem;
    }catch{return {}}
  }
  function writeMemory(v){try{localStorage.setItem(MEMORY_KEY,JSON.stringify(v))}catch{}}
  function decisionSignature(item){
    const edge=item.remainingEdge?.label||'';
    const delta=n(item.metrics?.delta),deltaBand=delta===null?'':Math.abs(delta)>=.35?'high':Math.abs(delta)>=.20?'mid':'low';
    const dte=n(item.metrics?.dte),dteBand=dte===null?'':dte<=7?'7':dte<=21?'21':dte<=45?'45':'long';
    return [item.kind,item.symbol,item.decision||'',item.level||'',item.timing||'',edge,deltaBand,dteBand].join('|');
  }
  function trackDecision(item){
    const mem=readMemory(),key=(item.kind==='option'?'option:':'stock:')+(item.id||item.symbol),slot=mem[key]||{},prev=slot.current||slot;
    const sig=decisionSignature(item),changed=Boolean(prev?.signature&&prev.signature!==sig),now=new Date().toISOString();
    const record={signature:sig,decision:item.decision||'',level:item.level||'',timing:item.timing||'',edge:item.remainingEdge?.score??null,edgeLabel:item.remainingEdge?.label||'',dte:n(item.metrics?.dte),delta:n(item.metrics?.delta),iv:n(item.metrics?.iv),pnlPct:n(item.metrics?.pnlPct),at:now};
    const history=Array.isArray(slot.history)?slot.history.slice():prev?.signature?[prev]:[];
    if(!prev?.signature||changed)history.push(record);
    mem[key]={current:record,history:history.slice(-60),kind:item.kind,symbol:item.symbol,id:item.id||null};
    writeMemory(mem);return{changed,isNew:!prev?.signature,previous:prev?.signature?prev:null,history:mem[key].history};
  }
  function decisionHistory(idOrSymbol,kind='option'){const mem=readMemory(),slot=mem[(kind==='option'?'option:':'stock:')+idOrSymbol];return Array.isArray(slot?.history)?slot.history:[]}

  function readPolicyStore(){try{return JSON.parse(localStorage.getItem(POLICY_KEY)||'{}')||{}}catch{return {}}}
  function writePolicyStore(v){try{localStorage.setItem(POLICY_KEY,JSON.stringify(v))}catch{}}
  function buildLearningPolicy(){
    const review=global.MAVDecisionJournal?.getSelfReview?.()||{};
    const errors=global.MAVDecisionJournal?.getErrorMemory?.()||[];
    const sample=Number(review.sample||0),missed=Number(review.missed||0),noisy=Number(review.noisy||0);
    const falsePositive=errors.filter(x=>x.type==='false-positive').length;
    const learnedAdjustments={
      restart_bonus:missed>=2?Math.min(5,2+missed):0,
      repeat_alert_penalty:noisy>=2?-Math.min(10,4+noisy*2):0,
      weak_candidate_penalty:falsePositive>=2?-Math.min(6,2+falsePositive):0
    };
    const evidence={sample,missed,noisy,false_positive:falsePositive};
    const store=readPolicyStore(),baselineMode=Boolean(store.forceBaseline);
    const adjustments=baselineMode?{restart_bonus:0,repeat_alert_penalty:0,weak_candidate_penalty:0}:learnedAdjustments;
    const signature=JSON.stringify({adjustments,evidence,baselineMode});
    const prev=store.current||null;
    let version=Number(prev?.version||1);
    if(prev?.signature&&prev.signature!==signature)version+=1;
    const policy={version,signature,generatedAt:new Date().toISOString(),adjustments,evidence,baselineMode,learnedAdjustments,scope:'research-priority-and-alert-weight-only',baseline:{restart_bonus:0,repeat_alert_penalty:0,weak_candidate_penalty:0}};
    const history=Array.isArray(store.history)?store.history.slice():[];
    if(!prev?.signature||prev.signature!==signature)history.push(policy);
    writePolicyStore({current:policy,history:history.slice(-20),forceBaseline:baselineMode});
    return policy;
  }
  function applyLearningPolicy(row,policy){
    const base=n(row?.metrics?.research_priority),stage=String(row?.label||'');
    let adjustment=0;const reasons=[];
    if(base!==null&&/二次启动|趋势启动|修复/.test(stage)&&policy.adjustments.restart_bonus){
      adjustment+=policy.adjustments.restart_bonus;reasons.push('历史漏掉上涨样本提高二次启动复核权重');
    }
    if(base!==null&&/修复|启动/.test(stage)&&policy.adjustments.weak_candidate_penalty){
      adjustment+=policy.adjustments.weak_candidate_penalty;reasons.push('历史误报样本提高候选证据门槛');
    }
    const adjusted=base===null?null:Math.max(0,Math.min(100,Math.round((base+adjustment)*10)/10));
    let adjustedLevel=row.level;
    if(adjusted!==null&&adjustedLevel==='watch'&&adjusted<58)adjustedLevel='quiet';
    if(adjusted!==null&&rank(adjustedLevel)<rank('review')&&adjusted>=70)adjustedLevel='review';
    return {...row,level:adjustedLevel,metrics:{...(row.metrics||{}),base_research_priority:base,research_priority:adjusted,learning_adjustment:adjustment},learningPolicyReasons:reasons};
  }
  function resetLearningPolicy(){const store=readPolicyStore();writePolicyStore({...store,forceBaseline:true});render()}
  function resumeLearningPolicy(){const store=readPolicyStore();writePolicyStore({...store,forceBaseline:false});render()}
  function levelLabel(level){return({quiet:'无需处理',watch:'观察',review:'需要复查',action:'需要处理'})[level]||level}

  async function loadPublic(){
    try{
      const [a,e,s,h,p,x,v7,le,ca,bi,rg,range,pb,la,po,rp,cl,ff,ce]=await Promise.all([
        fetch('research/autonomous_agent.json?v='+Date.now(),{cache:'no-store'}),
        fetch('research/evidence_attribution.json?v='+Date.now(),{cache:'no-store'}),
        fetch('data/source_intelligence.json?v='+Date.now(),{cache:'no-store'}),
        fetch('research/system_status.json?v='+Date.now(),{cache:'no-store'}).catch(()=>null),
        fetch('research/research_planner.json?v='+Date.now(),{cache:'no-store'}).catch(()=>null),
        fetch('research/research_execution.json?v='+Date.now(),{cache:'no-store'}).catch(()=>null),
        fetch('research/self_improvement.json?v='+Date.now(),{cache:'no-store'}).catch(()=>null),
        fetch('research/learning_evaluation.json?v='+Date.now(),{cache:'no-store'}).catch(()=>null),
        fetch('research/cross_asset_divergence.json?v='+Date.now(),{cache:'no-store'}).catch(()=>null),
        fetch('research/breadth_intelligence.json?v='+Date.now(),{cache:'no-store'}).catch(()=>null),
        fetch('research/regime_combination_memory.json?v='+Date.now(),{cache:'no-store'}).catch(()=>null),
        fetch('research/range_intelligence.json?v='+Date.now(),{cache:'no-store'}).catch(()=>null),
        fetch('research/playbook_status.json?v='+Date.now(),{cache:'no-store'}).catch(()=>null),
        fetch('research/ledger_anchor.json?v='+Date.now(),{cache:'no-store'}).catch(()=>null),
        fetch('research/playbook_outcome_shadow.json?v='+Date.now(),{cache:'no-store'}).catch(()=>null),
        fetch('research/walk_forward_replay.json?v='+Date.now(),{cache:'no-store'}).catch(()=>null),
        fetch('research/controlled_learning_policy.json?v='+Date.now(),{cache:'no-store'}).catch(()=>null),
        fetch('research/forward_learning_feedback.json?v='+Date.now(),{cache:'no-store'}).catch(()=>null),
        fetch('research/challenger_experiments.json?v='+Date.now(),{cache:'no-store'}).catch(()=>null)
      ]);
      state.publicData=a.ok?await a.json():null;
      state.evidenceData=e.ok?await e.json():null;
      state.sourceIntel=s.ok?await s.json():null;
      state.systemStatus=h&&h.ok?await h.json():null;
      state.plannerData=p&&p.ok?await p.json():null;
      state.researchData=x&&x.ok?await x.json():null;
      state.selfImproveData=v7&&v7.ok?await v7.json():null;
      state.learningEvalData=le&&le.ok?await le.json():null;
      state.crossAssetData=ca&&ca.ok?await ca.json():null;
      state.breadthData=bi&&bi.ok?await bi.json():null;
      state.regimeData=rg&&rg.ok?await rg.json():null;
      state.rangeData=range&&range.ok?await range.json():null;
      state.playbookData=pb&&pb.ok?await pb.json():null;
      state.ledgerAnchor=la&&la.ok?await la.json():null;
      state.outcomeData=po&&po.ok?await po.json():null;
      state.replayData=rp&&rp.ok?await rp.json():null;
      state.controlledPolicy=cl&&cl.ok?await cl.json():null;
      state.forwardFeedback=ff&&ff.ok?await ff.json():null;
      state.challengerExperiments=ce&&ce.ok?await ce.json():null;
    }catch{state.publicData=null;state.evidenceData=null;state.sourceIntel=null;state.systemStatus=null;state.plannerData=null;state.researchData=null;state.selfImproveData=null;state.learningEvalData=null;state.crossAssetData=null;state.breadthData=null;state.regimeData=null;state.rangeData=null;state.playbookData=null;state.ledgerAnchor=null;state.outcomeData=null;state.replayData=null;state.controlledPolicy=null;state.forwardFeedback=null;state.challengerExperiments=null}
  }


  function rangeIntelligenceHtml(){
    const d=state.rangeData||{};if(!d.version||d.mode!=='research_only')return'';
    const labels={RANGE_EXTENDED:'扩张区',RANGE_BALANCED:'均衡区',RANGE_PULLBACK:'回撤区',RANGE_STRESS:'压力区',UNDETERMINED:'数据不足'};
    const cls={RANGE_EXTENDED:'review',RANGE_BALANCED:'watch',RANGE_PULLBACK:'review',RANGE_STRESS:'action',UNDETERMINED:'watch'};
    const rows=(d.assets||[]);
    return `<div class="agent-section-title"><b>V6.10b Market Location Research · 市场位置研究</b><span>Research Only · 不是完整 Range Engine</span></div>
      <div class="agent-grid">${rows.map(x=>`<article class="agent-card agent-${cls[x.state]||'watch'}"><div class="agent-card-head"><div><span>RANGE RESEARCH</span><h3>${esc(x.symbol)} · ${esc(labels[x.state]||x.state)}</h3></div><b>${esc(x.market_date||'—')}</b></div><div class="agent-metrics"><span>RSI ${num(x.metrics?.rsi14,1)}</span><span>回撤 ${pct(x.metrics?.drawdown,1)}</span><span>距200MA ${pct(x.metrics?.distance_200ma,1)}</span></div><p>${esc(x.decision_prompt||'')}</p><small>仅做 RSI / 回撤 / 200MA 市场位置分类：不改变 CP-01/02/03，不生成仓位，不写 Forward Ledger；结构化 Range Engine 尚未开发。</small></article>`).join('')}</div>`;
  }


  function learningEvaluationHtml(){
    const d=state.learningEvalData||{};if(!d.version)return'';
    const h=d.learning_health||{},r=d.research_scorecard||{},m=d.method_validation||{},g=d.evidence_gaps||[],lessons=d.lessons||[],focus=d.next_learning_focus||[];
    return `<div class="agent-section-title"><b>V6.9 Learning Evaluation · 自我评估中心</b><span>学习健康 ${esc(h.score??'—')}/${esc(h.max_score??100)}</span></div>
      <div class="agent-grid"><article class="agent-card agent-watch"><div class="agent-card-head"><div><span>LEARNING SCORECARD</span><h3>系统最近学到了什么</h3></div><b>${esc(d.version)}</b></div><div class="agent-metrics"><span>Situation ${r.situation_memory||0}</span><span>研究 ${r.analyzed||0}</span><span>高置信 ${r.high_confidence||0}</span><span>历史60日成熟 ${d.outcome_memory?.mature_60||0}</span><span>方法直接验证 ${m.methods_with_direct_validation||0}</span></div><ul>${lessons.slice(0,5).map(x=>`<li>${esc(x)}</li>`).join('')||'<li>等待下一轮学习结果。</li>'}</ul><small>${esc(h.meaning||'')}</small></article>
      <article class="agent-card agent-review"><div class="agent-card-head"><div><span>EVIDENCE GAPS</span><h3>当前最需要补什么</h3></div><b>${g.length} 类缺口</b></div><ul>${g.slice(0,5).map(x=>`<li><b>${esc(x.category)}</b> · ${x.count||0} 项</li>`).join('')||'<li>当前没有集中证据缺口。</li>'}</ul><details><summary>下一轮学习重点</summary><ul>${focus.slice(0,5).map(x=>`<li><b>#${x.priority} ${esc(x.focus)}</b> · ${esc(x.action)}</li>`).join('')}</ul></details><small>证据不足时只降置信度或补证据，不用猜测补全事实。</small></article></div>`;
  }

  function challengerExperimentHtml(){
    const d=state.challengerExperiments||{};if(!d.version)return'';
    if((d.candidate_count||0)===0){
      return '<div class="agent-change"><b>V6.13 Challenger Experiments</b><span>等待真实 Forward Challenger · 不从 Replay 单独制造候选</span></div>';
    }
    const ready=(d.experiments||[]).filter(x=>x.execution?.ready).length;
    return `<div class="agent-change"><b>V6.13 Challenger Experiments</b><span>候选 ${esc(d.candidate_count||0)} · 预注册实验 ${esc(d.experiment_count||0)} · 可运行 ${esc(ready)}</span></div><small>实验规格在结果生成前冻结；只能 Shadow 研究，任何晋级仍需人工复核。</small>`;
  }

  function controlledLearningHtml(){
    const d=state.controlledPolicy||{};if(!d.version)return'';
    const adj=d.candidate_adjustments||[],active=adj.filter(x=>x.active),pb=d.playbook_validation_priority_bonus||{};
    const applied=Object.entries(d.task_kind_priority_delta||{});
    const ff=state.forwardFeedback||{},fc=ff.counts||{},fps=ff.playbooks||{},chall=ff.challengers||[];
    const stateLabel={forward_unproven:'前瞻未成熟',forward_early:'前瞻早期',forward_supportive:'前瞻支持',forward_mixed:'前瞻混合',forward_challenging:'前瞻挑战',data_quality_review:'先查数据质量'};
    const forwardLine=['CP-01','CP-02','CP-03'].map(pid=>`${pid} ${stateLabel[fps[pid]?.state]||fps[pid]?.state||'未成熟'}`).join(' · ');
    return `<div class="agent-section-title"><b>V6.13.2 Controlled Learning · 受控自学习</b><span>Research Only · 正式交易规则锁定</span></div>
      <article class="agent-card agent-watch"><div class="agent-card-head"><div><span>CONTROLLED LEARNING ZONE</span><h3>系统可自动改变研究行为，不自动改变交易规则</h3></div><b>${esc(d.mode||'')}</b></div>
      <div class="agent-metrics"><span>已激活调整 ${active.length}</span><span>研究权重调整 ${applied.length}</span><span>单项上限 ±${esc(d.max_abs_priority_delta??5)}</span><span>CP-01验证 +${esc(pb['CP-01']??0)}</span><span>CP-02验证 +${esc(pb['CP-02']??0)}</span><span>CP-03验证 +${esc(pb['CP-03']??0)}</span></div>
      <p><strong>Forward Learning：</strong>${esc(forwardLine)}</p>
      <div class="agent-metrics"><span>20日成熟 ${esc(fc.forward_mature20??0)}</span><span>60日成熟 ${esc(fc.forward_mature60??0)}</span><span>归因复盘 ${esc(fc.attribution_reviews??0)}</span><span>Challenger ${esc(fc.challenger_candidates??chall.length)}</span></div>
      ${challengerExperimentHtml()}
      <p><strong>当前自动范围：</strong>研究任务优先级、证据状态、提醒排序。重复 Workflow 不累计学习；Replay 与 Forward 分开。</p>
      <small>Challenger 仅做影子诊断，不能自动晋级；仓位、下单、核心配置、CP阈值与 TQQQ Hard Exit 均不受本层自动修改。</small></article>`;
  }

  function brainHtml(){
    if(decisionDataBlock().blocked)return '<div class="agent-empty">当前研究计划与研究结果因关键数据新鲜度不足暂停作为当前结论展示；待数据恢复后自动恢复。</div>';
    const p=state.plannerData||{},x=state.researchData||{},v=state.selfImproveData||{};
    const today=p.today||[],results=x.results||[],cands=v.candidates||[];
    if(!today.length&&!results.length&&!cands.length)return'';
    const planner=`<div class="agent-section-title"><b>自主研究规划 · 研究计划</b><span>${today.length} 项今日重点 · ${p.counts?.persistent||0} 项持续跟踪</span></div>
      <div class="agent-grid">${today.slice(0,6).map(x=>`<article class="agent-card agent-review"><div class="agent-card-head"><div><span>${esc(kindLabel(x.kind))}</span><h3>${esc(x.title||x.key||'研究任务')}</h3></div><b>优先级 ${esc(x.priority??'—')}</b></div><p><strong>为什么现在研究：</strong>${esc(x.why_now||'')}</p><ul>${(x.questions||[]).slice(0,4).map(q=>`<li>${esc(q)}</li>`).join('')}</ul><small>连续运行 ${x.run_count||1} 次 · 需要同时记录支持证据、反证、未知项和下一验证条件。</small></article>`).join('')||'<div class="agent-empty">当前没有高优先级自主研究任务。</div>'}</div>`;
    const shadow=`<div class="agent-section-title"><b>Shadow Brain · 自我优化</b><span>${cands.length} 个候选 · ${v.shadow_brain?.eligible_for_review?.length||0} 个达到复核门槛</span></div>
      <div class="agent-grid">${cands.slice(0,6).map(x=>`<article class="agent-card agent-watch"><div class="agent-card-head"><div><span>影子测试 · ${esc(kindLabel(x.kind))}</span><h3>${esc(x.scope==='tab-cn-hk'?'A股港股学习模式':x.scope==='evidence_coverage'?'证据完整度':x.scope||'研究策略')}</h3></div><b>${esc(x.state==='eligible_for_review'?'可复核':'影子测试')}</b></div><p><strong>候选改进：</strong>${esc(shadowChange(x))}</p><p><strong>依据：</strong>${esc(x.reason||'')}</p><div class="agent-metrics"><span>证据 ${x.evidence_n||0}</span><span>独立市场日 ${x.shadow_market_days??x.shadow_runs??0} 天</span><span>Workflow ${x.workflow_runs||0} 次</span><span>最低市场日门槛 ${v.promotion_gate?.minimum_shadow_market_days??v.promotion_gate?.minimum_shadow_runs??5} 天</span></div><small>达到门槛也不会自动修改正式交易规则；Promotion Gate 要求人工复核。</small></article>`).join('')||'<div class="agent-empty">目前没有新的策略候选。</div>'}</div>`;
    const executed=`<div class="agent-section-title"><b>自主研究执行 · 研究结果</b><span>${results.length} 项已分析 · 反证 ${x.summary?.with_counter_evidence||0} · 未知项 ${x.summary?.with_unknowns||0}</span></div>
      <div class="agent-grid">${results.slice(0,6).map(r=>`<article class="agent-card agent-${r.confidence==='high'?'watch':'review'}"><div class="agent-card-head"><div><span>已分析 · ${esc(kindLabel(r.kind))}</span><h3>${esc(r.title||r.key||'自主研究')}</h3></div><b>${esc(confidenceLabel(r.confidence))}置信 · ${r.evidence_score??'—'}</b></div><p><strong>暂时结论：</strong>${esc(r.provisional_conclusion||'')}</p><details open><summary>支持证据（${(r.supporting_evidence||[]).length}）</summary><ul>${(r.supporting_evidence||[]).slice(0,5).map(z=>`<li>${esc(z)}</li>`).join('')||'<li>暂无</li>'}</ul></details><details><summary>反证（${(r.counter_evidence||[]).length}）</summary><ul>${(r.counter_evidence||[]).slice(0,5).map(z=>`<li>${esc(z)}</li>`).join('')||'<li>暂无</li>'}</ul></details><details><summary>未知项（${(r.unknowns||[]).length}）</summary><ul>${(r.unknowns||[]).slice(0,5).map(z=>`<li>${esc(z)}</li>`).join('')||'<li>暂无</li>'}</ul></details><small>已自动分析 ${r.analysis_runs||1} 次 · 不补猜缺失事实 · 不自动交易。</small></article>`).join('')||'<div class="agent-empty">等待执行第一批自主研究任务。</div>'}</div>`;
    return controlledLearningHtml()+planner+executed+shadow;
  }

  function crossAssetHtml(){
    if(decisionDataBlock().blocked)return'';
    const d=state.crossAssetData||{};if(!d.level)return'';
    const cls=d.level==='high'?'negative':d.level==='medium'?'review':'watch';
    const hits=(d.signals||[]).filter(x=>x.hit);
    return `<div class="agent-section-title"><b>跨资产背离 · 市场风险环境</b><span>${esc(d.label||'')}</span></div>
      <div class="agent-grid"><article class="agent-card agent-${cls==='negative'?'action':cls}">
      <div class="agent-card-head"><div><span>CROSS-ASSET DIVERGENCE · V6.7</span><h3>${esc(d.label||'跨资产观察')}</h3></div><b>风险信号 ${d.risk_hits||0}</b></div>
      <p><strong>含义：</strong>指数价格趋势与利率、信用、波动或市场宽度出现不同步。该标签用于提高研究优先级，不是卖出或做空指令。</p>
      <ul>${hits.slice(0,6).map(x=>`<li><b>${esc(x.label)}</b> · ${esc(x.reason)}</li>`).join('')}</ul>
      ${(d.unknowns||[]).length?`<details><summary>仍待补齐的数据</summary><ul>${d.unknowns.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details>`:''}
      <small>${esc(d.guardrail||'')}</small></article></div>`;
  }
  function breadthIntelligenceHtml(){
    if(decisionDataBlock().blocked)return'';
    const d=state.breadthData||{};if(!d.level)return'';
    const m=d.metrics||{},hits=(d.signals||[]).filter(x=>x.hit);
    return `<div class="agent-section-title"><b>Breadth Intelligence · 市场参与度</b><span>${esc(d.label||'')}</span></div>
      <div class="agent-grid"><article class="agent-card agent-${d.level==='fragile'?'action':d.level==='weakening'?'review':'watch'}">
      <div class="agent-card-head"><div><span>V6.8 BREADTH INTELLIGENCE</span><h3>${esc(d.label||'市场参与度')}</h3></div><b>参与度 ${esc(d.participation_score??'—')}/100</b></div>
      <div class="agent-metrics"><span>20日 ${pct(m.b20)}</span><span>50日 ${pct(m.b50)}</span><span>200日 ${pct(m.b200)}</span><span>10日斜率 ${pct(m.slope_10d,1)}</span><span>SPY-RSP ${pct(m.spy_minus_rsp_20d,1)}</span><span>QQQ-QQQE ${pct(m.qqq_minus_qqqe_20d,1)}</span><span>A/D20 ${n(m.ad_line_20d)!==null?n(m.ad_line_20d).toFixed(2):'—'}</span><span>52周新高 ${pct(m.new_high_52w_pct,1)}</span></div>
      <p><strong>组合状态：</strong>${esc(d.combination_key||'—')}</p>
      <ul>${hits.slice(0,6).map(x=>`<li><b>${esc(x.label)}</b> · ${esc(x.reason)}</li>`).join('')}</ul>
      <small>${esc(d.guardrail||'')}</small></article></div>`;
  }
  function regimeMemoryHtml(){
    if(decisionDataBlock().blocked)return'';
    const d=state.regimeData||{};if(!d.level)return'';
    const h=d.historical_matches?.mature||{};
    return `<div class="agent-section-title"><b>Regime Combination Memory · 组合情境记忆</b><span>${esc(d.label||'')}</span></div>
      <div class="agent-grid"><article class="agent-card agent-${d.level==='high'?'action':d.level==='medium'?'review':'watch'}">
      <div class="agent-card-head"><div><span>V6.8 JOINT SITUATION MEMORY</span><h3>${esc(d.state_id||'组合环境')}</h3></div><b>${esc(d.level||'')}</b></div>
      <p>${esc((d.interpretation||[])[0]||'等待组合情境积累。')}</p>
      <div class="agent-metrics"><span>历史同类 ${d.historical_matches?.total||0}</span><span>5日成熟 ${h['5']?.n||0}</span><span>20日成熟 ${h['20']?.n||0}</span><span>60日成熟 ${h['60']?.n||0}</span>${h['20']?.n?`<span>20日MAE ${pct(h['20']?.avg_mae,1)}</span><span>20日MFE ${pct(h['20']?.avg_mfe,1)}</span>`:''}</div>
      <small>${esc(d.guardrail||'')}</small></article></div>`;
  }

  function renderCrossAssetMarket(){
    const root=$('crossAssetMarketRoot');if(!root)return;
    if(decisionDataBlock().blocked){root.innerHTML='<div class="agent-empty">关键市场数据已超过新鲜度阈值；当前市场环境结论暂停展示，避免把缓存数据误认为当前状态。</div>';return}
    const d=state.crossAssetData||{},b=state.breadthData||{},r=state.regimeData||{};
    if(!d.level&&!b.level&&!r.level){root.innerHTML='<div class="agent-empty">等待市场环境智能数据。</div>';return}
    const hits=(d.signals||[]).filter(x=>x.hit),bm=b.metrics||{};
    root.innerHTML=`<div class="section-head"><div><h2>市场参与度与跨资产环境</h2><p>指数强弱、利率信用、20/50/200日宽度与等权/市值权重集中度联动</p></div><span>${esc(r.label||d.label||b.label||'')}</span></div>
      <div class="agent-grid">
      ${d.level?`<article class="agent-card agent-${d.level==='high'?'action':d.level==='medium'?'review':'watch'}"><div class="agent-card-head"><div><span>V6.7 CROSS-ASSET</span><h3>${esc(d.label||'跨资产观察')}</h3></div><b>${d.risk_hits||0} 项风险信号</b></div><div class="agent-metrics">${hits.slice(0,5).map(x=>`<span>${esc(x.label)}</span>`).join('')}</div><p>${esc((d.thesis||[])[0]||'跨资产状态正在评估。')}</p><small>${esc(d.guardrail||'')}</small></article>`:''}
      ${b.level?`<article class="agent-card agent-${b.level==='fragile'?'action':b.level==='weakening'?'review':'watch'}"><div class="agent-card-head"><div><span>V6.8 BREADTH</span><h3>${esc(b.label||'市场参与度')}</h3></div><b>${esc(b.participation_score??'—')}/100</b></div><div class="agent-metrics"><span>20日 ${pct(bm.b20)}</span><span>50日 ${pct(bm.b50)}</span><span>200日 ${pct(bm.b200)}</span><span>SPY-RSP ${pct(bm.spy_minus_rsp_20d,1)}</span><span>QQQ-QQQE ${pct(bm.qqq_minus_qqqe_20d,1)}</span><span>A/D20 ${n(bm.ad_line_20d)!==null?n(bm.ad_line_20d).toFixed(2):'—'}</span><span>52周新高 ${pct(bm.new_high_52w_pct,1)}</span></div><p>${esc((b.interpretation||[])[0]||'市场参与度正在评估。')}</p><small>${esc(b.guardrail||'')}</small></article>`:''}
      ${r.level?`<article class="agent-card agent-${r.level==='high'?'action':r.level==='medium'?'review':'watch'}"><div class="agent-card-head"><div><span>V6.8 REGIME MEMORY</span><h3>${esc(r.label||'组合情境')}</h3></div><b>${esc(r.state_id||'')}</b></div><p>${esc((r.interpretation||[])[0]||'')}</p><div class="agent-metrics"><span>同类历史 ${r.historical_matches?.total||0}</span><span>20日成熟 ${r.historical_matches?.mature?.['20']?.n||0}</span></div><small>${esc(r.guardrail||'')}</small></article>`:''}
      </div>`;
  }


  function replayShadowHtml(){
    const r=state.replayData||{};if(!r.version)return'';
    const s=r.summary||{},cov=r.coverage||{};
    const cp01=cov['CP-01']||{},cp02=cov['CP-02']||{},cp03=cov['CP-03']||{};
    return `<div class="agent-change"><b>V6.11 Historical Replay · Research Only</b><span>Raw ${esc(s.raw_events??0)} · Effective clusters ${esc(s.effective_clusters??0)} · 可完整回放 ${esc(s.replayable_playbooks??0)}/3</span></div>
      <small>证据标签：historical_replay_post_rule_design。CP-01 ${esc(cp01.status||'—')}；CP-02 ${esc(cp02.status||'—')}；CP-03 ${esc(cp03.status||'—')}。缺少依赖的数据不会用近似条件补齐，也不会与真实 Forward 样本混合。</small>`;
  }

  function outcomeShadowHtml(){
    const o=state.outcomeData||{};if(!o.version)return'';
    const m=o.mature_total||{},p=o.pending_total||{};
    return `<div class="agent-change"><b>Outcome Learning · Shadow Only</b><span>Forward Trigger ${esc(o.eligible_forward_triggers??0)} · 5日成熟 ${esc(m['5']??0)} / 待成熟 ${esc(p['5']??0)} · 20日成熟 ${esc(m['20']??0)} · 60日成熟 ${esc(m['60']??0)}</span></div><small>只建立结果学习闭环，不写 Forward Outcome Ledger；样本不足时不展示胜率、不改变正式规则。</small>`;
  }

  function playbookRuntimeHtml(){
    const d=state.playbookData||{},a=state.ledgerAnchor||{};
    if(!Array.isArray(d.playbooks)||!d.playbooks.length)return'';
    const names={'CP-01':'核心 ETF 回撤分档','CP-02':'TQQQ / QQQ 回调杠杆','CP-03':'LEAPS Opportunity'};
    const stateCn={IDLE:'等待条件',NEAR_TRIGGER:'接近条件',TRIGGERED:'当前状态触发',UNDETERMINED:'数据不足'};
    const evidenceCn={unverified:'未验证',verified:'已验证',research_only:'仅研究'};
    const lifecycleCn={active:'运行中',paused:'暂停',retired:'停用'};
    const rows=d.playbooks.map(x=>`<tr><td><b>${esc(x.playbook_id)}</b><small>${esc(names[x.playbook_id]||'')}</small></td><td>${esc(x.symbol)}</td><td>${esc(stateCn[x.state]||x.state)}<small>${esc(x.detail||'')}</small></td><td>${x.runtime?.ledger_active===false?'人为暂停':'运行中'}</td><td>${esc(evidenceCn[x.evidence]||x.evidence||'未验证')}</td><td>v${esc(x.rule_version||'—')}</td></tr>`).join('');
    const s=d.stabilization||{},streams=a.streams||{},root=String(a.root_hash||'');
    const counts=['trigger','audit','discipline','correction'].map(k=>`${k} ${streams[k]?.count??0}`).join(' · ');
    return `<div class="agent-section-title"><b>Playbook · 剧本运行摘要</b><span>只读 · 不展示私有账本内容</span></div>
      <details class="agent-card agent-watch" open><summary><b>前瞻时钟与 7 个剧本对象</b> · 稳定期 ${s.completed_sessions??'—'}/${s.target_sessions??10} 个交易日</summary>
      <div class="journal-table-wrap"><table class="journal-table"><thead><tr><th>剧本</th><th>标的</th><th>当前状态</th><th>运行</th><th>证据</th><th>规则</th></tr></thead><tbody>${rows}</tbody></table></div>
      <div class="agent-metrics"><span>Heartbeat ${esc(d.heartbeat?.status||'—')}</span><span>Data Quality ${esc(d.data_quality?.status||'—')}</span><span>Kill Switch ${d.kill_switch?.global_enabled===false?'已暂停':'正常'}</span><span>Ledger ${esc(a.status||d.storage?.health||'—')}</span></div>
      <p><strong>Forward 起始：</strong>${esc(s.start_market_date||'2026-10-02')} · <strong>账本摘要：</strong>${esc(counts)} · <strong>Root：</strong>${esc(root?root.slice(0,10)+'…':'—')}</p>
      ${outcomeShadowHtml()}
      ${replayShadowHtml()}
      <small>CP-02 的 full_restore 若是启动基线，只表示当前允许恢复目标敞口，不代表新的 Forward Trigger；Raw Ledger 始终留在私有仓库。</small></details>`;
  }

  function systemStatusHtml(){
    const s=state.systemStatus;if(!s)return'';
    const q=s.workflows?.['quant-dashboard']||{},w=s.workflows?.['wxc-bot']||{};
    const sourceArtifact=(s.artifacts||{}).source_intelligence||{};
    const sourceRun=q['Source Intelligence Validation']||{};
    const sourceRecovered=sourceRun.health==='bad'&&sourceArtifact.freshness==='fresh'&&sourceArtifact.updated_at&&sourceRun.updated_at&&new Date(sourceArtifact.updated_at)>new Date(sourceRun.updated_at);
    const rows=[
      ['Daily Dashboard',q['Daily Dashboard Update']],
      ['Autonomous QA',q['Autonomous QA & Security']],
      ['Source Intelligence',sourceRecovered?{...sourceRun,health:'ok',_recovered:true}:sourceRun],
      ['Trend Pulse 5Y',q['Trend Pulse 5Y Backtest']],
      ['Pages',q['pages build and deployment']],
      ['Playbook巡检',q['Playbook Independent Watchdog']],
      ['收盘研究采集',w['research-close']],
      ['TG采集',w['tg-bot']]
    ];
    const cn=x=>x==='ok'?'正常':x==='running'?'运行中':x==='bad'?'异常':x==='neutral'?'跳过':'未知';
    const cls=x=>x==='ok'?'positive':x==='bad'?'negative':'';
    const latest=state.sourceIntel?.generated_at||'—';
    const artifacts=s.artifacts||{},contract=s.decision_data_contract||{};
    const critical=contract.critical_artifacts||[];
    const freshnessNames={autonomous_agent:'自主研究',breadth_intelligence:'市场宽度',cross_asset_divergence:'跨资产',learning_engine:'学习引擎',market_dashboard:'市场数据',regime_combination_memory:'组合情境'};const freshness=critical.map(name=>{const a=artifacts[name]||{};const label=a.freshness==='fresh'?'新鲜':a.freshness==='stale'?'陈旧':a.freshness==='expired'?'过期':a.freshness==='missing'?'缺失':'未知';return `${freshnessNames[name]||name} · ${label}${a.age_hours!==null&&a.age_hours!==undefined?` ${a.age_hours}h`:''}`;});
    const excluded=contract.excluded_artifacts||[];
    const pr=s.playbook_runtime||{},ph=pr.heartbeat||{},pq=pr.data_quality||{},ps=pr.storage||{},pk=pr.kill_switch||{};
    const playbookText=pr.mode==='silent_forward'
      ? `静默前瞻 · 心跳${ph.status==='pass'?'正常':'异常'} · 数据${pq.status==='pass'?'通过':'需关注'} · 账本${pr.ledger_anchor_status==='ok'?'正常':'需关注'}`
      : `观察模式 · 私有账本${ps.configured?'已配置':'尚未配置'}`;
    const killText=pk.global_enabled===false?'全局已暂停':pk.ledger_enabled===false?'新触发记账已暂停':pk.alerts_enabled?'提醒已启用':'提醒静默';
    return `<div class="agent-section-title"><b>System Status · 自主系统状态</b><span>${s.overall==='ok'?'运行正常':s.overall==='running'?'正在运行':'需要关注'}</span></div>
      <div class="agent-grid"><article class="agent-card agent-watch"><div class="agent-card-head"><div><span>PIPELINE HEALTH</span><h3>采集 → 学习 → 验证 → 部署</h3></div><b>${esc(humanTime(s.generated_at))}</b></div>
      <div class="agent-metrics">${rows.map(([name,x])=>`<span class="${cls(x?.health)}">${esc(name)} · ${esc(x?._recovered?'已由后续更新恢复':cn(x?.health))}</span>`).join('')}</div>
      <p><strong>最近 Source Intelligence：</strong>${esc(humanTime(latest))}</p>
      <p><strong>关键数据新鲜度：</strong>${freshness.map(esc).join(' · ')||'等待状态数据'}</p>
      <p><strong>Playbook：</strong>${esc(playbookText)} · ${esc(killText)}${pr.unresolved_failure?' · 存在未恢复的隔离故障':''}</p>
      ${excluded.length?`<p class="negative"><strong>已暂停参与当前判断：</strong>${excluded.map(esc).join(' · ')}</p>`:''}
      <small>缓存或过期关键产物只保留为历史上下文，不继续参与当前研究结论；Daily Dashboard、Autonomous QA 或收盘研究采集失败也会直接标记异常。</small></article></div>`;
  }

  function sourceIntelHtml(){
    const rows=state.sourceIntel?.research_alerts||[];
    if(!rows.length)return'';
    return `<div class="agent-section-title"><b>Source Intelligence · 外部研究线索</b><span>${rows.length} 条待独立核验</span></div>
      <div class="agent-grid">${rows.slice(0,6).map(x=>`<article class="agent-card agent-review">
        <div class="agent-card-head"><div><span>EXTERNAL SOURCE · ${esc(x.author||'未知作者')}</span><h3>${esc((x.symbols||[]).join(' / ')||x.title||'研究线索')}</h3></div><b>研究优先级 ${x.priority||60}</b></div>
        <p><strong>来源观点：</strong>${esc(x.source_view||x.title||'')}</p>
        <p><strong>MyAlpha判断：</strong>${esc(x.myalpha_view||'先独立验证')}</p>
        <div class="agent-change"><b>什么情况会升级判断</b><span>${esc(x.what_changes_view||'需要独立证据与后续结果')}</span></div>
        <small>${esc(x.published_at||'')} · <a href="${esc(x.url||'#')}" target="_blank" rel="noopener noreferrer">查看作者原文</a> · 作者观点仅作研究来源</small>
      </article>`).join('')}</div>`;
  }

  function termHelp(term){
    const g=state.evidenceData?.glossary?.[term];
    if(!g)return'';
    return `<details class="agent-term-help"><summary>${esc(term)} · ${esc(g.cn||'术语解释')}</summary><p><b>这是什么意思：</b>${esc(g.plain||'')}</p><p><b>为什么重要：</b>${esc(g.why||'')}</p></details>`;
  }
  function evidenceHtml(){
    const top=state.evidenceData?.breadcrumb_engine?.top||[];
    if(!top.length)return'';
    return `<div class="agent-section-title"><b>Evidence Map · 证据地图</b><span>先解释，再判断</span></div>
      <div class="agent-grid">${top.slice(0,6).map(x=>`<article class="agent-card agent-watch">
        <div class="agent-card-head"><div><span>BREADCRUMB ENGINE</span><h3>${esc(x.symbol)} · ${esc(x.trend_state?.label_cn||'观察')}</h3></div><b>证据 ${x.evidence_score}/100</b></div>
        <p><strong>现在是什么意思：</strong>${esc(x.trend_state?.explanation||'')}</p>
        ${termHelp(x.trend_state?.state)}
        <ul>${(x.breadcrumbs||[]).slice(0,4).map(b=>`<li><b>${esc(b.evidence)}</b><br><small>${esc(b.meaning)}</small></li>`).join('')}</ul>
        <div class="agent-change"><b>什么情况会改变判断</b><span>${esc(x.next_confirmation||'继续等待新证据')}</span></div>
        <small>${esc(x.source_scope||'')}</small>
      </article>`).join('')}</div>`;
  }
  function attributionHtml(){
    const f=state.evidenceData?.failure_attribution;
    if(!f)return'';
    const rows=f.recent||[];
    return `<div class="agent-section-title"><b>Failure Attribution · 错误归因</b><span>${f.review_samples||0} 个需要复盘的成熟样本</span></div>
      ${termHelp('Failure Attribution')}
      ${rows.length?`<div class="agent-grid">${rows.slice(0,4).map(x=>`<article class="agent-card agent-review">
        <div class="agent-card-head"><div><span>OUTCOME REVIEW</span><h3>${esc(x.symbol)} · ${esc(x.date||'')}</h3></div><b>20日 ${pct(x.return_20,1)}</b></div>
        <p>${(x.attribution_hypotheses||[]).map(esc).join(' ')}</p>
        <small>${esc(x.guardrail||'')}</small>
      </article>`).join('')}</div>`:'<div class="agent-empty">暂无新的成熟失败样本需要归因。</div>'}`;
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
    const absDelta=m.delta===null?null:Math.abs(m.delta),capture=m.pnlPct;
    const rawCloseCostRatio=capture===null?null:Math.max(0,1-capture);
    const uncapturedOriginalRatio=rawCloseCostRatio===null?null:Math.max(0,Math.min(1,rawCloseCostRatio));
    const lossOverhang=rawCloseCostRatio===null?0:Math.max(0,rawCloseCostRatio-1);
    const assignment=String(position.assignment_mode||'accept').toLowerCase(),note=String(position.strategy_note||'').toLowerCase();
    const premiumPriority=/权利金|premium|income|收租|theta/.test(note),strike=n(position.strike);
    let strikeBuffer=null;
    if(m.spot!==null&&strike){
      if(type==='put')strikeBuffer=(m.spot-strike)/m.spot;
      else if(type==='call')strikeBuffer=(strike-m.spot)/m.spot;
    }
    let score=50;const positives=[],risks=[],components={};
    if(short&&capture!==null){
      if(capture>=0){
        const v=Math.min(18,uncapturedOriginalRatio*18);score+=v;components.remainingPremium=Math.round(v);
        positives.push('尚未兑现的原始权利金约 '+pct(uncapturedOriginalRatio,0));
      }else{
        const penalty=Math.min(22,8+lossOverhang*20);score-=penalty;components.lossOverhang=-Math.round(penalty);
        risks.push('当前买回成本约为原始权利金的 '+pct(rawCloseCostRatio,0)+'（浮亏 '+pct(Math.abs(capture),0)+'）');
      }
    }
    if(absDelta!==null){
      if(absDelta<=0.15){score+=12;components.delta=12;positives.push('|Delta| '+absDelta.toFixed(2)+' 较低')}
      else if(absDelta>=0.35){score-=18;components.delta=-18;risks.push('|Delta| '+absDelta.toFixed(2)+' 较高')}
      else components.delta=0;
    }
    if(Number.isFinite(m.dte)){
      if(m.dte>=30){score+=8;components.dte=8;positives.push('DTE '+m.dte+'，时间仍充足')}
      else if(m.dte<=7){score-=20;components.dte=-20;risks.push('仅剩 '+m.dte+' DTE')}
      else if(m.dte<=21){score-=8;components.dte=-8;risks.push('进入 '+m.dte+' DTE 临期区')}
    }
    if(m.spread!==null){
      if(m.spread<=0.12){score+=8;components.spread=8;positives.push('价差约 '+pct(m.spread,0)+'，执行成本可控')}
      else if(m.spread>0.20){score-=12;components.spread=-12;risks.push('价差约 '+pct(m.spread,0)+' 偏宽')}
    }
    if(strikeBuffer!==null&&short){
      if(strikeBuffer>=0.10){score+=10;components.strikeBuffer=10;positives.push('距行权价缓冲约 '+pct(strikeBuffer,0))}
      else if(strikeBuffer>=0.05){score+=4;components.strikeBuffer=4;positives.push('距行权价缓冲约 '+pct(strikeBuffer,0))}
      else if(strikeBuffer<=0.03){score-=15;components.strikeBuffer=-15;risks.push('距行权价缓冲仅 '+pct(strikeBuffer,0))}
    }
    if(m.iv!==null){
      if(short&&m.iv>=0.50&&!immediateEvents.length){score+=4;components.iv=4;positives.push('IV '+pct(m.iv,0)+'，权利金环境较高')}
      else if(!short&&m.iv>=0.60){score-=6;components.iv=-6;risks.push('IV '+pct(m.iv,0)+' 较高，Long仓位波动率回落风险更大')}
    }
    if(immediateEvents.length){score-=18;components.event=-18;risks.push('未来2天存在事件风险')}
    else if(nearEvents.length){score-=10;components.event=-10;risks.push('未来7天存在事件风险')}
    if(short&&type==='put'&&assignment==='avoid'){
      if(absDelta!==null&&absDelta>=0.30){score-=12;components.assignment=-12;risks.push('不愿接货且行权风险上升')}
      else positives.push('已标记尽量避免被指派');
    }
    if(capture!==null&&capture>=0.80){score-=15;components.capture=-15;risks.push('主要权利金已兑现')}
    else if(premiumPriority&&capture!==null&&capture>=0.70){score-=8;components.premiumGoal=-8;risks.push('权利金优先目标已大部分兑现')}
    if(premiumPriority)positives.push('策略备注识别为权利金优先');
    score=Math.max(0,Math.min(100,Math.round(score)));
    return{
      version:'v2',calculationVersion:'2.1',score,label:score>=75?'高':score>=55?'中高':score>=40?'中':score>=25?'偏低':'低',
      positives,risks,components,
      remainingPremiumRatio:uncapturedOriginalRatio,
      currentCloseCostRatio:rawCloseCostRatio,
      lossOverhangRatio:lossOverhang,
      strikeBuffer,premiumPriority
    };
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
    const assignment=String(position.assignment_mode||'accept').toLowerCase();
    const purpose=String(position.strategy_note||'').trim();
    const capture=m.pnlPct;
    const remaining=capture===null?null:Math.max(0,Math.min(1,1-capture));
    const spreadGood=m.spread!==null&&m.spread<=0.12;
    const spreadWide=m.spread!==null&&m.spread>0.20;
    const deltaLow=absDelta!==null&&absDelta<=0.15;
    const deltaHigh=absDelta!==null&&absDelta>=0.35;
    const nearStrike=m.spot!==null&&strike?m.spot/strike-1:null;
    const edgeScore=remainingEdge(position,m,nearEvents,immediateEvents);

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

  function decisionDataBlock(){
    const contract=state.systemStatus?.decision_data_contract||{};
    const excluded=Array.isArray(contract.excluded_artifacts)?contract.excluded_artifacts:[];
    const critical=new Set(['market_dashboard','learning_engine','autonomous_agent','cross_asset_divergence','breadth_intelligence','regime_combination_memory']);
    const blocked=excluded.filter(x=>critical.has(x));
    return{blocked:blocked.length>0,excluded:blocked,rule:contract.rule||''};
  }

  function publicAttention(policy){
    if(decisionDataBlock().blocked)return[];
    const rows=state.publicData?.attention_summary?.top_attention||[];
    return rows.map(x=>applyLearningPolicy({kind:'stock',symbol:x.symbol,label:x.stage||'Watchlist',level:x.level,timing:x.timing,action:x.action,reasons:x.reasons||[],metrics:{day_change:x.day_change,research_priority:x.research_priority}},policy));
  }

  function card(item){
    const m=item.metrics||{};
    const metrics=item.kind==='option'
      ?[`P/L ${m.pnlPct===null?'—':pct(m.pnlPct,0)}`,`DTE ${m.dte??'—'}`,`Δ ${m.delta===null?'—':Number(m.delta).toFixed(2)}`,`IV ${m.iv===null?'—':pct(m.iv,0)}`,`价差 ${m.spread===null?'—':pct(m.spread,0)}`]
      :[`当日 ${m.day_change===null||m.day_change===undefined?'—':pct(m.day_change,1)}`,`研究优先级 ${m.research_priority??'—'}`,`学习调整 ${m.learning_adjustment>0?'+':''}${m.learning_adjustment||0}`];
    const decision=item.decision||levelLabel(item.level);
    const change=item.changeConditions?.length?`<div class="agent-change"><b>改变判断的条件</b><span>${item.changeConditions.slice(0,4).map(esc).join(' · ')}</span></div>`:'';
    const edge=item.edge?`<div class="agent-edge"><b>剩余风险收益：</b>${esc(item.edge)}</div>`:'';
    const edgeScore=item.remainingEdge?'<div class="agent-edge"><b>Remaining Edge：</b>'+item.remainingEdge.score+'/100 · '+esc(item.remainingEdge.label)+(item.remainingEdge.positives?.length?'<br><span>支持：'+item.remainingEdge.positives.slice(0,3).map(esc).join(' · ')+'</span>':'')+(item.remainingEdge.risks?.length?'<br><span>风险：'+item.remainingEdge.risks.slice(0,3).map(esc).join(' · ')+'</span>':'')+'</div>':'';
    return `<article class="agent-card agent-${esc(item.level)}"><div class="agent-card-head"><div><span>${item.kind==='option'?'PRIVATE POSITION':'WATCHLIST'}</span><h3>${esc(item.symbol)} · ${esc(item.label)}</h3></div><b>${esc(levelLabel(item.level))} · ${esc(item.timing)}</b></div><div class="agent-decision">${esc(decision)}</div><div class="agent-metrics">${metrics.map(x=>`<span>${esc(x)}</span>`).join('')}</div><p><strong>当前方案：</strong>${esc(item.action)}</p>${edgeScore}${edge}${item.reasons?.length?`<ul>${item.reasons.slice(0,5).map(r=>`<li>${esc(r)}</li>`).join('')}</ul>`:''}${change}${item.kind==='option'?'<small>系统不会自动下单；若执行，请以券商实时报价、保证金与公司事件为最终确认。</small>':''}</article>`;
  }

  function render(){
    const center=$('agentCenterRoot'),home=$('agentAttentionRoot');const host=center||home;if(!host)return;
    const policy=buildLearningPolicy();
    const dataBlock=decisionDataBlock();
    const pub=publicAttention(policy),priv=privateAttention();
    const optionAttention=priv.filter(x=>x.level!=='quiet').sort((a,b)=>rank(b.level)-rank(a.level)||((a.metrics?.dte??999)-(b.metrics?.dte??999)));
    const stockAttention=pub.filter(x=>x.level!=='quiet').sort((a,b)=>rank(b.level)-rank(a.level));
    const all=[...optionAttention,...stockAttention];
    const tracked=all.map(item=>({...item,_change:trackDecision(item)}));
    const changed=tracked.filter(x=>x._change.changed);
    const repeatPenalty=policy.adjustments.repeat_alert_penalty||0;
    const visibleTracked=tracked.filter(x=>!(repeatPenalty<0&&x.kind==='stock'&&x.level==='watch'&&!x._change.changed&&!x._change.isNew));
    const quietSuppressed=tracked.length-visibleTracked.length;
    const counts={action:visibleTracked.filter(x=>x.level==='action').length,review:visibleTracked.filter(x=>x.level==='review').length,watch:visibleTracked.filter(x=>x.level==='watch').length};
    const discovery=state.publicData?.discovery_queue||[];
    const selfReview=global.MAVDecisionJournal?.getSelfReview?.()||null;
    const learned=selfReview?.lessons||[];
    const visibleOptions=visibleTracked.filter(x=>x.kind==='option');
    const visibleStocks=visibleTracked.filter(x=>x.kind==='stock');
    const optionsHtml=visibleOptions.length?`<div class="agent-section-title"><b>期权持仓决策</b><span>${visibleOptions.length} 笔需要注意</span></div><div class="agent-grid">${visibleOptions.map(card).join('')}</div>`:'<div class="agent-section-title"><b>期权持仓决策</b><span>当前无需要处理的异常</span></div>';
    const stocksHtml=visibleStocks.length?`<div class="agent-section-title"><b>关注股与核心资产</b><span>${visibleStocks.length} 项需要显示${quietSuppressed?` · 已降噪 ${quietSuppressed}`:''}</span></div><div class="agent-grid">${visibleStocks.map(card).join('')}</div>`:'<div class="agent-section-title"><b>关注股与核心资产</b><span>当前无重要变化</span></div>';
    host.innerHTML=`<div class="agent-attention-head"><div><span class="agent-kicker">MYALPHA AUTONOMOUS AGENT · V6.9</span><h2>自主研究助手</h2><p>不是只告诉你“需要复查”，而是明确说明今天做什么、为什么、什么条件会改变判断。</p></div><div class="agent-counts"><span class="action">需处理 <b>${counts.action}</b></span><span class="review">需复查 <b>${counts.review}</b></span><span>观察 <b>${counts.watch}</b></span></div></div>
      ${dataBlock.blocked?`<div class="agent-empty"><strong>当前公开研究判断已暂停：</strong>关键数据 ${dataBlock.excluded.map(esc).join('、')} 已超过新鲜度阈值。系统仍可显示历史上下文与私有期权实时检查，但不会把陈旧缓存当成当前市场结论。</div>`:''}
      ${tracked.length?`<div class="agent-section-title"><b>Changed Since Last Decision</b><span>${changed.length} 项变化</span></div>${changed.length?`<div class="agent-grid">${changed.slice(0,6).map(card).join('')}</div>`:'<div class="agent-empty">当前判断与上次一致，不重复打扰。</div>'}`+optionsHtml+stocksHtml:'<div class="agent-empty">当前没有需要打扰你的重大变化；系统仍在后台记录和学习。</div>'}
      <div class="agent-section-title"><b>Learning Policy · 学习策略</b><span>v${policy.version} · ${policy.baselineMode?'基线模式':'自主学习生效'} · 可审计</span></div>
      <div class="agent-grid"><article class="agent-card agent-watch"><div class="agent-card-head"><div><span>AUDITABLE POLICY</span><h3>研究权重调整</h3></div><b>成熟样本 ${policy.evidence.sample}</b></div><div class="agent-metrics"><span>二次启动 ${policy.adjustments.restart_bonus>=0?'+':''}${policy.adjustments.restart_bonus}</span><span>重复提醒 ${policy.adjustments.repeat_alert_penalty}</span><span>弱候选 ${policy.adjustments.weak_candidate_penalty}</span></div><p>证据：错过上涨 ${policy.evidence.missed} · 噪音 ${policy.evidence.noisy} · 误报 ${policy.evidence.false_positive}</p><small>仅影响研究优先级与提醒显示；不改变核心ETF阈值、仓位或交易规则。</small><div><button type="button" onclick="MAVAutonomousAgent.resetLearningPolicy()">回到学习基线</button> <button type="button" onclick="MAVAutonomousAgent.resumeLearningPolicy()">恢复自主学习</button></div></article></div>
      ${learned.length?`<div class="agent-section-title"><b>What I learned · 自主学习</b><span>${selfReview.sample||0} 个成熟样本</span></div><div class="agent-grid">${learned.slice(0,3).map((x,i)=>`<article class="agent-card agent-watch"><div class="agent-card-head"><div><span>SELF REVIEW</span><h3>学习结论 #${i+1}</h3></div><b>研究权重</b></div><p>${esc(x)}</p><small>只调整研究优先级和提醒权重，不自动改变核心ETF阈值，也不自动交易。</small></article>`).join('')}</div>`:''}
      ${crossAssetHtml()}
      ${breadthIntelligenceHtml()}
      ${regimeMemoryHtml()}
      ${rangeIntelligenceHtml()}
      ${learningEvaluationHtml()}
      ${brainHtml()}
      ${playbookRuntimeHtml()}
      ${systemStatusHtml()}\n      ${sourceIntelHtml()}
      ${evidenceHtml()}
      ${attributionHtml()}
      ${termHelp('Research Priority')}
      ${discovery.length?`<details class="agent-discovery"><summary>自主发现 · 异常机会 ${discovery.length}</summary><div>${discovery.slice(0,8).map(x=>`<p><b>${esc(x.symbol)}</b> · ${pct(x.price_change,1)} · ${esc(x.event_strength)}<br><small>${esc(x.next_step)} ${esc(x.guardrail)}</small></p>`).join('')}</div></details>`:''}
      <div class="agent-foot">自主研究 ≠ 自动交易。系统负责主动发现、解释、排序和提出方案；最终交易仍由投资者确认。</div>`;
    if(home&&center){
      const top=[...optionAttention,...stockAttention].slice(0,3);
      home.innerHTML=`<div class="agent-attention-head"><div><span class="agent-kicker">MYALPHA AUTONOMOUS AGENT · V6 + V7</span><h2>今日 AI 摘要</h2><p>完整研究过程已集中到 AI智能中心；首页只保留真正需要你注意的事项。</p></div><div class="agent-counts"><span class="action">需处理 <b>${counts.action}</b></span><span class="review">需复查 <b>${counts.review}</b></span><span>观察 <b>${counts.watch}</b></span></div></div>${top.length?`<div class="agent-grid">${top.map(card).join('')}</div>`:'<div class="agent-empty">当前没有需要打扰你的重大变化；Agent 仍在后台学习。</div>'}<div class="agent-foot"><button type="button" onclick="openDashboardTab('tab-agent-center')">打开 AI智能中心 · 查看完整研究与自我优化</button></div>`;
    }
    renderCrossAssetMarket();
    state.lastRender=Date.now();
  }

  async function init(){await loadPublic();render();setTimeout(render,2500);setTimeout(render,7000)}
  global.MAVAutonomousAgent={render,loadPublic,optionAdvice,privateAttention,remainingEdge,readMemory,decisionHistory,buildLearningPolicy,resetLearningPolicy,resumeLearningPolicy,decisionDataBlock,state};
  if(typeof document!=='undefined'){
    window.addEventListener('mav:options-updated',()=>render());
    document.addEventListener('DOMContentLoaded',init);
  }
})(typeof window!=='undefined'?window:globalThis);
