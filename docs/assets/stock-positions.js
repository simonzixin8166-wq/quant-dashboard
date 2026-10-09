/* Private stock ledger (quant-dashboard#133 item B).
 * Owner-only Supabase table `stock_positions` (RLS; one open row per account+symbol).
 * Manual entry only: no broker link, no import of existing holdings, no trading.
 * Accounts are always shown separately and never summed together.
 * Nothing here is written to public docs, console or analytics.
 */
(function(global){
  'use strict';
  const STALE_DAYS=7;
  const state={session:null,accounts:[],rows:[],showArchived:false,editId:null,error:null,loaded:false};
  const $=id=>document.getElementById(id);
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const sb=()=>typeof supabaseClient!=='undefined'?supabaseClient:(global.mavSupabase||null);
  const toast=(m,t)=>global.MAV?.toast?.(m,t);
  const num=v=>{if(v===null||v===undefined||v==='')return null;const n=Number(v);return Number.isFinite(n)?n:null};
  const fmt=(v,d=2)=>v===null||v===undefined?'—':Number(v).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});

  function ageDays(ts,now=Date.now()){const t=Date.parse(ts||'');return Number.isFinite(t)?(now-t)/86400000:Infinity}
  function isStale(row,now=Date.now()){return ageDays(row.data_as_of,now)>STALE_DAYS}

  /* Group per account; never merge rows across accounts. */
  function groupByAccount(rows,accounts){
    const names=new Map((accounts||[]).map(a=>[String(a.id),a.name||`账户 ${a.id}`]));
    const groups=new Map();
    (rows||[]).forEach(r=>{const k=String(r.broker_account_id);if(!groups.has(k))groups.set(k,{account_id:k,name:names.get(k)||'未知账户',rows:[]});groups.get(k).rows.push(r)});
    return [...groups.values()].sort((a,b)=>a.name.localeCompare(b.name,'zh'));
  }

  function validate(input){
    const errs=[];
    const symbol=String(input.symbol||'').trim().toUpperCase();
    if(!/^[A-Z0-9.-]{1,12}$/.test(symbol))errs.push('代码格式不正确');
    const shares=num(input.shares);if(!(shares>0))errs.push('股数必须大于 0');
    const cost=num(input.cost_basis);if(cost!==null&&cost<0)errs.push('成本不能为负');
    if(!input.broker_account_id)errs.push('请选择账户');
    const note=String(input.note||'').trim();if(note.length>300)errs.push('备注不超过 300 字');
    return {ok:!errs.length,errs,payload:{broker_account_id:Number(input.broker_account_id),symbol,shares,cost_basis:cost,opened_at:input.opened_at||null,note:note||null}};
  }

  async function load(){
    const root=$('stockLedgerRoot');if(!root)return;const c=sb();
    if(!c){state.loaded=true;render();return}
    try{
      const {data:{session}}=await c.auth.getSession();state.session=session;
      if(!session){state.rows=[];state.accounts=[];state.loaded=true;render();return}
      const [a,p]=await Promise.all([
        c.from('broker_accounts').select('id,name,is_active,sort_order').order('sort_order').order('name'),
        c.from('stock_positions').select('*').order('symbol')
      ]);
      if(a.error)throw a.error;
      if(p.error){state.error=/stock_positions|schema cache|does not exist/i.test(p.error.message)?'私有正股账本尚未部署。':p.error.message;state.rows=[]}
      else{state.error=null;state.rows=p.data||[]}
      state.accounts=a.data||[];
    }catch(e){state.error=e.message||String(e)}
    state.loaded=true;render();
  }

  function rowHtml(r){
    const stale=r.status==='open'&&isStale(r);
    const asOf=r.data_as_of?new Date(r.data_as_of).toLocaleDateString('zh-CN',{timeZone:'Asia/Shanghai'}):'—';
    const actions=r.status==='open'
      ?`<button type="button" data-sp="edit" data-id="${esc(r.id)}">修改</button><button type="button" data-sp="verify" data-id="${esc(r.id)}" title="与券商核对无误后点击，更新核对时间">核对无误</button><button type="button" data-sp="archive" data-id="${esc(r.id)}">归档</button>`
      :`<button type="button" data-sp="delete" data-id="${esc(r.id)}">删除</button>`;
    return `<tr class="${stale?'sp-stale':''}${r.status==='archived'?' sp-archived':''}"><td><b>${esc(r.symbol)}</b></td><td>${fmt(r.shares,r.shares%1?4:0)}</td><td>${r.cost_basis===null?'<span class="sp-muted">未填</span>':fmt(r.cost_basis)}</td><td>${esc(r.opened_at||'—')}</td><td>${esc(asOf)}${stale?' <span class="sp-badge">需核对</span>':''}</td><td class="sp-note">${esc(r.note||'')}</td><td class="sp-actions">${actions}</td></tr>`;
  }

  function formHtml(){
    const r=state.editId?state.rows.find(x=>String(x.id)===String(state.editId)):null;
    const opts=state.accounts.filter(a=>a.is_active!==false||(r&&String(a.id)===String(r.broker_account_id))).map(a=>`<option value="${esc(a.id)}"${r&&String(r.broker_account_id)===String(a.id)?' selected':''}>${esc(a.name)}</option>`).join('');
    return `<form id="spForm" class="sp-form" autocomplete="off"><select id="spAccount" required><option value="">选择账户</option>${opts}</select><input id="spSymbol" placeholder="代码 如 QQQM" maxlength="12" value="${esc(r?.symbol||'')}" ${r?'readonly':''} required><input id="spShares" type="number" step="0.0001" min="0" placeholder="股数" value="${esc(r?.shares??'')}" required><input id="spCost" type="number" step="0.0001" min="0" placeholder="每股成本（可选）" value="${esc(r?.cost_basis??'')}"><input id="spOpened" type="date" value="${esc(r?.opened_at||'')}" title="建仓日期（可选）"><input id="spNote" maxlength="300" placeholder="备注（可选）" value="${esc(r?.note||'')}"><button class="primary" type="submit">${r?'保存修改':'添加'}</button>${r?'<button type="button" data-sp="cancel">取消</button>':''}</form>`;
  }

  function render(){
    const root=$('stockLedgerRoot');if(!root)return;
    if(!state.loaded){root.innerHTML='<div class="sp-muted">加载中…</div>';return}
    if(!state.session){root.innerHTML='<div class="sp-muted">登录后显示你的私有正股账本（仅本人可见）。</div>';return}
    if(state.error){root.innerHTML=`<div class="sp-muted">${esc(state.error)}</div>`;return}
    const shown=state.rows.filter(r=>state.showArchived||r.status==='open');
    const groups=groupByAccount(shown,state.accounts);
    const staleN=state.rows.filter(r=>r.status==='open'&&isStale(r)).length;
    const head='<thead><tr><th>代码</th><th>股数</th><th>每股成本</th><th>建仓日</th><th>核对日期</th><th>备注</th><th></th></tr></thead>';
    const body=groups.length?groups.map(g=>`<div class="sp-account"><div class="sp-account-name">${esc(g.name)} <span class="sp-muted">· ${g.rows.filter(r=>r.status==='open').length} 只持仓</span></div><div class="sp-table-wrap"><table class="sp-table">${head}<tbody>${g.rows.map(rowHtml).join('')}</tbody></table></div></div>`).join(''):'<div class="sp-muted">暂无记录。请按券商实际持仓手工录入；系统不会自动导入或交易。</div>';
    root.innerHTML=`<div class="sp-head"><div><b>我的正股持仓</b> <span class="sp-muted">私有 · 手工录入 · 各账户分开显示，不合并</span></div><label class="sp-muted"><input type="checkbox" id="spShowArchived"${state.showArchived?' checked':''}> 显示已归档</label></div>${staleN?`<div class="sp-warn">${staleN} 条持仓超过 ${STALE_DAYS} 天未核对，请与券商核对后点击“核对无误”或修改。</div>`:''}${state.accounts.length?formHtml():'<div class="sp-muted">请先在期权中心的账户管理中添加券商账户。</div>'}${body}`;
  }

  async function submit(ev){
    ev.preventDefault();const c=sb();if(!c||!state.session)return;
    const v=validate({broker_account_id:$('spAccount')?.value,symbol:$('spSymbol')?.value,shares:$('spShares')?.value,cost_basis:$('spCost')?.value,opened_at:$('spOpened')?.value,note:$('spNote')?.value});
    if(!v.ok){toast(v.errs.join('；'),'warn');return}
    const now=new Date().toISOString();
    const q=state.editId
      ?c.from('stock_positions').update({...v.payload,data_as_of:now}).eq('id',state.editId)
      :c.from('stock_positions').insert({...v.payload,user_id:state.session.user.id,data_as_of:now});
    const {error}=await q;
    if(error){const dup=/duplicate|unique/i.test(error.message);toast(dup?'该账户已有这只股票的持仓记录，请修改原记录。':/ACCOUNT_NOT_OWNED/.test(error.message)?'账户无效。':`保存失败：${error.message}`,'bad');return}
    state.editId=null;await load();toast('已保存（仅记录，不会下单）','good');
  }

  async function act(kind,id){
    const c=sb();const r=state.rows.find(x=>String(x.id)===String(id));
    if(kind==='cancel'){state.editId=null;render();return}
    if(!c||!r)return;
    if(kind==='edit'){state.editId=r.id;render();$('spShares')?.focus();return}
    let res;
    if(kind==='verify')res=await c.from('stock_positions').update({data_as_of:new Date().toISOString()}).eq('id',r.id);
    else if(kind==='archive'){if(!confirm(`归档 ${r.symbol}？\n\n仅标记为已清仓/不再持有，不会卖出任何证券。`))return;res=await c.from('stock_positions').update({status:'archived',archived_at:new Date().toISOString()}).eq('id',r.id)}
    else if(kind==='delete'){if(prompt(`永久删除已归档的 ${r.symbol} 记录（用于纠正误录）。输入 DELETE 确认`)!=='DELETE')return;res=await c.from('stock_positions').delete().eq('id',r.id).eq('status','archived')}
    if(res?.error){toast(`操作失败：${res.error.message}`,'bad');return}
    await load();
  }

  function bind(){
    const root=$('stockLedgerRoot');if(!root||root.dataset.bound)return;root.dataset.bound='1';
    root.addEventListener('submit',e=>{if(e.target.id==='spForm')submit(e)});
    root.addEventListener('click',e=>{const b=e.target.closest('[data-sp]');if(b)act(b.dataset.sp,b.dataset.id)});
    root.addEventListener('change',e=>{if(e.target.id==='spShowArchived'){state.showArchived=e.target.checked;render()}});
    load();
    const c=sb();if(c?.auth?.onAuthStateChange)c.auth.onAuthStateChange(()=>setTimeout(load,0));
  }

  global.StockPositions={load,render,_test:{groupByAccount,validate,isStale,ageDays,STALE_DAYS}};
  if(typeof document!=='undefined'){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind()}
})(typeof window!=='undefined'?window:globalThis);
