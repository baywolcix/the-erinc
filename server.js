'use strict';
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { WebSocketServer, WebSocket } = require('./vendor/ws');
const { Game } = require('./game');
function createServer({ game = new Game(), allowedOrigins = process.env.ALLOWED_ORIGINS || '' } = {}) {
  const root = path.join(__dirname, 'public');
  const mime = { '.html':'text/html; charset=utf-8', '.js':'text/javascript; charset=utf-8', '.css':'text/css; charset=utf-8', '.jpeg':'image/jpeg', '.svg':'image/svg+xml' };
  const server = http.createServer((req, res) => {
    const headers = { 'X-Content-Type-Options':'nosniff', 'Referrer-Policy':'same-origin', 'Cache-Control':'no-cache' };
    if (req.method !== 'GET' && req.method !== 'HEAD') { res.writeHead(405, headers); return res.end(); }
    let pathname;
    try { pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname); } catch { res.writeHead(400,headers); return res.end(); }
    if (pathname === '/health') { res.writeHead(200, {...headers, 'Content-Type':'application/json'}); return res.end(JSON.stringify({ok:true, players:game.players.size, capacity:10})); }
    if (pathname === '/') pathname = '/index.html';
    const file = path.resolve(root, '.' + pathname);
    if (!file.startsWith(root + path.sep)) { res.writeHead(403,headers); return res.end(); }
    fs.readFile(file, (err, data) => { res.writeHead(err ? 404 : 200, {...headers, 'Content-Type':mime[path.extname(file)] || 'application/octet-stream'}); res.end(req.method === 'HEAD' || err ? undefined : data); });
  });
  const wss = new WebSocketServer({ noServer: true, maxPayload: 1024, perMessageDeflate: false });
  const origins = new Set(allowedOrigins.split(',').map(s=>s.trim()).filter(Boolean));
  server.on('upgrade', (req, socket, head) => {
    const origin = req.headers.origin;
    const sameOrigin = origin === `https://${req.headers.host}` || origin === `http://${req.headers.host}`;
    if (req.url !== '/ws' || wss.clients.size >= 24 || (origin && !sameOrigin && !origins.has(origin))) {
      socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n'); return;
    }
    wss.handleUpgrade(req, socket, head, ws => wss.emit('connection', ws, req));
  });
  const send = (ws, data) => { if (ws.readyState === WebSocket.OPEN && ws.bufferedAmount < 512000) ws.send(JSON.stringify(data)); };
  wss.on('connection', ws => {
    ws.alive = true; ws.joinedAt = Date.now(); let player; let bucket = 80; let refill = Date.now();
    ws.on('error', () => {});
    ws.on('pong', () => { ws.alive = true; });
    send(ws, {type:'hello', protocol:1});
    ws.on('message', raw => {
      const now = Date.now(); bucket = Math.min(80, bucket + (now-refill)*0.06); refill=now;
      if (--bucket < 0) { ws.close(1008,'Çok fazla mesaj'); return; }
      let msg; try { msg=JSON.parse(raw.toString()); } catch { return; }
      if (!msg || typeof msg !== 'object') return;
      if (msg.type === 'join' && !player) {
        try { player=game.join(msg.name,msg.skin,now); send(ws,{type:'welcome',id:player.id}); send(ws,game.snapshot(now)); }
        catch (e) { send(ws,{type:'error',message:e.message}); }
      } else if (msg.type === 'input' && player) { game.input(player,msg); ws.lastInput = now; }
      else if (msg.type === 'respawn' && player) game.respawn(player,now);
      else if (msg.type === 'ping') send(ws,{type:'pong',time:msg.time});
    });
    ws.on('close', () => { if(player) game.players.delete(player.id); });
    ws.getPlayer = () => player;
  });
  let previous = Date.now(), tickNumber = 0, lastFood = game.food.slice();
  const tick = setInterval(() => {
    const now=Date.now();
    for(const ws of wss.clients) { const p=ws.getPlayer(); if (p && now-(ws.lastInput || 0)>700) p.dx=p.dy=0; }
    game.step((now-previous)/1000,now); previous=now;
    if (++tickNumber % 2 === 0) {
      const { food, ...snapshot }=game.snapshot(now);
      // Food only changes when eaten: send full map on join, then changed slots.
      snapshot.foodChanges=food.filter((f,i)=>f!==lastFood[i]); lastFood=food.slice();
      for(const ws of wss.clients) if(ws.getPlayer()) send(ws,snapshot);
    }
  }, 1000/30);
  const heartbeat=setInterval(()=>{
    for(const ws of wss.clients) {
      if(!ws.alive || (!ws.getPlayer() && Date.now()-ws.joinedAt>60000)) { ws.terminate(); continue; }
      ws.alive=false; ws.ping();
    }
  },15000);
  function stop() { clearInterval(tick); clearInterval(heartbeat); for(const ws of wss.clients) ws.terminate(); wss.close(); return new Promise(resolve=>server.close(resolve)); }
  return {server,wss,game,stop};
}
if(require.main === module) {
  const app=createServer(); const port=Number(process.env.PORT)||3000;
  app.server.listen(port,'0.0.0.0',()=>console.log(`THE ERİNÇ online: http://localhost:${port}`));
  for(const signal of ['SIGTERM','SIGINT']) process.on(signal,()=>{ app.stop().then(()=>process.exit(0)); });
}
module.exports={createServer};
