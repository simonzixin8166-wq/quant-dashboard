(function () {
  'use strict';
  const root = document.getElementById('financeToolsRoot');
  if (!root) return;

  const $ = (id) => document.getElementById(id);
  const STORAGE_KEY = 'mav_finance_plans_v37';
  const MODES = {
    end: { title: '计算期末资产', answer: '预计期末资产', solve: null },
    contribution: { title: '反推每期投入', answer: '所需定期投入', solve: 'contribution' },
    return: { title: '反推年化收益率', answer: '所需年化复合收益率', solve: 'rate' },
    start: { title: '反推起始本金', answer: '所需起始本金', solve: 'start' },
    length: { title: '反推投资年限', answer: '所需投资年限', solve: 'years' }
  };
  const IDS = {
    target: 'financeTarget', start: 'financeStart', years: 'financeYears', rate: 'financeRate',
    contribution: 'financeContribution', frequency: 'financeFrequency', timing: 'financeTiming', currency: 'financeCurrency'
  };
  let mode = 'end';
  let lastResult = null;
  let compositionChart = null;
  let growthChart = null;
  let editingId = null;
  let deletedPlan = null;
  let deleteTimer = null;

  function number(id) { return Number($(id).value); }
  function readInputs() {
    return {
      target: number(IDS.target), start: number(IDS.start), years: number(IDS.years),
      rate: number(IDS.rate) / 100, contribution: number(IDS.contribution),
      frequency: Number($(IDS.frequency).value), timing: $(IDS.timing).value,
      currency: $(IDS.currency).value
    };
  }
  function writeInputs(p) {
    Object.entries(IDS).forEach(([key, id]) => { if (p[key] !== undefined && p[key] !== null) $(id).value = key === 'rate' ? Number(p[key]) * 100 : p[key]; });
  }
  function money(value, currency) {
    if (!Number.isFinite(value)) return '—';
    return new Intl.NumberFormat('zh-CN', { style: 'currency', currency: currency || 'CNY', maximumFractionDigits: 0 }).format(value);
  }
  function pct(value, digits) { return Number.isFinite(value) ? `${(value * 100).toFixed(digits ?? 1)}%` : '—'; }
  function frequencyName(value) { return ({ 1: '每年', 12: '每月', 52: '每周', 252: '每个交易日' })[value] || '每期'; }
  function validate(p) {
    const errors = [];
    ['target', 'start', 'years', 'rate', 'contribution'].forEach(k => { if (!Number.isFinite(p[k])) errors.push('请完整填写有效数字'); });
    if (p.target < 0 || p.start < 0 || p.contribution < 0) errors.push('金额不能为负数');
    if (p.years <= 0 || p.years > 100) errors.push('投资期限应在0至100年之间');
    if (p.rate <= -1 || p.rate > 2) errors.push('年化收益率应大于-100%且不超过200%');
    if (mode !== 'end' && p.target <= 0) errors.push('反推计算需要填写大于0的目标金额');
    return [...new Set(errors)];
  }
  function simulate(p, forcedSteps) {
    const freq = p.frequency;
    const steps = forcedSteps == null ? Math.max(1, Math.round(p.years * freq)) : Math.max(1, forcedSteps);
    const periodicRate = Math.pow(1 + p.rate, 1 / freq) - 1;
    let balance = p.start;
    let totalInterest = 0;
    let totalContributions = 0;
    let yearStart = balance;
    let yearContribution = 0;
    let yearInterest = 0;
    const schedule = [];
    for (let step = 1; step <= steps; step++) {
      if (p.timing === 'begin') { balance += p.contribution; totalContributions += p.contribution; yearContribution += p.contribution; }
      const earned = balance * periodicRate;
      balance += earned; totalInterest += earned; yearInterest += earned;
      if (p.timing === 'end') { balance += p.contribution; totalContributions += p.contribution; yearContribution += p.contribution; }
      if (step % freq === 0 || step === steps) {
        schedule.push({ year: step / freq, start: yearStart, contribution: yearContribution, interest: yearInterest, end: balance });
        yearStart = balance; yearContribution = 0; yearInterest = 0;
      }
    }
    return { end: balance, principal: p.start + totalContributions, contributions: totalContributions, interest: totalInterest, steps, years: steps / freq, schedule };
  }
  function solveMonotonic(base, field, target, low, high, transform) {
    const valueAt = (x) => simulate({ ...base, [field]: transform ? transform(x) : x }).end;
    while (valueAt(high) < target && high < 1e15) high *= 2;
    if (valueAt(high) < target) throw new Error('在允许范围内无法达到目标，请调整期限、投入或收益率');
    for (let i = 0; i < 90; i++) {
      const mid = (low + high) / 2;
      if (valueAt(mid) >= target) high = mid; else low = mid;
    }
    return high;
  }
  function solveRate(base) {
    let low = -0.99, high = 5;
    const at = (r) => simulate({ ...base, rate: r }).end;
    if (at(low) > base.target) return low;
    if (at(high) < base.target) throw new Error('即使年化收益率达到500%也无法在当前期限内完成目标');
    for (let i = 0; i < 100; i++) { const mid = (low + high) / 2; if (at(mid) >= base.target) high = mid; else low = mid; }
    return high;
  }
  function solveYears(base) {
    const maxSteps = base.frequency * 100;
    if (simulate({ ...base, years: 100 }, maxSteps).end < base.target) throw new Error('在100年范围内仍无法达到目标，请增加投入或调整收益假设');
    let low = 1, high = maxSteps;
    while (low < high) { const mid = Math.floor((low + high) / 2); if (simulate(base, mid).end >= base.target) high = mid; else low = mid + 1; }
    return low / base.frequency;
  }
  function calculate(silent) {
    const original = readInputs();
    const errors = validate(original);
    const validation = $('financeValidation');
    if (errors.length) { validation.textContent = errors.join('；'); validation.classList.add('show'); return null; }
    validation.classList.remove('show');
    let effective = { ...original };
    let answer;
    try {
      if (mode === 'contribution') {
        const noContribution = simulate({ ...effective, contribution: 0 }).end;
        effective.contribution = noContribution >= effective.target ? 0 : solveMonotonic(effective, 'contribution', effective.target, 0, Math.max(1, effective.target / Math.max(1, effective.years * effective.frequency)));
        answer = money(effective.contribution, effective.currency);
      } else if (mode === 'return') {
        effective.rate = solveRate(effective); answer = pct(effective.rate, 2);
      } else if (mode === 'start') {
        const noStart = simulate({ ...effective, start: 0 }).end;
        effective.start = noStart >= effective.target ? 0 : solveMonotonic(effective, 'start', effective.target, 0, Math.max(1, effective.target));
        answer = money(effective.start, effective.currency);
      } else if (mode === 'length') {
        effective.years = solveYears(effective); answer = formatYears(effective.years);
      }
      const result = simulate(effective);
      if (mode === 'end') answer = money(result.end, effective.currency);
      lastResult = { mode, original, effective, result };
      renderResult(answer, lastResult);
      if (!silent) validation.classList.remove('show');
      return lastResult;
    } catch (error) {
      validation.textContent = error.message || '计算失败，请检查输入'; validation.classList.add('show'); return null;
    }
  }
  function formatYears(years) {
    const whole = Math.floor(years + 1e-8);
    const months = Math.round((years - whole) * 12);
    if (months === 12) return `${whole + 1}年`;
    return months ? `${whole}年${months}个月` : `${whole}年`;
  }
  function renderResult(answer, pack) {
    const { original, effective: p, result: r } = pack;
    $('financeAnswerLabel').textContent = MODES[mode].answer;
    $('financeAnswer').textContent = answer;
    $('financeAnswerMeta').textContent = `${formatYears(r.years)} · 年化${pct(p.rate, 2)}`;
    const solved = mode === 'end' ? (original.target > 0 ? `按当前假设估算 · 目标${money(original.target, p.currency)}` : '按当前假设估算') : `为达到${money(original.target, p.currency)}目标`;
    $('financeAnswerHint').textContent = mode === 'contribution' ? `${solved}，${frequencyName(p.frequency)}投入` : solved;
    $('financePrincipal').textContent = money(r.principal, p.currency);
    $('financeInterest').textContent = money(r.interest, p.currency);
    $('financeInterest').className = r.interest >= 0 ? 'positive' : 'negative';
    $('financeInterestShare').textContent = r.end ? pct(r.interest / r.end, 1) : '—';
    $('financeTargetProgress').textContent = original.target > 0 ? pct(r.end / original.target, 1) : '未设置目标';
    renderComposition(p, r); renderGrowth(p, r); renderSchedule(p, r); renderScenarios(p);
  }
  function renderComposition(p, r) {
    const start = Math.max(0, p.start), added = Math.max(0, r.contributions), gains = Math.abs(r.interest);
    const data = [start, added, gains];
    const labels = ['起始本金', '定期投入', r.interest >= 0 ? '投资收益' : '投资亏损'];
    const colors = ['#1f2b52', '#b8863a', r.interest >= 0 ? '#57a577' : '#b23b2e'];
    $('financeCompositionLegend').innerHTML = labels.map((label, i) => `<div><i style="background:${colors[i]}"></i><span>${label}</span><b>${money(i === 2 ? r.interest : data[i], p.currency)}</b></div>`).join('');
    if (!window.Chart) return;
    compositionChart?.destroy();
    compositionChart = new Chart($('financeCompositionChart'), { type: 'doughnut', data: { labels, datasets: [{ data, backgroundColor: colors, borderWidth: 0 }] }, options: { responsive: true, maintainAspectRatio: false, cutout: '68%', plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => `${c.label}: ${money(c.raw, p.currency)}` } } } } });
  }
  function renderGrowth(p, r) {
    if (!window.Chart) return;
    const rows = r.schedule;
    growthChart?.destroy();
    growthChart = new Chart($('financeGrowthChart'), { type: 'bar', data: { labels: rows.map(x => `${Number.isInteger(x.year) ? x.year : x.year.toFixed(1)}年`), datasets: [
      { label: '累计投入本金', data: rows.map((x, i) => p.start + r.schedule.slice(0, i + 1).reduce((s, y) => s + y.contribution, 0)), backgroundColor: '#cdbb91', borderRadius: 3, stack: 'asset' },
      { label: '累计投资收益', data: rows.map(x => x.end - (p.start + r.schedule.filter(y => y.year <= x.year).reduce((s, y) => s + y.contribution, 0))), backgroundColor: '#537a67', borderRadius: 3, stack: 'asset' }
    ] }, options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, scales: { x: { stacked: true, grid: { display: false }, ticks: { maxTicksLimit: 12 } }, y: { stacked: true, ticks: { callback: v => compactMoney(v, p.currency) }, grid: { color: 'rgba(100,100,90,.1)' } } }, plugins: { legend: { position: 'bottom', labels: { boxWidth: 9, usePointStyle: true } }, tooltip: { callbacks: { label: c => `${c.dataset.label}: ${money(c.raw, p.currency)}` } } } } });
  }
  function compactMoney(value, currency) { const sign = currency === 'USD' ? '$' : '¥'; if (Math.abs(value) >= 1e8) return `${sign}${(value / 1e8).toFixed(1)}亿`; if (Math.abs(value) >= 1e4) return `${sign}${(value / 1e4).toFixed(0)}万`; return `${sign}${Math.round(value)}`; }
  function renderSchedule(p, r) {
    $('financeScheduleBody').innerHTML = r.schedule.map(row => `<tr><td>第${row.year.toFixed(row.year % 1 ? 1 : 0)}年</td><td>${money(row.start, p.currency)}</td><td>${money(row.contribution, p.currency)}</td><td class="${row.interest >= 0 ? 'positive' : 'negative'}">${money(row.interest, p.currency)}</td><td><b>${money(row.end, p.currency)}</b></td></tr>`).join('');
  }
  function renderScenarios(p) {
    const rates = [0.05, 0.08, 0.12];
    $('financeScenarios').innerHTML = rates.map(rate => { const r = simulate({ ...p, rate }); return `<div class="finance-scenario ${Math.abs(p.rate - rate) < .0001 ? 'current' : ''}"><span>年化${pct(rate, 0)}</span><strong>${money(r.end, p.currency)}</strong><small>收益 ${money(r.interest, p.currency)}</small></div>`; }).join('');
  }
  function setMode(next) {
    mode = next; editingId = null;
    document.querySelectorAll('[data-finance-mode]').forEach(b => b.classList.toggle('active', b.dataset.financeMode === mode));
    $('financeModeTitle').textContent = MODES[mode].title;
    $('financeAnswerLabel').textContent = MODES[mode].answer;
    document.querySelectorAll('[data-finance-field]').forEach(el => { el.hidden = el.dataset.financeField === MODES[mode].solve; });
    $('financeSave').textContent = '保存当前方案';
    calculate(true);
  }
  function plans() { try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); } catch (_) { return []; } }
  function storePlans(value) { localStorage.setItem(STORAGE_KEY, JSON.stringify(value.slice(0, 30))); }
  function savePlan() {
    const result = calculate(); if (!result) return;
    const list = plans();
    const plan = { id: editingId || (crypto.randomUUID ? crypto.randomUUID() : String(Date.now())), mode, inputs: result.original, updatedAt: new Date().toISOString() };
    const index = list.findIndex(x => x.id === plan.id);
    if (index >= 0) list[index] = plan; else list.unshift(plan);
    storePlans(list); editingId = plan.id; $('financeSave').textContent = '更新当前方案'; renderPlans();
    window.MAV?.toast(index >= 0 ? '理财方案已更新' : '理财方案已保存到本机浏览器', 'success');
  }
  function loadPlan(id) {
    const plan = plans().find(x => x.id === id); if (!plan) return;
    writeInputs(plan.inputs); editingId = id; $('financeSave').textContent = '更新当前方案'; setMode(plan.mode || 'end'); editingId = id; $('financeSave').textContent = '更新当前方案'; calculate(); window.scrollTo({ top: root.offsetTop - 80, behavior: 'smooth' });
  }
  function deletePlan(id) {
    const list = plans(), index = list.findIndex(x => x.id === id); if (index < 0) return;
    if (!confirm('删除这个本机理财方案？删除后可在8秒内撤回。')) return;
    deletedPlan = { plan: list[index], index }; list.splice(index, 1); storePlans(list); if (editingId === id) editingId = null;
    clearTimeout(deleteTimer); deleteTimer = setTimeout(() => { deletedPlan = null; renderPlans(); }, 8000); renderPlans();
  }
  function undoDelete() {
    if (!deletedPlan) return; const list = plans(); list.splice(Math.min(deletedPlan.index, list.length), 0, deletedPlan.plan); storePlans(list); deletedPlan = null; clearTimeout(deleteTimer); renderPlans();
  }
  function renderPlans() {
    const list = plans(), holder = $('financeSavedPlans');
    const undo = deletedPlan ? '<div class="finance-saved-item"><div><strong>方案已删除</strong><small>8秒内可以撤回</small></div><div class="finance-saved-actions"><button data-plan-undo>撤回删除</button></div></div>' : '';
    holder.innerHTML = undo + (list.length ? list.map(plan => { const m = MODES[plan.mode] || MODES.end; const date = new Date(plan.updatedAt).toLocaleDateString('zh-CN'); return `<div class="finance-saved-item"><button data-plan-load="${plan.id}"><strong>${m.title}</strong><small>${date} · ${frequencyName(plan.inputs.frequency)}</small></button><div class="finance-saved-actions"><button data-plan-load="${plan.id}">修改</button><button class="delete" data-plan-delete="${plan.id}">删除</button></div></div>`; }).join('') : '<p>尚未保存方案。保存后可在本机修改或删除。</p>');
  }
  function reset() {
    editingId = null; $('financeSave').textContent = '保存当前方案';
    writeInputs({ target: 1000000, start: 100000, years: 20, rate: .08, contribution: 4000, frequency: 12, timing: 'end', currency: 'CNY' }); setMode('end');
  }
  function exportCsv() {
    const pack = calculate(); if (!pack) return;
    const rows = [['年份', '年初余额', '本年投入', '本年收益', '年末余额'], ...pack.result.schedule.map(x => [x.year, x.start.toFixed(2), x.contribution.toFixed(2), x.interest.toFixed(2), x.end.toFixed(2)])];
    const blob = new Blob(['\ufeff' + rows.map(r => r.join(',')).join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = `理财规划-${new Date().toISOString().slice(0, 10)}.csv`; a.click(); URL.revokeObjectURL(url);
  }

  document.querySelectorAll('[data-finance-mode]').forEach(b => b.addEventListener('click', () => setMode(b.dataset.financeMode)));
  document.querySelectorAll('[data-rate-preset]').forEach(b => b.addEventListener('click', () => { $(IDS.rate).value = b.dataset.ratePreset; document.querySelectorAll('[data-rate-preset]').forEach(x => x.classList.toggle('active', x === b)); calculate(true); }));
  root.querySelectorAll('input,select').forEach(el => el.addEventListener('change', () => calculate(true)));
  $('financeCalculate').addEventListener('click', () => calculate()); $('financeReset').addEventListener('click', reset); $('financeSave').addEventListener('click', savePlan); $('financeExport').addEventListener('click', exportCsv);
  document.querySelectorAll('[data-finance-view]').forEach(b => b.addEventListener('click', () => { const table = b.dataset.financeView === 'table'; $('financeTableView').hidden = !table; $('financeChartView').hidden = table; document.querySelectorAll('[data-finance-view]').forEach(x => x.classList.toggle('active', x === b)); }));
  $('financeSavedPlans').addEventListener('click', e => { const load = e.target.closest('[data-plan-load]'), del = e.target.closest('[data-plan-delete]'), undo = e.target.closest('[data-plan-undo]'); if (load) loadPlan(load.dataset.planLoad); else if (del) deletePlan(del.dataset.planDelete); else if (undo) undoDelete(); });
  renderPlans(); setMode('end');
  window.FinanceTools = { calculate, setMode, loadPlan, deletePlan, undoDelete };
})();
