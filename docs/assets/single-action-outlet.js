(function(global){
'use strict';
const AUTHORITY_TAB='tab-overview';
const ACTION_WORDS=['EARLY ENTRY','CONFIRMED ENTRY','HOLD','NO ADD','REDUCE','EXIT'];
const SECONDARY_TABS=['tab-agent-center','tab-index','tab-stocks','tab-options','tab-engine','tab-wenxuecity','tab-knowledge','tab-journal','tab-system-health'];
function bannerHtml(){
 return '<div class="single-action-banner" data-single-action-banner="true"><div><b>研究 / 解释页面</b><span>本页不发布正式投资动作；所有经过自主学习、验证与风险检查后的行动结论，只在「今日驾驶舱」统一发布。</span></div><button type="button" data-open-action-outlet>返回今日驾驶舱</button></div>';
}
function install(){
 for(const id of SECONDARY_TABS){
   const tab=document.getElementById(id); if(!tab||tab.querySelector('[data-single-action-banner]')) continue;
   tab.insertAdjacentHTML('afterbegin',bannerHtml());
 }
 document.querySelectorAll('[data-open-action-outlet]').forEach(b=>b.addEventListener('click',()=>global.openDashboardTab?.(AUTHORITY_TAB)));
}
function audit(){
 const violations=[];
 for(const id of SECONDARY_TABS){
   const tab=document.getElementById(id); if(!tab) continue;
   const text=(tab.innerText||'').toUpperCase();
   const hits=ACTION_WORDS.filter(w=>text.includes(w));
   if(hits.length) violations.push({tab:id,formal_action_words:hits});
 }
 return {authority_tab:AUTHORITY_TAB,secondary_tabs:SECONDARY_TABS.slice(),violations};
}
global.MAVSingleActionOutlet={AUTHORITY_TAB,ACTION_WORDS,SECONDARY_TABS,install,audit};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install);else install();
})(window);
