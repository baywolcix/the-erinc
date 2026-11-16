"use strict";
// BULUT HOME istemcisi — bağımlılıksız, derleme adımı yok.
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const el = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat()) if (k != null && k !== false) e.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return e;
};
const fmtTime = (iso) => iso ? new Date(iso).toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" }) : "—";
const fmtBytes = (n) => n == null ? "—" : n > 1e9 ? (n / 1e9).toFixed(1) + " GB" : n > 1e6 ? (n / 1e6).toFixed(1) + " MB" : (n / 1e3).toFixed(0) + " KB";
const STATUS_TR = { pending: "Bekliyor", waiting_approval: "Onay bekliyor", running: "Çalışıyor", done: "Tamamlandı", failed: "Başarısız", cancelled: "İptal" };
const KIND_TR = { fact: "Bilgi", preference: "Tercih", goal: "Hedef", decision: "Karar", project: "Proje", date: "Tarih", note: "Not" };

function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg; t.className = "toast" + (err ? " err" : "");
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.add("hidden"), 3500);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    method: opts.method || "GET",
    headers: { "Content-Type": "application/json", "X-Bulut": "1" },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    credentials: "same-origin",
  });
  let data = null;
  try { data = await res.json(); } catch { /* boş yanıt */ }
  if (res.status === 401 && !path.startsWith("/api/auth")) { showAuth(false); throw new Error("Oturum gerekli"); }
  if (!res.ok) {
    const d = data && data.detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg).join(", ") : `Hata ${res.status}`);
  }
  if (res.status === 202 && data && data.approval_required) toast(`Onay Merkezi'ne gönderildi (#${data.approval_id}).`);
  return data;
}

/* ---------------- giriş ---------------- */
let setupMode = false;
function showAuth(needsSetup) {
  setupMode = needsSetup;
  $("#app").classList.add("hidden"); $("#auth").classList.remove("hidden");
  $("#setup-token-row").classList.toggle("hidden", !needsSetup);
  $("#auth-hint").textContent = needsSetup ? "İlk kurulum: sahip hesabını oluştur. Kurulum kodu sunucu kayıtlarında yazar." : "Giriş yap";
  const pw = $("#auth-form [name=password]");
  pw.minLength = needsSetup ? 10 : 1;
  pw.autocomplete = needsSetup ? "new-password" : "current-password";
}
$("#auth-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const body = { username: f.get("username"), password: f.get("password") };
  if (setupMode) body.setup_token = f.get("setup_token");
  $("#auth-error").textContent = "";
  try {
    await api(setupMode ? "/api/auth/setup" : "/api/auth/login", { method: "POST", body });
    e.target.reset(); start();
  } catch (err) { $("#auth-error").textContent = err.message; }
});
$("#logout").addEventListener("click", async () => { await api("/api/auth/logout", { method: "POST" }).catch(() => {}); showAuth(false); });

/* ---------------- gezinme ---------------- */
const loaders = {};
function go(view) {
  $$(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + view));
  try { localStorage.setItem("bulut.view", view); } catch { /* yok say */ }
  if (loaders[view]) loaders[view]().catch((e) => toast(e.message, true));
}
$$(".nav a").forEach((a) => a.addEventListener("click", () => go(a.dataset.view)));

/* ---------------- sohbet ---------------- */
let convId = null, sending = false;
const SUGGESTIONS = ["BULUT, bugün ne yaptık?", "Yan Daire'nin durumunu özetle", "Bu hafta hangi işten daha fazla para kazanabiliriz?", "Mağaranın Dışı için 5 video fikri"];
function renderSuggestions() {
  const box = $("#suggestions"); box.replaceChildren();
  SUGGESTIONS.forEach((s) => box.append(el("button", { type: "button", onclick: () => { $("#input").value = s; send(); } }, s)));
}
function addMsg(role, content, foot) {
  $("#chat-empty").classList.add("hidden");
  const m = el("div", { class: "msg " + role }, content, foot ? el("div", { class: "foot" }, foot) : null);
  $("#messages").append(m); m.scrollIntoView({ block: "end" });
  return m;
}
async function loadConversation(id) {
  const c = await api("/api/conversations/" + id);
  convId = c.id; $("#conv-title").textContent = c.title;
  $$("#messages .msg").forEach((m) => m.remove());
  if (!c.messages.length) $("#chat-empty").classList.remove("hidden");
  c.messages.forEach((m) => addMsg(m.role, m.content, m.role === "assistant" ? `${fmtTime(m.created_at)} · ${m.model || ""}` : null));
}
function newConversation() {
  convId = null; $("#conv-title").textContent = "Yeni konuşma";
  $$("#messages .msg").forEach((m) => m.remove()); $("#chat-empty").classList.remove("hidden");
}
async function toggleConvList() {
  const box = $("#conv-list");
  if (!box.classList.contains("hidden")) { box.classList.add("hidden"); return; }
  const list = await api("/api/conversations");
  box.replaceChildren(...(list.length ? list.map((c) => el("a", { onclick: () => { box.classList.add("hidden"); loadConversation(c.id); } },
    el("span", {}, c.title), el("span", { class: "muted small" }, fmtTime(c.updated_at)))) : [el("p", { class: "muted small" }, "  Henüz konuşma yok.")]));
  if (convId) box.append(el("a", { class: "small", onclick: async () => {
    if (!confirm("Bu konuşma silinsin mi?")) return;
    await api("/api/conversations/" + convId, { method: "DELETE" }); box.classList.add("hidden"); newConversation(); toast("Silindi");
  } }, el("span", { class: "error" }, "Bu konuşmayı sil")));
  box.classList.remove("hidden");
}
$("#conv-toggle").addEventListener("click", () => toggleConvList().catch((e) => toast(e.message, true)));
$("#conv-new").addEventListener("click", newConversation);

async function send() {
  const input = $("#input"), text = input.value.trim();
  if (!text || sending) return;
  sending = true; $("#send").disabled = true;
  input.value = ""; autosize();
  addMsg("user", text);
  const wait = el("div", { class: "msg assistant thinking" }, el("div", { class: "brand-mark" }), "Düşünüyor…");
  $("#messages").append(wait); wait.scrollIntoView({ block: "end" });
  try {
    const r = await api("/api/chat", { method: "POST", body: { message: text, conversation_id: convId, tier: $("#tier").value || null } });
    wait.remove();
    if (!convId) { convId = r.conversation_id; $("#conv-title").textContent = text.slice(0, 60); }
    const extras = [];
    if (r.memories_saved.length) extras.push(`🧠 ${r.memories_saved.length} bilgi hafızaya`);
    if (r.tasks_created.length) extras.push(`✓ ${r.tasks_created.length} görev eklendi`);
    addMsg("assistant", r.assistant_message.content,
      [r.assistant_message.model, `${r.usage.input_tokens}+${r.usage.output_tokens} token`, ...extras].join(" · "));
    speak(r.assistant_message.content);
    refreshBadges();
  } catch (e) {
    wait.remove(); addMsg("error", e.message);
  } finally { sending = false; $("#send").disabled = false; input.focus(); }
}
$("#composer").addEventListener("submit", (e) => { e.preventDefault(); send(); });
function autosize() { const t = $("#input"); t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 160) + "px"; }
$("#input").addEventListener("input", autosize);
$("#input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing && window.matchMedia("(min-width:900px)").matches) { e.preventDefault(); send(); } });

/* ---------------- ses: bas-konuş (tarayıcının kendi tanıma/sentez servisi) ---------------- */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let rec = null;
if (!SR) { $("#mic").disabled = true; $("#mic").title = "Bu tarayıcı konuşma tanımayı desteklemiyor"; }
function startRec(e) {
  e.preventDefault();
  if (!SR || rec) return;
  rec = new SR(); rec.lang = "tr-TR"; rec.interimResults = true; rec.continuous = true;
  const base = $("#input").value;
  rec.onresult = (ev) => { $("#input").value = (base + " " + [...ev.results].map((r) => r[0].transcript).join("")).trim(); autosize(); };
  rec.onerror = (ev) => toast("Mikrofon: " + ev.error, true);
  rec.onend = () => { $("#mic").classList.remove("rec"); rec = null; };
  rec.start(); $("#mic").classList.add("rec");
}
function stopRec() { if (rec) rec.stop(); }
$("#mic").addEventListener("pointerdown", startRec);
["pointerup", "pointerleave", "pointercancel"].forEach((ev) => $("#mic").addEventListener(ev, stopRec));
try { $("#tts").checked = localStorage.getItem("bulut.tts") === "1"; } catch { /* yok say */ }
$("#tts").addEventListener("change", () => { try { localStorage.setItem("bulut.tts", $("#tts").checked ? "1" : "0"); } catch { /* */ } });
function speak(text) {
  if (!$("#tts").checked || !window.speechSynthesis) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text.slice(0, 1500)); u.lang = "tr-TR";
  const v = speechSynthesis.getVoices().find((x) => x.lang && x.lang.startsWith("tr")); if (v) u.voice = v;
  speechSynthesis.speak(u);
}

/* ---------------- görevler ---------------- */
let taskFilter = "", projectsCache = [];
async function loadProjectsCache() { projectsCache = await api("/api/projects"); return projectsCache; }
loaders.tasks = async () => {
  const [data] = await Promise.all([api("/api/tasks" + (taskFilter ? "?status=" + taskFilter : "")), loadProjectsCache()]);
  const kindSel = $("#task-kind");
  if (!kindSel.options.length) Object.entries(data.kinds).forEach(([k, v]) => kindSel.append(el("option", { value: k, title: v }, { manual: "Elle", llm: "BULUT yapsın", plan: "Hedefi planla" }[k] || k)));
  const ps = $("#task-project"); ps.replaceChildren(el("option", { value: "" }, "Proje yok"), ...projectsCache.map((p) => el("option", { value: p.id }, p.name)));
  const tabs = $("#task-tabs"); tabs.replaceChildren();
  [["", "Tümü"], ["running", "Aktif"], ["pending", "Bekleyen"], ["waiting_approval", "Onay"], ["done", "Tamamlanan"], ["failed", "Başarısız"]].forEach(([s, label]) => {
    const n = s ? data.counts[s] : Object.values(data.counts).reduce((a, b) => a + b, 0);
    tabs.append(el("button", { class: taskFilter === s ? "active" : "", onclick: () => { taskFilter = s; loaders.tasks(); } }, `${label} ${n}`));
  });
  const list = $("#task-list");
  list.replaceChildren(...(data.tasks.length ? data.tasks.map(taskItem) : [el("p", { class: "muted" }, "Bu filtrede görev yok.")]));
};
function taskItem(t) {
  const actions = [];
  if (["pending", "failed", "cancelled"].includes(t.status)) actions.push(el("button", { class: "btn small", onclick: () => setTask(t.id, "done") }, "Tamamlandı"));
  if (["failed", "cancelled", "done"].includes(t.status)) actions.push(el("button", { class: "btn small ghost", onclick: () => setTask(t.id, "pending") }, "Yeniden aç"));
  if (["pending", "waiting_approval"].includes(t.status)) actions.push(el("button", { class: "btn small danger", onclick: () => setTask(t.id, "cancelled") }, "İptal"));
  return el("div", { class: "item" },
    el("div", { class: "item-head" }, el("span", { class: "title" }, `#${t.id} ${t.title}`), el("span", { class: "pill " + t.status }, STATUS_TR[t.status] || t.status)),
    el("div", { class: "meta" }, el("span", {}, "P" + t.priority), el("span", {}, t.kind), t.project_name ? el("span", {}, t.project_name) : null,
      el("span", {}, "kaynak: " + t.origin), el("span", {}, fmtTime(t.created_at)), t.attempts ? el("span", {}, `deneme ${t.attempts}/${t.max_attempts}`) : null,
      t.estimated_cost_usd != null ? el("span", {}, `tahmini $${t.estimated_cost_usd.toFixed(4)}`) : null),
    t.description ? el("div", { class: "muted small" }, t.description) : null,
    t.last_error ? el("pre", {}, "Hata: " + t.last_error) : null,
    t.output ? el("details", {}, el("summary", { class: "small" }, "Çıktı"), el("pre", {}, t.output)) : null,
    actions.length ? el("div", { class: "actions" }, actions) : null);
}
async function setTask(id, status) { try { await api(`/api/tasks/${id}/status`, { method: "POST", body: { status } }); loaders.tasks(); refreshBadges(); } catch (e) { toast(e.message, true); } }
$("#task-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  try {
    await api("/api/tasks", { method: "POST", body: { title: f.get("title"), description: f.get("description") || "", kind: f.get("kind"),
      project_id: f.get("project_id") ? Number(f.get("project_id")) : null, priority: Number(f.get("priority")) } });
    e.target.reset(); toast("Görev eklendi"); loaders.tasks(); refreshBadges();
  } catch (err) { toast(err.message, true); }
});

/* ---------------- projeler ---------------- */
loaders.projects = async () => {
  const ps = await loadProjectsCache();
  $("#project-list").replaceChildren(...ps.map((p) => {
    const pct = p.task_total ? Math.round(100 * p.task_done / p.task_total) : 0;
    const bar = el("i"); bar.style.width = pct + "%";
    const statusSel = el("select", { onchange: async (ev) => { await api("/api/projects/" + p.id, { method: "PATCH", body: { status: ev.target.value } }); toast("Güncellendi"); } },
      ...[["active", "Aktif"], ["paused", "Beklemede"], ["done", "Bitti"]].map(([v, l]) => el("option", { value: v, selected: p.status === v }, l)));
    return el("div", { class: "card" },
      el("div", { class: "item-head" }, el("span", { class: "title" }, p.name), statusSel),
      el("p", { class: "muted small" }, p.description || "—"),
      el("div", { class: "meta small muted" }, `${p.task_done}/${p.task_total} görev tamam · ${p.task_open} açık · ${p.task_failed} başarısız`),
      el("div", { class: "progress" }, bar),
      el("div", { class: "actions" },
        el("button", { class: "btn small", onclick: () => { go("tasks"); $("#task-project").value = p.id; $("#task-form [name=title]").focus(); } }, "Görev ekle"),
        el("button", { class: "btn small danger", onclick: async () => { if (confirm(`'${p.name}' silinsin mi? (Onay Merkezi'ne gider)`)) { await api("/api/projects/" + p.id, { method: "DELETE" }); refreshBadges(); } } }, "Sil…")));
  }));
};
$("#project-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  try { await api("/api/projects", { method: "POST", body: Object.fromEntries(f) }); e.target.reset(); loaders.projects(); }
  catch (err) { toast(err.message, true); }
});

/* ---------------- aktivite ---------------- */
let oldestActivity = null;
function activityItem(a) {
  return el("li", { class: a.level }, el("time", {}, fmtTime(a.created_at)), el("div", {}, a.summary),
    a.detail ? el("details", {}, el("summary", {}, "Ayrıntı"), el("pre", {}, a.detail)) : null);
}
loaders.activity = async () => {
  const rows = await api("/api/activity?limit=60");
  oldestActivity = rows.length ? rows[rows.length - 1].id : null;
  $("#activity-list").replaceChildren(...rows.map(activityItem));
  $("#activity-more").classList.toggle("hidden", rows.length < 60);
};
$("#activity-more").addEventListener("click", async () => {
  const rows = await api(`/api/activity?limit=60&before_id=${oldestActivity}`);
  rows.forEach((r) => $("#activity-list").append(activityItem(r)));
  oldestActivity = rows.length ? rows[rows.length - 1].id : oldestActivity;
  $("#activity-more").classList.toggle("hidden", rows.length < 60);
});

/* ---------------- hafıza ---------------- */
loaders.memory = async () => {
  const q = $("#memory-search").value.trim();
  const rows = await api("/api/memories" + (q ? "?q=" + encodeURIComponent(q) : ""));
  $("#memory-list").replaceChildren(...(rows.length ? rows.map(memoryItem) : [el("p", { class: "muted" }, q ? "Eşleşme yok." : "Henüz kayıt yok. BULUT sohbetten öğrendiklerini buraya yazar; sen de ekleyebilirsin.")]));
};
function memoryItem(m) {
  const body = el("div", { class: "title" }, m.content);
  return el("div", { class: "item" },
    el("div", { class: "item-head" }, body, el("span", { class: "pill" }, KIND_TR[m.kind] || m.kind)),
    el("div", { class: "meta" }, el("span", {}, "kaynak: " + m.source), el("span", {}, "güven " + Number(m.confidence).toFixed(1)),
      el("span", {}, "güncelleme " + fmtTime(m.updated_at)), m.pinned ? el("span", {}, "📌 sabit") : null),
    el("div", { class: "actions" },
      el("button", { class: "btn small", onclick: async () => {
        const v = prompt("Düzelt:", m.content); if (v == null || !v.trim()) return;
        await api("/api/memories/" + m.id, { method: "PATCH", body: { content: v.trim(), confidence: 1 } }); loaders.memory();
      } }, "Düzelt"),
      el("button", { class: "btn small ghost", onclick: async () => { await api("/api/memories/" + m.id, { method: "PATCH", body: { pinned: !m.pinned } }); loaders.memory(); } }, m.pinned ? "Sabitlemeyi kaldır" : "Sabitle"),
      el("button", { class: "btn small danger", onclick: async () => { if (confirm("Bu kayıt silinsin mi?")) { await api("/api/memories/" + m.id, { method: "DELETE" }); loaders.memory(); } } }, "Sil")));
}
$("#memory-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  try { await api("/api/memories", { method: "POST", body: { content: f.get("content"), kind: f.get("kind"), pinned: f.get("pinned") === "on", confidence: 1 } }); e.target.reset(); loaders.memory(); }
  catch (err) { toast(err.message, true); }
});
let memT; $("#memory-search").addEventListener("input", () => { clearTimeout(memT); memT = setTimeout(() => loaders.memory().catch(() => {}), 250); });
$("#memory-clear").addEventListener("click", async () => { if (confirm("Sabitlenmemiş tüm hafıza silinsin mi? (Onay Merkezi'ne gider)")) { await api("/api/memories/clear", { method: "POST" }); refreshBadges(); } });

/* ---------------- raporlar ---------------- */
function lastDays(n) {
  const out = []; const d = new Date();
  for (let i = n - 1; i >= 0; i--) { const x = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() - i)); out.push(x.toISOString().slice(0, 10)); }
  return out;
}
function barChart(container, days, series) {
  const max = Math.max(1e-9, ...days.map((d) => series.reduce((s, x) => s + (x.map[d] || 0), 0)));
  container.replaceChildren(...days.map((d) => {
    const col = el("div", { class: "bar", title: d });
    const total = series.reduce((s, x) => s + (x.map[d] || 0), 0);
    if (total) col.append(el("span", {}, series[0].label ? series[0].label(total) : total));
    series.forEach((x) => { const v = x.map[d] || 0; if (!v) return; const b = el("i", { class: x.cls || "" }); b.style.height = (100 * v / max) + "%"; col.append(b); });
    col.append(el("em", {}, d.slice(8)));
    return col;
  }));
}
loaders.reports = async () => {
  const [r, s] = await Promise.all([api("/api/reports/daily?days=14"), api("/api/system")]);
  const days = lastDays(14), rate = r.usd_try_rate;
  const costMap = Object.fromEntries(r.cost_by_day.map((x) => [x.day, rate ? x.usd * rate : x.usd]));
  barChart($("#cost-chart"), days, [{ map: costMap, label: (v) => v.toFixed(2) }]);
  $("#cost-note").textContent = rate ? "TL cinsinden (girilen kur: " + rate + "). Fiyat tablosu tarihi: " + s.models.prices_as_of + ", canlı doğrulanmadı." : "USD cinsinden — TL için BULUT_USD_TRY_RATE gir.";
  barChart($("#task-chart"), days, [
    { map: Object.fromEntries(r.tasks_done_by_day.map((x) => [x.day, x.n])) },
    { map: Object.fromEntries(r.tasks_failed_by_day.map((x) => [x.day, x.n])), cls: "fail" }]);
  const today = r.cost_by_day.find((x) => x.day === r.today) || { usd: 0, calls: 0 };
  const b = s.budget;
  $("#report-stats").replaceChildren(
    stat(r.today_detail.done.length, "Bugün tamamlanan"), stat(r.today_detail.failed.length, "Bugün başarısız"),
    stat(rate ? (today.usd * rate).toFixed(2) + " ₺" : "$" + today.usd.toFixed(4), "Bugünkü AI maliyeti"),
    stat(b.spent_try != null ? b.spent_try.toFixed(2) + " / " + b.budget_try + " ₺" : "$" + b.spent_usd.toFixed(4), "Bu ay"));
  const list = (title, rows, f) => el("div", {}, el("h3", {}, title), rows.length ? el("ul", {}, ...rows.map((x) => el("li", {}, f(x)))) : el("p", { class: "muted small" }, "Yok."));
  $("#today-detail").replaceChildren(el("h3", {}, "Bugünün özeti (" + r.today + ", UTC)"),
    el("p", { class: "small muted" }, `${r.today_detail.messages} mesaj`),
    list("Tamamlanan", r.today_detail.done, (x) => `#${x.id} ${x.title}`),
    list("Başarısız", r.today_detail.failed, (x) => `#${x.id} ${x.title} — ${x.last_error || ""}`),
    list("Devam eden / bekleyen", r.today_detail.in_progress, (x) => `#${x.id} ${x.title} (${STATUS_TR[x.status]})`));
};
const stat = (v, label) => el("div", { class: "stat" }, el("b", {}, v), el("span", {}, label));

/* ---------------- sistem ---------------- */
loaders.system = async () => {
  const s = await api("/api/system"), sv = s.server, b = s.budget;
  $("#system-stats").replaceChildren(
    stat(sv.memory ? sv.memory.used_pct + "%" : "—", "RAM kullanımı"), stat(fmtBytes(sv.process_rss), "BULUT bellek"),
    stat(sv.loadavg ? sv.loadavg[0] : "—", "Yük (1 dk)"), stat(sv.disk.used_pct + "%", "Disk"));
  const pct = b.spent_try != null ? Math.min(100, 100 * b.spent_try / b.budget_try) : 0;
  const bar = el("i"); bar.style.width = pct + "%"; if (pct > 80) bar.style.background = "var(--warn)";
  $("#budget-card").replaceChildren(el("h3", {}, "API bütçesi (bu ay)"),
    el("dl", { class: "kv" },
      el("dt", {}, "Harcanan"), el("dd", {}, b.spent_try != null ? `${b.spent_try.toFixed(2)} ₺ ($${b.spent_usd.toFixed(4)})` : `$${b.spent_usd.toFixed(4)}`),
      el("dt", {}, "Sınır"), el("dd", {}, b.budget_try + " ₺"),
      el("dt", {}, "Kur"), el("dd", {}, b.usd_try_rate ? b.usd_try_rate + " ₺/$ (elle girilen)" : "girilmedi"),
      el("dt", {}, "Çağrı"), el("dd", {}, `${b.calls_this_month}` + (b.unknown_cost_calls ? ` (${b.unknown_cost_calls} maliyeti bilinmiyor)` : "")),
      el("dt", {}, "Durum"), el("dd", { class: b.blocked ? "error" : "" }, b.blocked ? "Ücretli çağrılar KAPALI" + (b.reason ? " — " + b.reason : "") : "Açık")),
    el("div", { class: "progress" }, bar));
  $("#system-detail").replaceChildren(el("h3", {}, "Ayrıntılar"),
    el("dl", { class: "kv" },
      el("dt", {}, "Sürüm"), el("dd", {}, s.version), el("dt", {}, "Sunucu"), el("dd", {}, `${sv.hostname} · ${sv.os}`),
      el("dt", {}, "Çalışma süresi"), el("dd", {}, Math.round(sv.uptime_s / 60) + " dk"),
      el("dt", {}, "Veritabanı"), el("dd", {}, fmtBytes(sv.db_size)),
      el("dt", {}, "Hızlı model"), el("dd", {}, s.models.fast), el("dt", {}, "Akıllı model"), el("dd", {}, s.models.smart),
      el("dt", {}, "Yedek zincir"), el("dd", {}, s.models.fallbacks.join(", ") || "—"),
      el("dt", {}, "Sağlayıcılar"), el("dd", {}, s.providers.map((p) => `${p.name}: ${p.configured ? "✓" : "anahtar yok"}`).join(" · ")),
      el("dt", {}, "Görev işçisi"), el("dd", {}, s.worker.enabled ? "çalışıyor" : "kapalı"),
      el("dt", {}, "Cihazlar"), el("dd", {}, s.devices.map((d) => `${d.name}: ${d.status}`).join(" · ")),
      el("dt", {}, "Yedekler"), el("dd", {}, s.backups.slice(0, 3).join(", ") || "henüz yok")));
};
$("#backup-now").addEventListener("click", async () => { try { const r = await api("/api/system/backup", { method: "POST" }); toast("Yedek: " + r.file); loaders.system(); } catch (e) { toast(e.message, true); } });

/* ---------------- onaylar ---------------- */
const ACTION_TR = { spend_money: "Para harcama", delete_data: "Veri silme", account_change: "Hesap ayarı", live_change: "Canlı sistem", external_irreversible: "Geri alınamaz harici işlem" };
loaders.approvals = async () => {
  const rows = await api("/api/approvals");
  $("#approval-list").replaceChildren(...(rows.length ? rows.map((a) => el("div", { class: "item" },
    el("div", { class: "item-head" }, el("span", { class: "title" }, a.summary), el("span", { class: "pill " + (a.status === "pending" ? "waiting_approval" : a.status === "rejected" ? "failed" : "done") }, a.status)),
    el("div", { class: "meta" }, el("span", {}, ACTION_TR[a.action] || a.action), el("span", {}, fmtTime(a.created_at)), a.decided_at ? el("span", {}, "karar: " + fmtTime(a.decided_at)) : null),
    a.status === "pending" ? el("div", { class: "actions" },
      el("button", { class: "btn small primary", onclick: () => decide(a.id, "approve") }, "Onayla"),
      el("button", { class: "btn small danger", onclick: () => decide(a.id, "reject") }, "Reddet")) : null))
    : [el("p", { class: "muted" }, "Bekleyen onay yok.")]));
};
async function decide(id, d) { try { const r = await api(`/api/approvals/${id}/${d}`, { method: "POST" }); toast(r.result || (d === "approve" ? "Onaylandı" : "Reddedildi")); loaders.approvals(); refreshBadges(); } catch (e) { toast(e.message, true); } }

/* ---------------- rozetler ---------------- */
async function refreshBadges() {
  try {
    const [t, a] = await Promise.all([api("/api/tasks?status=failed"), api("/api/approvals?status=pending")]);
    const bt = $("#badge-tasks"), ba = $("#badge-approvals");
    bt.textContent = t.counts.failed; bt.classList.toggle("hidden", !t.counts.failed);
    ba.textContent = a.length; ba.classList.toggle("hidden", !a.length);
  } catch { /* sessiz */ }
}

/* ---------------- başlangıç ---------------- */
async function start() {
  const st = await api("/api/auth/status");
  if (!st.user) { showAuth(st.needs_setup); return; }
  $("#auth").classList.add("hidden"); $("#app").classList.remove("hidden");
  renderSuggestions();
  let v = "chat"; try { v = localStorage.getItem("bulut.view") || "chat"; } catch { /* */ }
  go(v); refreshBadges();
  clearInterval(start._i); start._i = setInterval(refreshBadges, 30000);
}
start().catch((e) => { document.body.prepend(el("p", { class: "error" }, "Sunucuya ulaşılamadı: " + e.message)); });
