'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');const {once}=require('node:events');
const {createServer}=require('../server');const {Game}=require('../game');const {WebSocket}=require('../vendor/ws');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function join(url,name,skin=0){
  const ws=new WebSocket(url),messages=[];ws.on('message',raw=>messages.push(JSON.parse(raw)));
  await once(ws,'open');ws.send(JSON.stringify({type:'join',name,skin}));
  for(let i=0;i<100;i++){const m=messages.find(m=>m.type==='welcome'||m.type==='error');if(m)return {ws,m,messages};await sleep(10);}throw Error('join timeout');
}
test('10 gerçek WebSocket istemcisi: ortak harita, hareket, sıralama, kapasite, ayrılma',async t=>{
  const app=createServer();await new Promise(r=>app.server.listen(0,'127.0.0.1',r));t.after(()=>app.stop());
  const base=`http://127.0.0.1:${app.server.address().port}`,url=base.replace('http','ws')+'/ws';
  const clients=await Promise.all(Array.from({length:10},(_,i)=>join(url,i===0?'umutsiker':'oyuncu'+i,i%6)));
  for(const c of clients)assert.equal(c.m.type,'welcome');
  await sleep(180);assert.equal(app.game.players.size,10);
  for(const c of clients){const states=c.messages.filter(m=>m.type==='state'),state=states.at(-1);assert.equal(state.count,10);assert.equal(state.players.length,10);assert.equal(state.leaderboard[0].name,'umutsiker');assert.equal(states[0].food.length,550);assert.ok(Array.isArray(state.foodChanges));assert.equal(state.food,undefined);}
  const extra=await join(url,'onbir');assert.equal(extra.m.type,'error');extra.ws.close();
  const p=app.game.players.get(clients[1].m.id);p.x=p.y=800;const before=p.x;
  app.game.food[0]={id:0,x:820,y:800,color:0};
  clients[1].ws.send('{broken');clients[1].ws.send(JSON.stringify({type:'input',x:1,y:0,mass:99999999}));
  await sleep(250);assert.ok(p.x>before);assert.ok(p.mass<500);assert.equal(p.alive,true);
  assert.ok(p.mass>=72);assert.ok(clients[1].messages.some(m=>m.foodChanges?.some(f=>f.id===0)));
  assert.ok(JSON.stringify(clients[1].messages.filter(m=>m.type==='state').at(-1)).length<10000,'Boşta her pakette tüm kırıntı haritası tekrar gönderilmemeli');
  clients[9].ws.close();await once(clients[9].ws,'close');await sleep(60);assert.equal(app.game.players.size,9);
  const replacement=await join(url,'yeni');assert.equal(replacement.m.type,'welcome');replacement.ws.close();
  assert.equal((await fetch(base+'/health')).status,200);assert.match(await (await fetch(base)).text(),/THE ERİNÇ/);
  assert.equal((await fetch(base+'/server.js')).status,404);assert.equal((await fetch(base+'/assets/skins/skin-6.jpeg')).status,200);
  const bad=new WebSocket(url,{origin:'https://evil.invalid'});bad.on('error',()=>{});await new Promise(r=>bad.on('close',r));assert.equal(app.game.players.size<=10,true);
});
test('Poğaça olayı iki ayrı gerçek istemciye aynı şekilde yayınlanır',async t=>{
  const game=new Game({eventInterval:250,eventDuration:2000});game.food=[];
  const app=createServer({game});await new Promise(r=>app.server.listen(0,'127.0.0.1',r));t.after(()=>app.stop());
  const url=`ws://127.0.0.1:${app.server.address().port}/ws`;
  const a=await join(url,'a'),b=await join(url,'b');
  for(const p of game.players.values()){p.x=500;p.y=500;}
  await sleep(350);
  for(const c of [a,b]){const s=c.messages.filter(m=>m.type==='state').at(-1);assert.ok(s.pastry);assert.ok(s.notices.some(n=>/SON ZEYTİNLİ/.test(n.text)));}
});
