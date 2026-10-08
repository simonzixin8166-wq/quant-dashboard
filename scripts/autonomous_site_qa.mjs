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
  const soleOutletTitle=await page.locator('#tab-overview h1').first().innerText().catch(()=> '');
  const singleOutletLoaded=await page.evaluate(()=>Boolean(window.MAVSingleActionOutlet));
  report.public[name]={version:v,body_version:bodyv,assistant:Boolean(assistant),journal:Boolean(journal),historical_learning:history,autonomous_agent:Boolean(agentRoot)&&agent,negative_zero:/(^|[^\d])-0(?:\.0+)?(?=\s|%|$|｜|·)/m.test(txt),single_action_outlet:singleOutletLoaded&&/唯一行动出口/.test(soleOutletTitle)};
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
    const singleOutletBanners={};
    for(const id of ['tab-agent-center','tab-stocks','tab-options','tab-engine','tab-wenxuecity']) singleOutletBanners[id]=await page.locator('#'+id+' [data-single-action-banner="true"]').count()>0;
    const singleOutletPass=Object.values(singleOutletBanners).every(Boolean);
    await page.evaluate(()=>window.openDashboardTab?.('tab-overview'));await page.waitForTimeout(150);
    const summaryNavCount=await page.locator('#productIntelligenceRoot [data-pi-jump]').count();
    let summaryNavPass=summaryNavCount>=5;
    const optionJump=page.locator('#productIntelligenceRoot [data-pi-jump="tab:tab-options"]');
    if(await optionJump.count()){await optionJump.click();await page.waitForTimeout(120);summaryNavPass=summaryNavPass&&await page.locator('#tab-options').evaluate(el=>el.classList.contains('active'));}else summaryNavPass=false;
    await page.evaluate(()=>window.openDashboardTab?.('tab-overview'));
    report.interaction={status:tabChecks.every(x=>x.exists&&x.active&&Boolean(x.breadcrumb)&&Math.abs(x.body_overflow_px||0)<=4)&&fontChecks.every(x=>x.ok)&&!moduleEnglishLeak&&singleOutletPass&&summaryNavPass?'PASS':'FAIL',mode:'synthetic-read-only',tabs:tabChecks,controls:[],font_checks:fontChecks,module_english_leak:moduleEnglishLeak,bad_canonical_names:[],stock_name_sample:[],single_action_outlet_banners:singleOutletBanners,summary_navigation:{count:summaryNavCount,pass:summaryNavPass}};
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
  const singleOutletBanners={};
  for(const id of ['tab-agent-center','tab-stocks','tab-options','tab-engine','tab-wenxuecity']) singleOutletBanners[id]=await page.locator('#'+id+' [data-single-action-banner="true"]').count()>0;
  const singleOutletPass=Object.values(singleOutletBanners).every(Boolean);
  report.interaction={status:tabChecks.every(x=>x.exists&&x.active&&Math.abs(x.body_overflow_px||0)<=4)&&controlChecks.every(x=>x.ok)&&fontChecks.every(x=>x.ok)&&!moduleEnglishLeak&&!badCanonical.length&&singleOutletPass?'PASS':'FAIL',mode:'authenticated-private',tabs:tabChecks,controls:controlChecks,font_checks:fontChecks,module_english_leak:moduleEnglishLeak,bad_canonical_names:badCanonical,stock_name_sample:stockNames.slice(0,12),single_action_outlet_banners:singleOutletBanners};
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
  const [sr,dr,ar]=await Promise.all([
    fetch(base+'/research/system_status.json?qa='+Date.now(),{cache:'no-store'}),
    fetch(base+'/data.json?qa='+Date.now(),{cache:'no-store'}),
    fetch(base+'/research/server_action_status.json?qa='+Date.now(),{cache:'no-store'})
  ]);
  if(sr.ok&&dr.ok&&ar.ok){
    const sys=await sr.json(),data=await dr.json(),server=await ar.json(),market=sys?.artifacts?.market_dashboard||{};
    const marketAsOf=String(data?.spy_date||market.market_as_of||'');
    const expected=String(process.env.EXPECTED_MARKET_DATE||'');
    const sysGenerated=Date.parse(sys?.generated_at||'');
    const statusAgeHours=Number.isFinite(sysGenerated)?(Date.now()-sysGenerated)/36e5:Infinity;
    const ok=Boolean(expected)
      && marketAsOf===expected
      && String(market.market_as_of||'')===expected
      && market.business_freshness==='fresh'
      && market.decision_eligible===true
      && statusAgeHours>=0
      && statusAgeHours<=30
      && sys.overall!=='attention';
    report.business_data={
      status:ok?'PASS':'FAIL',
      system_overall:sys.overall||'unknown',
      market_as_of:marketAsOf,
      status_market_as_of:String(market.market_as_of||''),
      expected_market_date:expected,
      business_freshness:market.business_freshness||'unknown',
      decision_eligible:Boolean(market.decision_eligible),
      system_status_age_hours:Number.isFinite(statusAgeHours)?Number(statusAgeHours.toFixed(2)):null
    };
    const unknown=Number(server?.action_counts?.unknown||0);
    // The server snapshot must have judged the same completed session the site shows;
    // an older "clear" snapshot is stale evidence, not a current judgment.
    const serverMarketAsOf=String(server?.data_trust?.market_as_of||'');
    const serverCurrent=Boolean(expected)&&serverMarketAsOf===expected;
    const serverOk=['clear','action_required'].includes(String(server?.status||''))&&unknown===0&&server?.data_trust?.ok===true&&serverCurrent;
    report.server_action={status:serverOk?'PASS':'FAIL',server_status:server?.status||'unknown',judgment_basis:server?.judgment_basis||null,unknown_actions:unknown,data_trust_ok:server?.data_trust?.ok===true,server_market_as_of:serverMarketAsOf||null,server_snapshot_current:serverCurrent,last_checked_at:server?.last_checked_at||server?.generated_at||null};
  }else{
    report.business_data={status:'FAIL',error:`status ${sr.status}/${dr.status}/${ar.status}`};
    report.server_action={status:'FAIL',error:'server action status unavailable'};
  }
}catch(e){report.business_data={status:'FAIL',error:String(e.message).slice(0,200)}}
report.learning_guardrails={status:'FAIL'};
try{
  const nonce=Date.now();
  const [fr,er,cr,pr]=await Promise.all([
    fetch(base+'/research/candidate_forward_status.json?qa='+nonce,{cache:'no-store'}),
    fetch(base+'/research/candidate_eventscore_status.json?qa='+nonce,{cache:'no-store'}),
    fetch(base+'/research/candidate_family_scorecard_status.json?qa='+nonce,{cache:'no-store'}),
    fetch(base+'/research/candidate_evidence_promotion_status.json?qa='+nonce,{cache:'no-store'})
  ]);
  if(fr.ok&&er.ok&&cr.ok&&pr.ok){
    const forward=await fr.json(),eventscore=await er.json(),family=await cr.json(),promotion=await pr.json();
    const forwardOk=forward?.status==='running'
      &&forward?.historical_backfill_allowed===false
      &&forward?.production_effect==='none'
      &&forward?.promotion_effect==='none'
      &&String(forward?.ledger_mode||'').includes('next_open_baseline');
    const eventOk=eventscore?.production_effect==='none'
      &&eventscore?.promotion_effect==='none'
      &&eventscore?.promotion_gate_bridge?.state==='legacy_rule_promotion_bridge_frozen'
      &&eventscore?.promotion_gate_bridge?.candidate_evidence_promotion_path==='independent_ready'
      &&Number(eventscore?.counts?.promotion_gate_compatible||0)===0;
    const familyOk=family?.state==='shadow_statistics_ready'
      &&family?.production_effect==='none'
      &&family?.promotion_effect==='none'
      &&family?.promotion_bridge==='blocked_by_frozen_rule_family_semantics'
      &&Number(family?.counts?.promotion_gate_compatible||0)===0;
    const promotionOk=promotion?.state==='evidence_gate_ready'
      &&promotion?.production_effect==='none'
      &&promotion?.promotion_effect==='evidence_tier_only'
      &&Number(promotion?.counts?.passed||0)>=0
      &&Number(promotion?.counts?.decision_fusion_eligible||0)>=0;
    report.learning_guardrails={
      status:forwardOk&&eventOk&&familyOk&&promotionOk?'PASS':'FAIL',
      forward_status:forward?.status||'unknown',
      forward_historical_backfill_allowed:forward?.historical_backfill_allowed,
      forward_ledger_mode:forward?.ledger_mode||null,
      candidate_eventscore_bridge:eventscore?.promotion_gate_bridge?.state||'unknown',
      candidate_family_state:family?.state||'unknown',
      candidate_family_bridge:family?.promotion_bridge||'unknown',
      candidate_evidence_promotion_state:promotion?.state||'unknown',
      candidate_evidence_promotion_passed:Number(promotion?.counts?.passed||0),
      production_effects:[forward?.production_effect,eventscore?.production_effect,family?.production_effect,promotion?.production_effect],
      promotion_effects:[forward?.promotion_effect,eventscore?.promotion_effect,family?.promotion_effect,promotion?.promotion_effect]
    };
  }else{
    report.learning_guardrails={status:'FAIL',error:`candidate guardrail status unavailable ${fr.status}/${er.status}/${cr.status}/${pr.status}`};
  }
}catch(e){report.learning_guardrails={status:'FAIL',error:String(e.message).slice(0,200)}}

const engineeringBaseHealthy=Object.values(report.public).every(x=>Boolean(x.version)&&x.version===x.body_version&&x.assistant&&x.journal&&x.historical_learning&&x.autonomous_agent&&x.single_action_outlet&&!x.negative_zero)&&report.private.status!=='FAIL'&&report.interaction.status==='PASS';
report.engineering_qa={status:engineeringBaseHealthy?'PASS':'FAIL',public_surfaces:Object.keys(report.public),private_status:report.private.status,interaction_status:report.interaction.status};
const investmentDataPass=report.business_data.status==='PASS'&&report.server_action?.status==='PASS';
report.investment_data_qa={status:investmentDataPass?'PASS':'FAIL',market_as_of:report.business_data.market_as_of||null,expected_market_date:report.business_data.expected_market_date||null,business_freshness:report.business_data.business_freshness||'unknown',decision_eligible:Boolean(report.business_data.decision_eligible),server_action:report.server_action};
report.decision_readiness={status:(engineeringBaseHealthy&&investmentDataPass)?'PASS':'FAIL',rule:'Engineering QA and Investment Data QA must both PASS; market freshness and server action must fail closed when unknown.'};
const coreHealthy=engineeringBaseHealthy&&report.investment_data_qa.status==='PASS'&&report.learning_guardrails.status==='PASS'&&report.decision_readiness.status==='PASS';
let baseRetryHealthy=false;
try{
  const retry=await fetch(base+'/?qa-retry='+Date.now(),{cache:'no-store'});
  baseRetryHealthy=retry.ok;
}catch{}
const transientResourcePattern=/Failed to load resource: the server responded with a status of (404|503)/;
const fatalConsoleErrors=report.console_errors.filter(x=>!(report.http_errors.length===0&&coreHealthy&&baseRetryHealthy&&transientResourcePattern.test(x)));
report.fatal_console_errors=fatalConsoleErrors;
report.engineering_qa.status=(engineeringBaseHealthy&&report.fatal_console_errors.length===0&&report.http_errors.length===0)?'PASS':'FAIL';
report.decision_readiness.status=(report.engineering_qa.status==='PASS'&&report.investment_data_qa.status==='PASS'&&report.learning_guardrails.status==='PASS')?'PASS':'FAIL';
// Machine-readable verdict as GitHub check-run annotations (readable through the REST
// checks API even when log/artifact downloads are unavailable). Sanitized fields only.
function qaVerdictLines(r){
  const s=x=>String(x===undefined||x===null?'-':x);
  const b=r.business_data||{},sa=r.server_action||{};
  const fields=[
    ['overall',r.overall],['decision_readiness',(r.decision_readiness||{}).status],
    ['engineering_qa',(r.engineering_qa||{}).status],['interaction',(r.interaction||{}).status],
    ['business_data',b.status],['market_as_of',b.market_as_of],['expected_market_date',b.expected_market_date],
    ['business_freshness',b.business_freshness],['decision_eligible',b.decision_eligible],
    ['server_action',sa.status],['server_status',sa.server_status],['judgment_basis',sa.judgment_basis],
    ['server_market_as_of',sa.server_market_as_of],['server_snapshot_current',sa.server_snapshot_current],
    ['investment_data_qa',(r.investment_data_qa||{}).status],['learning_guardrails',(r.learning_guardrails||{}).status],
    ['fatal_console_errors',(r.fatal_console_errors||[]).length],['http_errors',(r.http_errors||[]).length],
  ];
  return fields.map(([k,v])=>`${k}=${s(v)}`);
}
function emitQaAnnotations(r){
  const esc=x=>String(x).replace(/%/g,'%25').replace(/\r/g,'%0D').replace(/\n/g,'%0A');
  const line=qaVerdictLines(r).join(' ');
  console.log(`::notice title=MyAlpha QA verdict::${esc('QA_VERDICT '+line)}`);
  if(r.overall!=='PASS'){
    const failing=['engineering_qa','interaction','business_data','server_action','investment_data_qa','learning_guardrails','decision_readiness']
      .filter(k=>((r[k]||{}).status)&&(r[k]||{}).status!=='PASS');
    console.log(`::error title=MyAlpha QA failing sections::${esc('QA_FAILING '+(failing.join(',')||'unknown'))}`);
  }
}
report.overall=report.decision_readiness.status;fs.writeFileSync(`${out}/report.json`,JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));emitQaAnnotations(report);if(report.overall!=='PASS')process.exit(1);
