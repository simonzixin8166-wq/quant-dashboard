(function(global){
'use strict';
const ACTIONS={
  NO_SIGNAL:{label:'NO SIGNAL',zh:'数据不足，暂停判断',tone:'bad',rank:0},
  WATCH:{label:'WATCH',zh:'观察，不介入',tone:'neutral',rank:1},
  EARLY_ENTRY:{label:'EARLY ENTRY',zh:'已达到早期介入机会',tone:'good',rank:4},
  CONFIRMED_ENTRY:{label:'CONFIRMED ENTRY',zh:'已达到确认介入机会',tone:'good',rank:5},
  HOLD:{label:'HOLD',zh:'继续持有',tone:'good',rank:3},
  NO_ADD:{label:'NO ADD',zh:'继续持有，停止加仓',tone:'warn',rank:3},
  REDUCE:{label:'REDUCE',zh:'建议降低部分仓位',tone:'bad',rank:6},
  EXIT:{label:'EXIT',zh:'原逻辑失效，建议退出',tone:'bad',rank:7},
  WAIT:{label:'WAIT',zh:'暂不介入，不追高',tone:'neutral',rank:1}
};
const n=v=>Number.isFinite(Number(v))?Number(v):null;
function result(action,reason,next,meta={}){
  const a=ACTIONS[action]||ACTIONS.WATCH;
  return {action,...a,reason,next_confirmation:next||'',...meta};
}
function classify(input={}){
  const score=n(input.score),stage=String(input.stage||''),held=input.held===true;
  const authority=input.decisionEligible!==false;
  if(!authority)return result('NO_SIGNAL','Data Trust / Decision Authority 未通过，禁止发布行动信号。','等待可信数据恢复',{decision_eligible:false});
  if(input.invalidated===true)return result(held?'EXIT':'WATCH','原始 Thesis / 介入逻辑已明确失效。','重新建立 Thesis 后再评估');
  if(held){
    if(score!==null&&score<=-60)return result('REDUCE','趋势评分进入高风险区；在 Thesis 未明确失效前先降低敞口。','若 Thesis 失效或风险继续扩大则升级 EXIT');
    if(/趋势恶化/.test(stage))return result('NO_ADD','趋势恶化，但当前缺少足够证据直接判定退出。','等待价格结构、基本面与失效条件确认');
    if(/趋势退潮|高位钝化/.test(stage))return result('NO_ADD','上涨动能减弱，停止新增仓位并继续观察。','动量重新增强则恢复 HOLD；风险扩大则 REDUCE');
    return result('HOLD','当前未触发减仓或退出条件。','持续监控趋势、事件与 Thesis 失效条件');
  }
  if(/趋势启动/.test(stage)&&score!==null&&score>=0)return result('EARLY_ENTRY','趋势由弱转强，已进入早期介入观察区。','关键均线/价格结构继续确认后升级 CONFIRMED ENTRY');
  if(/二次启动/.test(stage)&&score!==null&&score>=30)return result('CONFIRMED_ENTRY','回踩后重新转强，趋势结构得到进一步确认。','持续验证量价、事件与风险条件');
  if(/趋势延续/.test(stage)&&score!==null&&score>=50)return result('CONFIRMED_ENTRY','趋势延续且强度达到确认区。','避免追高，等待风险收益合适的执行位置');
  if(/修复中/.test(stage))return result('WATCH','弱势正在修复，但尚不足以形成介入信号。','等待趋势启动与关键位置确认');
  if(/趋势恶化|趋势退潮/.test(stage)||(score!==null&&score<0))return result('WATCH','趋势风险偏高，当前不介入。','等待风险状态解除');
  if(score!==null&&score>=75)return result('WAIT','趋势较强但位置偏热，不把高分直接等同追涨信号。','等待新的风险收益窗口');
  return result('WATCH','当前条件不足以形成明确介入机会。','继续等待状态迁移');
}
function applyLearnedEvidence(base,governance){
  const g=governance||{};
  if(g.learned_production_effect!=='active'||!Array.isArray(g.promoted_families)||!g.promoted_families.length){
    return {...base,learned_overlay:'shadow_only',learned_note:'自主学习结果仍在 Shadow/验证层，不改变正式 Action。'};
  }
  return {...base,learned_overlay:'eligible',learned_note:'仅已通过 Promotion Gate 的方法允许作为正式 Action 的附加证据；保护规则仍优先。'};
}
global.MAVSignalPolicy={ACTIONS,classify,applyLearnedEvidence};
})(window);
