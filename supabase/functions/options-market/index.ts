const corsHeaders={
  'Access-Control-Allow-Origin':'*',
  'Access-Control-Allow-Headers':'authorization, apikey, content-type',
  'Access-Control-Allow-Methods':'GET, OPTIONS',
  'Cache-Control':'private, max-age=15'
};
const memoryCache=new Map<string,{at:number,data:string,status:number}>();
const clean=(v:string|null,re:RegExp)=>v&&re.test(v)?v:null;
Deno.serve(async(req:Request)=>{
  if(req.method==='OPTIONS')return new Response('ok',{headers:corsHeaders});
  if(req.method!=='GET')return new Response(JSON.stringify({error:'Method not allowed'}),{status:405,headers:{...corsHeaders,'Content-Type':'application/json'}});
  const apiKey=Deno.env.get('MARKETDATA_API_TOKEN');
  if(!apiKey)return new Response(JSON.stringify({error:'服务器尚未配置 MARKETDATA_API_TOKEN'}),{status:503,headers:{...corsHeaders,'Content-Type':'application/json'}});
  const u=new URL(req.url),action=u.searchParams.get('action')||'',symbol=clean(u.searchParams.get('symbol'),/^[A-Z.\-]{1,12}$/),expiration=clean(u.searchParams.get('expiration'),/^\d{4}-\d{2}-\d{2}$/),side=clean(u.searchParams.get('side'),/^(call|put)$/),optionSymbol=clean(u.searchParams.get('optionSymbol'),/^[A-Z.\-]{1,12}\d{6}[CP]\d{8}$/);
  let upstream='';
  if(action==='expirations'&&symbol)upstream=`https://api.marketdata.app/v1/options/expirations/${encodeURIComponent(symbol)}/`;
  else if(action==='chain'&&symbol&&expiration&&side)upstream=`https://api.marketdata.app/v1/options/chain/${encodeURIComponent(symbol)}/?expiration=${expiration}&side=${side}`;
  else if(action==='quote'&&optionSymbol)upstream=`https://api.marketdata.app/v1/options/quotes/${encodeURIComponent(optionSymbol)}/`;
  else return new Response(JSON.stringify({error:'无效或缺失的查询参数'}),{status:400,headers:{...corsHeaders,'Content-Type':'application/json'}});
  const hit=memoryCache.get(upstream);if(hit&&Date.now()-hit.at<15000)return new Response(hit.data,{status:hit.status,headers:{...corsHeaders,'Content-Type':'application/json','X-Cache':'HIT'}});
  try{
    const r=await fetch(upstream,{headers:{Authorization:`Bearer ${apiKey}`,Accept:'application/json'}}),body=await r.text();memoryCache.set(upstream,{at:Date.now(),data:body,status:r.status});
    return new Response(body,{status:r.status,headers:{...corsHeaders,'Content-Type':'application/json','X-Cache':'MISS'}});
  }catch(e){return new Response(JSON.stringify({error:`行情上游连接失败：${e instanceof Error?e.message:String(e)}`}),{status:502,headers:{...corsHeaders,'Content-Type':'application/json'}})}
});
