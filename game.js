'use strict';
const { randomUUID } = require('node:crypto');
const WORLD = 3200;
const radius = mass => Math.sqrt(mass) * 4;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
class Game {
  constructor({ now = Date.now(), random = Math.random, eventInterval = 300000, eventDuration = 60000 } = {}) {
    this.random = random; this.players = new Map(); this.food = []; this.sequence = 0;
    this.eventInterval = eventInterval; this.eventDuration = eventDuration;
    this.nextEvent = now + eventInterval; this.pastry = null; this.notices = []; this.eventNumber = 0;
    for (let i = 0; i < 550; i++) this.food.push(this.makeFood(i));
  }
  makeFood(id) { return { id, x: 24 + this.random() * (WORLD - 48), y: 24 + this.random() * (WORLD - 48), color: Math.floor(this.random() * 5) }; }
  join(name, skin, now) {
    if (this.players.size >= 10) throw Error('Pastane dolu! En fazla 10 kişi oynayabilir.');
    if (typeof name !== 'string') throw Error('Bir oyuncu adı yaz.');
    name = name.trim().replace(/[\u0000-\u001f\u007f]/g, '').slice(0, 20);
    if (!name) throw Error('Bir oyuncu adı yaz.');
    if ([...this.players.values()].some(p => p.name === name)) throw Error('Bu isim şu anda kullanılıyor.');
    const p = { id: randomUUID(), name, skin: Number.isInteger(skin) && skin >= 0 && skin < 6 ? skin : 0,
      rainbow: name === 'kaptan' || name === 'samet', mass: name === 'umutsiker' ? 2500 : 70,
      x: 0, y: 0, dx: 0, dy: 0, alive: true, shieldUntil: now + 4000, wins: 0, diedAt: 0 };
    this.spawn(p); this.players.set(p.id, p); return p;
  }
  spawn(p) {
    const r = radius(p.mass);
    // Choose the safest of 40 candidate points, even when a giant is already in the room.
    let best = -Infinity;
    for (let i = 0; i < 40; i++) {
      const x = r + this.random() * (WORLD - 2 * r), y = r + this.random() * (WORLD - 2 * r);
      let safety = Infinity;
      for (const other of this.players.values()) if (other.alive && other.id !== p.id)
        safety = Math.min(safety, Math.hypot(x - other.x, y - other.y) - r - radius(other.mass));
      if (safety > best) { best = safety; p.x = x; p.y = y; }
    }
  }
  input(p, msg) {
    if (!p.alive || typeof msg.x !== 'number' || typeof msg.y !== 'number' || !Number.isFinite(msg.x) || !Number.isFinite(msg.y)) return;
    const length = Math.hypot(msg.x, msg.y), scale = Math.max(1, length);
    p.dx = msg.x / scale; p.dy = msg.y / scale;
  }
  respawn(p, now) {
    if (p.alive || now - p.diedAt < 1500) return false;
    p.mass = p.name === 'umutsiker' ? 2500 : 70; p.alive = true; p.dx = p.dy = 0;
    p.shieldUntil = now + 4000; this.spawn(p); return true;
  }
  notice(text, now) { this.notices.push({ id: ++this.sequence, text, until: now + 9000 }); this.notices = this.notices.slice(-5); }
  step(dt, now) {
    dt = clamp(dt, 0, 0.1);
    if (now >= this.nextEvent) {
      this.eventNumber++;
      this.pastry = { x: WORLD / 2, y: WORLD / 2, until: now + this.eventDuration, number: this.eventNumber };
      this.nextEvent += (Math.floor((now - this.nextEvent) / this.eventInterval) + 1) * this.eventInterval;
      this.notice('SON ZEYTİNLİ POĞAÇA! Haritanın merkezine koş!', now);
    }
    if (this.pastry && now >= this.pastry.until) { this.pastry = null; this.notice('Poğaça soğudu… Bir sonraki fırını bekle.', now); }
    for (const p of this.players.values()) {
      if (!p.alive) continue;
      const r = radius(p.mass), speed = 245 * Math.pow(70 / p.mass, 0.20);
      p.x = clamp(p.x + p.dx * speed * dt, r, WORLD - r);
      p.y = clamp(p.y + p.dy * speed * dt, r, WORLD - r);
      for (let i = 0; i < this.food.length; i++) if (Math.hypot(p.x - this.food[i].x, p.y - this.food[i].y) < r) {
        p.mass = Math.min(14000, p.mass + 2); this.food[i] = this.makeFood(this.food[i].id);
      }
    }
    const sorted = [...this.players.values()].filter(p => p.alive).sort((a, b) => b.mass - a.mass);
    for (const big of sorted) {
      if (!big.alive || now < big.shieldUntil) continue;
      for (const small of sorted) {
        if (big === small || !small.alive || now < small.shieldUntil || big.mass < small.mass * 1.25) continue;
        if (Math.hypot(big.x - small.x, big.y - small.y) < radius(big.mass) - radius(small.mass) * 0.45) {
          big.mass = Math.min(14000, big.mass + small.mass * 0.8); small.alive = false; small.dx = small.dy = 0;
          small.diedAt = now; small.killer = big.name; this.notice(`${big.name}, ${small.name} oyuncusunu yuttu!`, now);
        }
      }
    }
    // Resolve the single pastry after eating, so a swallowed player cannot win it.
    if (this.pastry) for (const p of sorted) {
      if (p.alive && now >= p.shieldUntil && Math.hypot(p.x - this.pastry.x, p.y - this.pastry.y) < radius(p.mass) + 25) {
        p.mass = Math.min(14000, p.mass + 600); p.wins++; this.pastry = null;
        this.notice(`🏆 Son zeytinli poğaça ${p.name} oyuncusunun! +600 kütle`, now); break;
      }
    }
    this.notices = this.notices.filter(n => n.until > now);
  }
  snapshot(now) {
    return { type: 'state', now, world: WORLD, nextEvent: this.nextEvent, pastry: this.pastry, food: this.food,
      count: this.players.size, capacity: 10, notices: this.notices,
      players: [...this.players.values()].map(({ dx, dy, diedAt, ...p }) => ({ ...p, mass: Math.round(p.mass) })),
      leaderboard: [...this.players.values()].filter(p => p.alive).sort((a,b) => b.mass-a.mass).map(p => ({ id:p.id, name:p.name, mass:Math.round(p.mass), wins:p.wins })) };
  }
}
module.exports = { Game, radius, WORLD };
