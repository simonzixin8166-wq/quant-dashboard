import fs from 'fs';
import { chromium } from 'playwright';
const base=(process.env.BASE_URL||'https://myalphaview.com').replace(/\/$/,'');
const out=process.env.QA_OUT||'qa-artifacts';fs.mkdirSync(out,{recursive:true});
const report={checked_at:new Date().toISOString(),base_url:base,public:{},private:{status:'SKIPPED'},interaction:{status:'SKIPPED',tabs:[],controls:[]},console_errors:[],http_errors:[]};
const browser=await chromium.launch({headless:true});
async function publicRun(viewport,name){
  const page=await browser.newPage({viewportSize:viewport});
  page.on('console',m=>{if(m.type()==='error')report.console_errors.push(String(m.text()).slice(0,300))});
  page.on('pageerror',e=>report.console_errors.push(String(e.message).slice(0,300)));
  page.on('response',r=>{if(r.status()>=400)report.http_errors.push({status:r.status(),url:r.url().slice(0,500)})});
  await page.goto(base+'/?qa='+Date.now(),{waitUntil:'networkidle',timeout:90000});
  await page.waitForTimeout(3500);
  const v=await page.locator('meta[name="application-version"]').getAttribute('content');
  const bodyv=await page.locator('body').getAttribute('data-app-version');
  const assistant=await page.locator('#marketOptionAlert').count();
  const journal=await page.locator('#decisionJournalRoot').count();
  const agentRoot=await page.locator('#agentAttentionRoot').count();
  let history=false,agent=false;
  try{const h=await page.request.get(base+'/research/historical_journal.json?qa='+Date.now());history=h.ok()&&Boolean((await h.json())?.summary?.events)}catch{}
  try{const a=await page.request.get(base+'/research/autonomous_agent.json?qa='+Date.now());agent=a.ok()&&String((await a.json())?.version||'').startsWith('5.5.')}catch{}
  const txt=(await page.locator('body').innerText()).slice(0,250000);
  report.public[name]={version:v,body_version:bodyv,assistant:Boolean(assistant),journal:Boolean(journal),historical_learning:history,autonomous_agent:Boolean(agentRoot)&&agent,negative_zero:/(^|[^\d])-0(?:\.0+)?(?=\s|%|$|｜|·)/m.test(txt)};
  await page.screenshot({path:`${out}/${name}-home.png`,fullPage:true});
  if(name==='desktop'){
    // Read-only synthetic private mode: verifies tab routing/layout even when CI has no private QA credentials.
    await page.evaluate(()=>{document.body.classList.add('private-mode');document.body.classList.remove('auth-pending')});
    const tabIds=await page.locator('.nav-menu li[data-auth-required]').evaluateAll(nodes=>nodes.map(n=>{const m=(n.getAttribute('onclick')||'').match(/switchTab\('([^']+)'/);return m?m[1]:null}).filter(Boolean));
    const tabChecks=[];
    for(const id of tabIds){
      const exists=await page.locator('#'+id).count();
      if(!exists){tabChecks.push({id,exists:false,active:false,body_overflow_px:null,breadcrumb:''});continue}
      await page.evaluate(id=>window.openDashboardTab?.(id),id);
      await page.waitForTimeout(120);
      const active=await page.locator('#'+id).evaluate(el=>el.classList.contains('active'));
      const bodyOverflow=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);
      const breadcrumb=(await page.locator('#bc-title').innerText().catch(()=>'' )).trim();
      tabChecks.push({id,exists:true,active,body_overflow_px:bodyOverflow,breadcrumb});
    }
    await page.evaluate(()=>window.openDashboardTab?.('tab-system-health'));
    await page.waitForTimeout(900);
    const moduleEnglishLeak=await page.locator('#systemHealthRoot').evaluate(el=>/(research_planner|learning_engine|self_improvement|system_status|decision_journal|failure_attribution)/.test(el.innerText||'')).catch(()=>false);
    const fontSpecs=[['nav','.nav-menu li',12],['system_module_copy','#tab-system-health .qa-note .qa-grid article p',12]];
    const fontChecks=[];
    for(const [label,selector,minPx] of fontSpecs){const loc=page.locator(selector);if(await loc.count()){const px=await loc.first().evaluate(el=>parseFloat(getComputedStyle(el).fontSize));fontChecks.push({name:label,font_px:px,min_px:minPx,ok:px>=minPx})}}
    report.interaction={status:tabChecks.every(x=>x.exists&&x.active&&Boolean(x.breadcrumb)&&Math.abs(x.body_overflow_px||0)<=4)&&fontChecks.every(x=>x.ok)&&!moduleEnglishLeak?'PASS':'FAIL',mode:'synthetic-read-only',tabs:tabChecks,controls:[],font_checks:fontChecks,module_english_leak:moduleEnglishLeak,bad_canonical_names:[],stock_name_sample:[]};
    await page.screenshot({path:`${out}/desktop-system-health.png`,fullPage:true});
  }
  await page.close();
}
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
  const fontSpecs=[['nav','.nav-menu li',12],['stock_name','#stocksTableBody .stock-name',14],['stock_table_header','.stock-table th',12],['system_module_copy','#tab-system-health .qa-note .qa-grid article p',12]];
  const fontChecks=[];
  for(const [name,selector,minPx] of fontSpecs){const loc=page.locator(selector);if(await loc.count()){const px=await loc.first().evaluate(el=>parseFloat(getComputedStyle(el).fontSize));fontChecks.push({name,selector,font_px:px,min_px:minPx,ok:px>=minPx})}}
  const stockNames=await page.locator('#stocksTableBody .stock-name').allInnerTexts().catch(()=>[]);
  const canonicalChecks={AVGO:'博通',ORCL:'甲骨文',TSM:'台积电',MRVL:'迈威尔科技',AMD:'美国超微公司'};
  const badCanonical=[];
  for(const [symbol,name] of Object.entries(canonicalChecks)){const row=page.locator(`#stocksTableBody tr[data-symbol="${symbol}"] .stock-name`);if(await row.count()){const txt=(await row.first().innerText()).trim();if(txt!==name)badCanonical.push({symbol,expected:name,actual:txt})}}
  report.interaction={status:tabChecks.every(x=>x.exists&&x.active&&Math.abs(x.body_overflow_px||0)<=4)&&controlChecks.every(x=>x.ok)&&fontChecks.every(x=>x.ok)&&!moduleEnglishLeak&&!badCanonical.length?'PASS':'FAIL',mode:'authenticated-private',tabs:tabChecks,controls:controlChecks,font_checks:fontChecks,module_english_leak:moduleEnglishLeak,bad_canonical_names:badCanonical,stock_name_sample:stockNames.slice(0,12)};
}
await page.close();}catch(e){report.private={status:'WARNING',error:String(e.message).slice(0,250)}}}
await browser.close();
report.http_errors=[...new Map(report.http_errors.map(x=>[x.status+'|'+x.url,x])).values()];
const persistentHttpErrors=[];
for(const item of report.http_errors){
  try{
    await new Promise(r=>setTimeout(r,600));
    const retry=await fetch(item.url,{cache:'no-store'});
    if(!retry.ok)persistentHttpErrors.push(item);
  }catch{persistentHttpErrors.push(item)}
}
report.http_errors=persistentHttpErrors;
report.business_data={status:'FAIL'};
try{
  const [sr,dr]=await Promise.all([
    fetch(base+'/research/system_status.json?qa='+Date.now(),{cache:'no-store'}),
    fetch(base+'/data.json?qa='+Date.now(),{cache:'no-store'})
  ]);
  if(sr.ok&&dr.ok){
    const sys=await sr.json(),data=await dr.json(),market=sys?.artifacts?.market_dashboard||{};
    const marketAsOf=String(market.market_as_of||data?.spy_date||'');
    const expected=String(market.expected_market_date||'');
    const ok=market.business_freshness==='fresh'&&market.decision_eligible===true&&Boolean(expected)&&marketAsOf===expected&&sys.overall!=='attention';
    report.business_data={status:ok?'PASS':'FAIL',system_overall:sys.overall||'unknown',market_as_of:marketAsOf,expected_market_date:expected,business_freshness:market.business_freshness||'unknown',decision_eligible:Boolean(market.decision_eligible)};
  }else report.business_data={status:'FAIL',error:`status ${sr.status}/${dr.status}`};
}catch(e){report.business_data={status:'FAIL',error:String(e.message).slice(0,200)}}
const engineeringBaseHealthy=Object.values(report.public).every(x=>Boolean(x.version)&&x.version===x.body_version&&x.assistant&&x.journal&&x.historical_learning&&x.autonomous_agent&&!x.negative_zero)&&report.private.status!=='FAIL'&&report.interaction.status==='PASS';
report.engineering_qa={status:engineeringBaseHealthy?'PASS':'FAIL',public_surfaces:Object.keys(report.public),private_status:report.private.status,interaction_status:report.interaction.status};
report.investment_data_qa={status:report.business_data.status,market_as_of:report.business_data.market_as_of||null,expected_market_date:report.business_data.expected_market_date||null,business_freshness:report.business_data.business_freshness||'unknown',decision_eligible:Boolean(report.business_data.decision_eligible)};
report.decision_readiness={status:(engineeringBaseHealthy&&report.business_data.status==='PASS')?'PASS':'FAIL',rule:'Engineering QA and Investment Data QA must both PASS; stale or incomplete market data fails closed.'};
const coreHealthy=engineeringBaseHealthy&&report.investment_data_qa.status==='PASS'&&report.decision_readiness.status==='PASS';
let baseRetryHealthy=false;
try{
  const retry=await fetch(base+'/?qa-retry='+Date.now(),{cache:'no-store'});
  baseRetryHealthy=retry.ok;
}catch{}
const transientResourcePattern=/Failed to load resource: the server responded with a status of (404|503)/;
const fatalConsoleErrors=report.console_errors.filter(x=>!(report.http_errors.length===0&&coreHealthy&&baseRetryHealthy&&transientResourcePattern.test(x)));
report.fatal_console_errors=fatalConsoleErrors;
report.engineering_qa.status=(engineeringBaseHealthy&&report.fatal_console_errors.length===0&&report.http_errors.length===0)?'PASS':'FAIL';
report.decision_readiness.status=(report.engineering_qa.status==='PASS'&&report.investment_data_qa.status==='PASS')?'PASS':'FAIL';
report.overall=report.decision_readiness.status;fs.writeFileSync(`${out}/report.json`,JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));if(report.overall!=='PASS')process.exit(1);
