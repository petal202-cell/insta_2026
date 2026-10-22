// Wake the existing single-writer processor; never trust webhook text as approval.
export default {
 async fetch(request, env) {
  const path=new URL(request.url).pathname;
  if(request.method==='GET' && path==='/health') return Response.json({service:'kids-weekend-webhook',configured:!!(env.RELAY_SECRET&&env.GITHUB_TOKEN),mode:'workflow-dispatch'});
  if(request.method!=='POST'||path!=='/webhook') return new Response('Not found',{status:404});
  if(!env.RELAY_SECRET||!env.GITHUB_TOKEN) return new Response('Not configured',{status:503});
  const enc=new TextEncoder();
  const hash=async s=>new Uint8Array(await crypto.subtle.digest('SHA-256',enc.encode(s)));
  const a=await hash(request.headers.get('X-Relay-Secret')||''),b=await hash(env.RELAY_SECRET);
  let diff=0;for(let i=0;i<a.length;i++)diff|=a[i]^b[i];
  if(diff)return new Response('Unauthorized',{status:401});
  if(Number(request.headers.get('content-length')||0)>65536)return new Response('Too large',{status:413});
  const raw=await request.text();if(raw.length>65536)return new Response('Too large',{status:413});
  let event;try{event=JSON.parse(raw);}catch{return new Response('Invalid JSON',{status:400});}
  if(event.test===true||event.event==='webhook.test')return Response.json({test:true});
  if(event.event!=='message.received')return Response.json({ignored:true});
  // Zernio subscription MUST be restricted to the configured Telegram account.
  // Retries may enqueue extra runs; Python serializes runs and verifies fresh owner commands.
  const r=await fetch('https://api.github.com/repos/petal202-cell/insta_2026/actions/workflows/free-bot.yml/dispatches',{
   method:'POST',headers:{Authorization:'Bearer '+env.GITHUB_TOKEN,'User-Agent':'kids-weekend-webhook',Accept:'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','Content-Type':'application/json'},
   body:JSON.stringify({ref:'main',inputs:{mode:'poll'}})
  });
  return r.status===204?Response.json({accepted:true},{status:202}):new Response('Dispatch failed',{status:502});
 }
};
