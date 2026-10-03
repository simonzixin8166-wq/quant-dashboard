import fs from 'fs';
import { chromium } from 'playwright';
const base=(process.env.BASE_URL||'https://myalphaview.com').replace(/\/$/,'');
const out=process.env.QA_OUT||'qa-artifacts';fs.mkdirSync(out,{recursive:true});
const report={checked_at:new Date().toISOString(),base_url:base,public:{},private:{status:'SKIPPED'},interaction:{status:'SKIPPED',tabs:[],controls:[]},console_errors:[]};
const browser=await chromium.launch({headless:true});
async function publicRun(viewport,name){const page=await browser.newPage({viewportSize:viewport});page.on('console',m=>{if(m.type()==='error')report.console_errors.push(String(m.text()).slice(0,300))});page.on('pageerror',e=>report.console_errors.push(String(e.message).slice(0,300)));await page.goto(base+'/?qa='+Date.now(),{waitUntil:'networkidle',timeout:90000});await page.waitForTimeout(3500);const v=await page.locator('meta[name="application-version"]').getAttribute('content');const bodyv=await page.locator('body').getAttribute('data-app-version');const assistant=await page.locator('#marketOptionAlert').count();const journal=await page.locator('#decisionJournalRoot').count();const agentRoot=await page.locator('#agentAttentionRoot').count();let history=false,agent=false;try{const h=await page.request.get(base+'/research/historical_journal.json?qa='+Date.now());history=h.ok()&&Boolean((await h.json())?.summary?.events)}catch{}try{const a=await page.request.get(base+'/research/autonomous_agent.json?qa='+Date.now());agent=a.ok()&&String((await a.json())?.version||'').startsWith('5.5.')}catch{}const txt=(await page.locator('body').innerText()).slice(0,250000);report.public[name]={version:v,body_version:bodyv,assistant:Boolean(assistant),journal:Boolean(journal),historical_learning:history,autonomous_agent:Boolean(agentRoot)&&agent,negative_zero:/(^|[^\d])-0(?:\.0+)?(?=\s|%|$|｜|·)/m.test(txt)};await page.screenshot({path:`${out}/${name}-home.png`,fullPage:true});if(name==='desktop'){await page.evaluate(()=>window.openDashboardTab?.('tab-journal'));await page.waitForTimeout(800);await page.screenshot({path:`${out}/desktop-journal.png`,fullPage:true});await page.evaluate(()=>window.openDashboardTab?.('tab-system-health'));await page.waitForTimeout(1200);await page.screenshot({path:`${out}/desktop-system-health.png`,fullPage:true});}await page.close();}
await publicRun({width:1440,height:1000},'desktop');await publicRun({width:390,height:844},'mobile');
const service=process.env.SUPABASE_SERVICE_ROLE_KEY,email=process.env.QA_EMAIL,supa=process.env.SUPABASE_URL;
if(service&&email&&supa){try{const resp=await fetch(supa.replace(/\/$/,'')+'/auth/v1/admin/generate_link',{method:'POST',headers:{apikey:service,Authorization:`Bearer ${service}`,'Content-Type':'application/json'},body:JSON.stringify({type:'magiclink',email,options:{redirectTo:base+'/'}})});const b=await resp.json();const link=b?.properties?.action_link||b?.action_link;if(!resp.ok||!link)throw new Error(b?.msg||b?.message||`generate_link ${resp.status}`);const page=await browser.newPage({viewportSize:{width:1440,height:1000}});await page.goto(link,{waitUntil:'networkidle',timeout:90000});await page.waitForTimeout(4500);const pm=await page.locator('body').evaluate(el=>el.classList.contains('private-mode'));const session=await page.evaluate(async()=>Boolean((await window.mavSupabase?.auth?.getSession())?.data?.session));report.private={status:pm&&session?'PASS':'FAIL',private_mode:pm,session};
if(pm&&session){
  const tabIds=await page.locator('.nav-menu li[data-auth-required]').evaluateAll(nodes=>nodes.map(n=>{const m=(n.getAttribute('onclick')||'').match(/switchTab\('([^']+)'/);return m?m[1]:null}).filter(Boolean));
  const tabChecks=[];
  for(const id of tabIds){
    const exists=await page.locator('#'+id).count();
    if(exists){await page.evaluate(id=>window.openDashboardTab?.(id),id);await page.waitForTimeout(180);const active=await page.locator('#'+id).evaluate(el=>el.classList.contains('active'));const bodyOverflow=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);tabChecks.push({id,exists:true,active,body_overflow_px:bodyOverflow});}
    else tabChecks.push({id,exists:false,active:false,body_overflow_px:null});
  }
  const safeControls=[
    ['themeToggle',async()=>{await page.locator('#themeToggle').click();await page.waitForTimeout(120);return true}],
    ['mobileNavClose',async()=>Boolean(await page.locator('#mobileNavClose').count())],
    ['authBtn',async()=>Boolean(await page.locator('#authBtn').count())],
  ];
  const controlChecks=[];
  for(const [id,fn] of safeControls){try{controlChecks.push({id,ok:Boolean(await fn())})}catch(e){controlChecks.push({id,ok:false,error:String(e.message).slice(0,120)})}}
  const moduleEnglishLeak=await page.locator('#systemHealthRoot').evaluate(el=>/(research_planner|learning_engine|self_improvement|system_status|decision_journal|failure_attribution)/.test(el.innerText||'')).catch(()=>false);
  const stockNames=await page.locator('#stocksTableBody .stock-name').allInnerTexts().catch(()=>[]);
  const canonicalChecks={AVGO:'博通',ORCL:'甲骨文',TSM:'台积电',MRVL:'迈威尔科技',AMD:'美国超微公司'};
  const badCanonical=[];
  for(const [symbol,name] of Object.entries(canonicalChecks)){const row=page.locator(`#stocksTableBody tr[data-symbol="${symbol}"] .stock-name`);if(await row.count()){const txt=(await row.first().innerText()).trim();if(txt!==name)badCanonical.push({symbol,expected:name,actual:txt})}}
  report.interaction={status:tabChecks.every(x=>x.exists&&x.active&&Math.abs(x.body_overflow_px||0)<=4)&&controlChecks.every(x=>x.ok)&&!moduleEnglishLeak&&!badCanonical.length?'PASS':'FAIL',tabs:tabChecks,controls:controlChecks,module_english_leak:moduleEnglishLeak,bad_canonical_names:badCanonical,stock_name_sample:stockNames.slice(0,12)};
}
await page.close();}catch(e){report.private={status:'WARNING',error:String(e.message).slice(0,250)}}}
await browser.close();
report.overall=(Object.values(report.public).every(x=>Boolean(x.version)&&x.version===x.body_version&&x.assistant&&x.journal&&x.historical_learning&&x.autonomous_agent&&!x.negative_zero)&&report.private.status!=='FAIL'&&report.interaction.status!=='FAIL')?'PASS':'FAIL';fs.writeFileSync(`${out}/report.json`,JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));if(report.overall!=='PASS')process.exit(1);
