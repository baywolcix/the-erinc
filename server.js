'use strict';
const http=require('http'),fs=require('fs'),path=require('path');
const {WebSocketServer}=require('ws');
const PORT=process.env.PORT||3000, MAP=3400, MAX=14, CAP=50000;
const players=new Map(),foods=new Map(),pellets=new Map(),boosts=new Map();let seq=0,event=null,eventAt=Date.now()+75000,champion=null,nextBoost=Date.now()+15000;
const rand=(a,b)=>a+Math.random()*(b-a),clamp=(x,a,b)=>Math.max(a,Math.min(b,x)),radius=m=>Math.sqrt(m)*3.4,dist=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);
const send=(ws,o)=>{if(ws.readyState===1)ws.send(JSON.stringify(o))},broadcast=o=>{for(const p of players.values())send(p.ws,o)};
function food(){let id=++seq;foods.set(id,{id,x:rand(25,MAP-25),y:rand(25,MAP-25),color:Math.floor(rand(0,6))})}for(let i=0;i<420;i++)food();
function spawn(ws,name,skin){const id=++seq,p={id,name,skin,mass:name==='umutsiker'?1150:65,parts:[],dx:0,dy:0,shoot:0,boostUntil:0,ws,invuln:Date.now()+2200};p.parts=[{id:++seq,x:rand(250,MAP-250),y:rand(250,MAP-250),mass:p.mass,mergeAt:0,vx:0,vy:0}];players.set(id,p);return p}
function total(p){return p.parts.reduce((s,c)=>s+c.mass,0)}
function addMass(p,part,amount){let room=CAP-total(p);part.mass+=Math.max(0,Math.min(amount,room))}
const mime={'.html':'text/html; charset=utf-8','.js':'application/javascript','.css':'text/css','.jpeg':'image/jpeg','.png':'image/png'};
const root=path.resolve(__dirname,'public');
const server=http.createServer((req,res)=>{if(req.url==='/health'){res.writeHead(200,{'Content-Type':'application/json'});return res.end(JSON.stringify({ok:true,players:players.size}))}let url;try{url=decodeURIComponent(req.url.split('?')[0])}catch{res.writeHead(400);return res.end()}const file=path.resolve(root,'.'+(url==='/'?'/index.html':url));if(file!==root&&!file.startsWith(root+path.sep)){res.writeHead(403);return res.end()}fs.readFile(file,(err,data)=>{if(err){res.writeHead(404);return res.end('Not found')}res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream','Cache-Control':'public, max-age=120'});res.end(data)})});
const wss=new WebSocketServer({server});wss.on('connection',ws=>{let p=null;ws.on('message',raw=>{if(raw.length>1024)return;let m;try{m=JSON.parse(raw)}catch{return}if(m.type==='join'){if(p)return;if(players.size>=MAX)return send(ws,{type:'error',message:'Oda dolu!'});let name=typeof m.name==='string'?m.name.trim().slice(0,18):'Oyuncu';if(!name)name='Oyuncu';p=spawn(ws,name,Number.isInteger(m.skin)?clamp(m.skin,0,5):0);send(ws,{type:'welcome',id:p.id,map:MAP});broadcast({type:'notice',message:name+' savaşa katıldı!'})}if(!p)return;
if(m.type==='move'){p.dx=clamp(Number(m.x)||0,-1,1);p.dy=clamp(Number(m.y)||0,-1,1)}
if(m.type==='split'&&p.parts.length<16){const now=Date.now(),parts=[...p.parts];let mag=Math.hypot(p.dx,p.dy)||1,ux=p.dx/mag,uy=p.dy/mag;for(const c of parts){if(c.mass<80||p.parts.length>=16)continue;const half=c.mass/2;c.mass=half;c.mergeAt=now+12000;const r=radius(half),child={id:++seq,mass:half,x:clamp(c.x+ux*(r*2+12),r,MAP-r),y:clamp(c.y+uy*(r*2+12),r,MAP-r),mergeAt:now+12000,vx:ux*440,vy:uy*440};c.vx=-ux*50;c.vy=-uy*50;p.parts.push(child)}}
if(m.type==='eject'&&Date.now()>p.shoot){let c=p.parts.reduce((a,b)=>a.mass>b.mass?a:b);if(c.mass<55)return;p.shoot=Date.now()+180;c.mass-=12;let mag=Math.hypot(p.dx,p.dy)||1,ux=p.dx/mag,uy=p.dy/mag,id=++seq;pellets.set(id,{id,owner:p.id,x:clamp(c.x+ux*(radius(c.mass)+19),10,MAP-10),y:clamp(c.y+uy*(radius(c.mass)+19),10,MAP-10),vx:ux*600,vy:uy*600,mass:10,until:Date.now()+12000,ignoreUntil:Date.now()+850})}
});ws.on('close',()=>{if(p){players.delete(p.id);if(champion?.id===p.id)champion=null}})});
let last=Date.now();setInterval(()=>{const now=Date.now(),dt=Math.min((now-last)/1000,.08);last=now;
if(now>=eventAt&&!event){event={x:rand(130,MAP-130),y:rand(130,MAP-130)};eventAt=now+300000;broadcast({type:'notice',message:'🥐 BEYLERBEYİ’NDE SON ZEYTİNLİ POĞAÇA KALDI!'})}
if(now>=nextBoost){if(boosts.size<5){let id=++seq;boosts.set(id,{id,x:rand(90,MAP-90),y:rand(90,MAP-90),until:now+35000})}nextBoost=now+rand(13000,22000)}
for(const [id,b] of boosts)if(now>b.until)boosts.delete(id);
for(const p of players.values()){
let mag=Math.hypot(p.dx,p.dy),ux=mag>.05?p.dx/mag:0,uy=mag>.05?p.dy/mag:0;
for(const c of p.parts){let speed=220/(1+Math.sqrt(c.mass)/23)*(now<p.boostUntil?2:1);c.x=clamp(c.x+(ux*speed+c.vx)*dt,radius(c.mass),MAP-radius(c.mass));c.y=clamp(c.y+(uy*speed+c.vy)*dt,radius(c.mass),MAP-radius(c.mass));c.vx*=Math.exp(-dt*4);c.vy*=Math.exp(-dt*4);
for(const [id,f] of foods)if(Math.abs(c.x-f.x)<radius(c.mass)+8&&dist(c,f)<radius(c.mass)+5){foods.delete(id);addMass(p,c,2.2)}
for(const [id,b] of boosts)if(dist(c,b)<radius(c.mass)+19){boosts.delete(id);p.boostUntil=now+10000;send(p.ws,{type:'notice',message:'⚡ 10 SANİYE 2X HIZ!'})}
if(event&&dist(c,event)<radius(c.mass)+32){let gain=Math.min(total(p),CAP-total(p));addMass(p,c,gain);champion={id:p.id,until:now+30000};event=null;broadcast({type:'notice',message:'👑 SON POĞAÇAYI '+p.name+' YEDİ! PUANI 2X! (MAKS 50.000)'})}}
// Merge only after cooldown; center-of-mass positioning preserves total score.
for(let i=0;i<p.parts.length;i++)for(let j=i+1;j<p.parts.length;j++){let a=p.parts[i],b=p.parts[j];if(now<a.mergeAt||now<b.mergeAt)continue;if(dist(a,b)<radius(a.mass)+radius(b.mass)+22){let mass=a.mass+b.mass;a.x=(a.x*a.mass+b.x*b.mass)/mass;a.y=(a.y*a.mass+b.y*b.mass)/mass;a.mass=mass;p.parts.splice(j,1);j--}}
}
let ps=[...players.values()];const eaten=new Set();for(let i=0;i<ps.length;i++)for(let j=i+1;j<ps.length;j++){let a=ps[i],b=ps[j];if(eaten.has(a.id)||eaten.has(b.id)||now<a.invuln||now<b.invuln)continue;for(const ac of a.parts)for(const bc of b.parts){let big=ac.mass>bc.mass?a:b,large=big===a?ac:bc,small=big===a?b:a,tiny=big===a?bc:ac;if(eaten.has(small.id))continue;if(large.mass>tiny.mass*1.2&&dist(large,tiny)<radius(large.mass)-radius(tiny.mass)*.25){addMass(big,large,tiny.mass*.75);small.parts=small.parts.filter(c=>c!==tiny);if(!small.parts.length){eaten.add(small.id);send(small.ws,{type:'dead',by:big.name});players.delete(small.id);if(champion?.id===small.id)champion=null;broadcast({type:'notice',message:big.name+' → '+small.name+' oyuncusunu yuttu!'})}}}}
for(const [id,q] of pellets){q.x+=q.vx*dt;q.y+=q.vy*dt;q.vx*=Math.exp(-dt*2);q.vy*=Math.exp(-dt*2);if(now>q.until||q.x<0||q.y<0||q.x>MAP||q.y>MAP){pellets.delete(id);continue}let collected=false;for(const p of players.values()){if(p.id===q.owner&&now<q.ignoreUntil)continue;for(const c of p.parts){if(dist(c,q)<radius(c.mass)+9){addMass(p,c,q.mass);pellets.delete(id);collected=true;break}}if(collected)break}}
while(foods.size<420)food();if(champion&&now>=champion.until){let winner=players.get(champion.id);if(winner)broadcast({type:'notice',message:'🏆 '+winner.name+' BEYLERBEYİ’NİN SAHİBİ OLDU!'});champion=null}
const state={type:'state',players:[...players.values()].map(p=>({id:p.id,name:p.name,skin:p.skin,mass:Math.round(total(p)),parts:p.parts.map(c=>({id:c.id,x:Math.round(c.x),y:Math.round(c.y),mass:Math.round(c.mass)})),boosted:now<p.boostUntil})),foods:[...foods.values()],projectiles:[...pellets.values()].map(q=>({id:q.id,x:q.x,y:q.y})),boosts:[...boosts.values()].map(b=>({id:b.id,x:b.x,y:b.y})),event,champion:champion?{id:champion.id,remaining:Math.ceil((champion.until-now)/1000)}:null,next:Math.max(0,Math.ceil((eventAt-now)/1000))};broadcast(state)
},50);
server.listen(PORT,'0.0.0.0',()=>console.log('THE ERINC v1.1 online:',PORT));
