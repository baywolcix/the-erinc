'use strict';
const {test}=require('node:test');const assert=require('node:assert/strict');
const {Game,radius,WORLD}=require('../game');
test('Özel isimler büyük/küçük harfe duyarlı; altı skin ve 10 oyuncu',()=>{
  const g=new Game({now:0});
  for(const [name,rainbow,mass] of [['kaptan',true,70],['samet',true,70],['Kaptan',false,70],['Samet',false,70],['umutsiker',false,2500],['Umutsiker',false,70]]){
    const p=g.join(name,5,0);assert.equal(p.rainbow,rainbow);assert.equal(p.mass,mass);assert.equal(p.skin,5);
  }
  assert.throws(()=>g.join('samet',0,0));assert.throws(()=>g.join('  ',0,0));
  for(let i=6;i<10;i++)g.join('p'+i,i%6,0);
  assert.throws(()=>g.join('eleven',0,0),/10 kişi/);
});
test('Sunucu yönü sınırlar, koordinat/kütle hilesini yok sayar; büyükler yavaşlar',()=>{
  const g=new Game({now:0});g.food=[];
  const a=g.join('normal',0,0),b=g.join('umutsiker',1,0);a.x=b.x=1000;a.y=500;b.y=1500;
  g.input(a,{x:1e99,y:0,mass:999999});g.input(b,{x:1,y:0});g.step(.1,100);
  assert.ok(a.x-1000>b.x-1000);assert.ok(a.x-1000<=24.5);assert.equal(a.mass,70);
  const old=a.dx;g.input(a,{x:NaN,y:0});assert.equal(a.dx,old);
  a.x=WORLD;g.step(.1,200);assert.ok(a.x<=WORLD-radius(a.mass));
});
test('Kırıntı büyütür, doğum kalkanı yutmayı engeller, büyük rakip yutar ve yeniden doğulur',()=>{
  const g=new Game({now:0});const a=g.join('büyük',0,0),b=g.join('küçük',1,0);
  a.x=b.x=1000;a.y=b.y=1000;a.mass=500;g.food=[{id:0,x:1000,y:1000,color:0}];
  g.step(0,1000);assert.equal(a.mass,502);assert.equal(b.alive,true);
  g.food=[];g.step(0,5000);assert.equal(b.alive,false);assert.equal(a.mass,558);assert.equal(b.killer,'büyük');
  assert.equal(g.respawn(b,5500),false);assert.equal(g.respawn(b,6600),true);assert.equal(b.mass,70);assert.ok(b.shieldUntil>6600);
});
test('Benzer kütledeki oyuncular birbirini yutamaz',()=>{
  const g=new Game({now:0});g.food=[];const a=g.join('a',0,0),b=g.join('b',0,0);a.x=b.x=900;a.y=b.y=900;a.mass=80;g.step(0,5000);assert.ok(a.alive&&b.alive);
});
test('Gerçek 300000ms etkinlik takvimi, tek kazanan, 600 kütle ve sonraki etkinlik',()=>{
  const g=new Game({now:0});g.food=[];const a=g.join('a',0,0),b=g.join('b',1,0);a.x=b.x=1600;a.y=b.y=1600;
  g.step(0,299999);assert.equal(g.pastry,null);g.step(0,300000);assert.equal(g.pastry,null);
  assert.equal(a.wins+b.wins,1);assert.equal(a.mass+b.mass,740);assert.equal(g.nextEvent,600000);
  a.x=b.x=400;a.y=b.y=400;g.step(0,600000);assert.ok(g.pastry);g.step(0,660000);assert.equal(g.pastry,null);
});
test('Etkinliği yeni doğmuş kalkanlı oyuncu kazanamaz; durum herkes için aynı',()=>{
  const g=new Game({now:0});g.food=[];const p=g.join('p',0,299000);p.x=p.y=1600;g.step(0,300000);assert.ok(g.pastry);assert.equal(p.wins,0);
  const snapshot=g.snapshot(300000);assert.equal(snapshot.players[0].id,p.id);assert.equal(snapshot.nextEvent,600000);assert.equal(snapshot.leaderboard[0].name,'p');assert.equal(snapshot.players[0].dx,undefined);
});
