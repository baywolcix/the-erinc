"""BULUT HOME HTTP API + statik web arayüzü."""
from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, approvals, auth, briefing, chat, memory, sysinfo, tasks
from . import tools as _tools  # noqa: F401 — onay yürütücülerini kaydeder
from .web import WebClient
from .config import Settings, load_settings
from .db import Database, log_activity, now_iso
from .llm.pricing import PRICES_AS_OF
from .llm.providers import AnthropicProvider, OpenAICompatProvider
from .llm.router import BudgetError, LLMRouter, NoProviderError, ProvidersFailed, month_start_utc

STATIC = Path(__file__).parent / "static"
COOKIE = "bulut_session"
BACKUP_KEEP = 7


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)

class SetupIn(LoginIn):
    setup_token: str

class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    conversation_id: int | None = None
    tier: str | None = None

class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field("", max_length=10000)
    kind: str = "manual"
    project_id: int | None = None
    priority: int = Field(3, ge=1, le=5)

class TaskStatusIn(BaseModel):
    status: str
    note: str | None = None

class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9-]+$")
    description: str = Field("", max_length=2000)

class ProjectPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = Field(None, pattern=r"^(active|paused|done)$")

class MemoryIn(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    kind: str = "fact"
    confidence: float = Field(1.0, ge=0, le=1)
    pinned: bool = False
    project_id: int | None = None

class MemoryPatch(BaseModel):
    content: str | None = Field(None, max_length=4000)
    kind: str | None = None
    confidence: float | None = Field(None, ge=0, le=1)
    pinned: bool | None = None


class LiveTestIn(BaseModel):
    confirm: str = Field(max_length=40)


class State:
    settings: Settings
    db: Database
    router: LLMRouter
    worker: tasks.TaskWorker | None = None
    setup_token: str | None = None
    web: WebClient | None = None


def build_providers(s: Settings) -> dict:
    return {
        "anthropic": AnthropicProvider(s.anthropic_api_key),
        "openai_compat": OpenAICompatProvider(s.compat_api_key, s.compat_base_url, s.compat_model,
                                              s.compat_price_in, s.compat_price_out),
    }


def make_backup(st: State) -> Path:
    bdir = st.settings.data_dir / "backups"
    dest = bdir / f"bulut-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.db"
    st.db.backup(dest)
    # Döndürme politikası: yalnızca BULUT'un kendi ürettiği yedeklerden en yeni BACKUP_KEEP tanesi tutulur.
    olds = sorted(bdir.glob("bulut-*.db"))[:-BACKUP_KEEP]
    for o in olds:
        o.unlink(missing_ok=True)
    log_activity(st.db, "backup", f"Veritabanı yedeği alındı: {dest.name}")
    return dest


async def _daily_backup_loop(st: State) -> None:
    while True:
        bdir = st.settings.data_dir / "backups"
        latest = max(bdir.glob("bulut-*.db"), default=None, key=lambda p: p.stat().st_mtime) if bdir.exists() else None
        if latest is None or (datetime.now().timestamp() - latest.stat().st_mtime) > 86400:
            try:
                await asyncio.to_thread(make_backup, st)
            except Exception as e:  # noqa: BLE001
                log_activity(st.db, "backup_error", "Yedek alınamadı", detail=str(e), level="error")
        await asyncio.sleep(3600)


async def _brief_scheduler_loop(st: State) -> None:
    while True:
        try:
            t = briefing.maybe_schedule(st.db, st.settings.brief_time, st.settings.timezone)
            if t and not t.get("deduplicated"):
                log_activity(st.db, "schedule", f"Günlük brifing görevi açıldı (#{t['id']})", ref=f"task:{t['id']}")
        except Exception as e:  # noqa: BLE001
            log_activity(st.db, "schedule_error", "Brifing zamanlayıcısı hatası", detail=str(e)[:500], level="error")
        await asyncio.sleep(60)


def create_app(settings: Settings | None = None, providers: dict | None = None, start_worker: bool | None = None,
               web: WebClient | None = None) -> FastAPI:
    st = State()
    st.settings = settings or load_settings()
    from .redact import install_logging_filter, register
    register(st.settings.secret_key, st.settings.anthropic_api_key, st.settings.compat_api_key,
             st.settings.brave_api_key)
    install_logging_filter()
    st.db = Database(st.settings.db_path)
    st.db.init()
    st.router = LLMRouter(st.db, st.settings, providers if providers is not None else build_providers(st.settings))
    st.web = web or WebClient(st.db, st.settings)

    if not auth.has_owner(st.db):
        tf = st.settings.data_dir / ".setup_token"
        if not tf.exists():
            tf.write_text(secrets.token_urlsafe(18))
            tf.chmod(0o600)
        st.setup_token = tf.read_text().strip()
        print(f"[BULUT] İlk kurulum: web arayüzünde bu kurulum kodunu kullan → {st.setup_token}", flush=True)

    run_worker = st.settings.worker_enabled if start_worker is None else start_worker

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bg = []
        if run_worker:
            st.worker = tasks.TaskWorker(st.db, st.router, web=st.web)
            bg.append(asyncio.create_task(st.worker.run_forever()))
            bg.append(asyncio.create_task(_daily_backup_loop(st)))
            bg.append(asyncio.create_task(_brief_scheduler_loop(st)))
        log_activity(st.db, "system", f"BULUT HOME {__version__} başlatıldı")
        yield
        if st.worker:
            st.worker.stop()
        for t in bg:
            t.cancel()

    app = FastAPI(title="BULUT HOME", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.bulut = st

    @app.middleware("http")
    async def security(request: Request, call_next):
        # Durum değiştiren isteklerde özel başlık zorunlu (CSRF'e karşı ikinci katman; çerez zaten SameSite=Strict)
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.url.path.startswith("/api/"):
            if request.headers.get("x-bulut") != "1":
                return JSONResponse({"detail": "Eksik güvenlik başlığı"}, status_code=403)
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; media-src 'self' blob:; frame-ancestors 'none'")
        resp.headers["Permissions-Policy"] = "microphone=(self), camera=(), geolocation=()"
        return resp

    def current_user(request: Request) -> dict:
        user = auth.session_user(st.db, st.settings.secret_key, request.cookies.get(COOKIE))
        if not user:
            raise HTTPException(401, "Giriş gerekli")
        return user

    def _ip(request: Request) -> str:
        return request.client.host if request.client else "?"

    def _set_cookie(resp: Response, token: str) -> None:
        resp.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=st.settings.cookie_secure,
                        max_age=auth.SESSION_DAYS * 86400, path="/")

    # ---------------- auth ----------------


    @app.get("/api/health")
    def health():
        return {"ok": True, "version": __version__}

    @app.get("/api/auth/status")
    def auth_status(request: Request):
        user = auth.session_user(st.db, st.settings.secret_key, request.cookies.get(COOKIE))
        return {"needs_setup": not auth.has_owner(st.db), "user": user}

    @app.post("/api/auth/setup")
    def setup(body: SetupIn, request: Request, response: Response):
        if auth.has_owner(st.db):
            raise HTTPException(409, "Kurulum zaten yapılmış")
        if not st.setup_token or not secrets.compare_digest(body.setup_token.strip(), st.setup_token):
            raise HTTPException(403, "Kurulum kodu hatalı (sunucu kayıtlarında yazıyor)")
        try:
            auth.create_owner(st.db, body.username, body.password)
        except ValueError as e:
            raise HTTPException(400, str(e))
        (st.settings.data_dir / ".setup_token").unlink(missing_ok=True)
        st.setup_token = None
        token = auth.login(st.db, st.settings.secret_key, body.username, body.password, _ip(request),
                           request.headers.get("user-agent", ""))
        _set_cookie(response, token)
        log_activity(st.db, "auth", "Sahip hesabı oluşturuldu")
        return {"ok": True}

    @app.post("/api/auth/login")
    def login(body: LoginIn, request: Request, response: Response):
        ip = _ip(request)
        if auth.too_many_failures(st.db, ip):
            raise HTTPException(429, "Çok fazla hatalı deneme. 15 dakika sonra tekrar dene.")
        token = auth.login(st.db, st.settings.secret_key, body.username, body.password, ip,
                           request.headers.get("user-agent", ""))
        if not token:
            log_activity(st.db, "auth", f"Hatalı giriş denemesi ({ip})", level="warn")
            raise HTTPException(401, "Kullanıcı adı veya parola hatalı")
        _set_cookie(response, token)
        return {"ok": True}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        auth.logout(st.db, st.settings.secret_key, request.cookies.get(COOKIE))
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    # ---------------- sohbet ----------------

    @app.post("/api/chat")
    async def chat_send(body: ChatIn, user=Depends(current_user)):
        try:
            return await chat.reply(st.db, st.router, body.conversation_id, body.message, body.tier, web=st.web)
        except KeyError as e:
            raise HTTPException(404, str(e))
        except ValueError as e:
            raise HTTPException(400, str(e))
        except BudgetError as e:
            log_activity(st.db, "budget_block", "Bütçe koruması çağrıyı engelledi", detail=str(e), level="warn")
            raise HTTPException(402, str(e))
        except (NoProviderError, ProvidersFailed) as e:
            raise HTTPException(503, str(e))

    @app.get("/api/conversations")
    def conversations(user=Depends(current_user)):
        return st.db.query("SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id=c.id) AS message_count "
                           "FROM conversations c ORDER BY updated_at DESC LIMIT 100")

    @app.get("/api/conversations/{cid}")
    def conversation(cid: int, user=Depends(current_user)):
        c = st.db.one("SELECT * FROM conversations WHERE id=?", (cid,))
        if not c:
            raise HTTPException(404, "Konuşma yok")
        c["messages"] = st.db.query("SELECT id, role, content, model, created_at FROM messages WHERE conversation_id=? "
                                    "ORDER BY id", (cid,))
        return c

    @app.delete("/api/conversations/{cid}")
    def conversation_delete(cid: int, user=Depends(current_user)):
        # Sahibinin kendi sohbet geçmişini arayüzden silmesi doğrudan kullanıcı eylemidir.
        with st.db.tx() as t:
            n = t.execute("DELETE FROM conversations WHERE id=?", (cid,)).rowcount
        if not n:
            raise HTTPException(404, "Konuşma yok")
        log_activity(st.db, "conversation_deleted", f"Konuşma #{cid} silindi")
        return {"ok": True}

    # ---------------- görevler ----------------


    @app.get("/api/tasks")
    def task_list(status: str | None = None, project_id: int | None = None, user=Depends(current_user)):
        return {"tasks": tasks.list_tasks(st.db, status, project_id), "counts": tasks.counts(st.db), "kinds": tasks.KINDS}

    @app.post("/api/tasks")
    def task_create(body: TaskIn, user=Depends(current_user)):
        try:
            return tasks.create(st.db, body.title, body.description, body.kind, body.project_id, body.priority, origin="board")
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.get("/api/tasks/{tid}")
    def task_get(tid: int, user=Depends(current_user)):
        t = tasks.get(st.db, tid)
        if not t:
            raise HTTPException(404, "Görev yok")
        t["children"] = st.db.query("SELECT id, title, status FROM tasks WHERE parent_id=? ORDER BY id", (tid,))
        return t

    @app.post("/api/tasks/{tid}/status")
    def task_status(tid: int, body: TaskStatusIn, user=Depends(current_user)):
        try:
            return tasks.set_status(st.db, tid, body.status, body.note)
        except KeyError as e:
            raise HTTPException(404, str(e))
        except ValueError as e:
            raise HTTPException(400, str(e))

    # ---------------- projeler ----------------


    @app.get("/api/projects")
    def projects(user=Depends(current_user)):
        return st.db.query(
            "SELECT p.*, "
            "(SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id) AS task_total, "
            "(SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id AND t.status='done') AS task_done, "
            "(SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id AND t.status IN ('pending','running','waiting_approval')) AS task_open, "
            "(SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id AND t.status='failed') AS task_failed "
            "FROM projects p ORDER BY p.status='active' DESC, p.id")

    @app.post("/api/projects")
    def project_create(body: ProjectIn, user=Depends(current_user)):
        try:
            with st.db.tx() as t:
                pid = t.execute("INSERT INTO projects(slug,name,description,created_at,updated_at) VALUES (?,?,?,?,?)",
                                (body.slug, body.name, body.description, now_iso(), now_iso())).lastrowid
        except Exception:
            raise HTTPException(409, "Bu kısa ad zaten kullanılıyor")
        log_activity(st.db, "project_created", f"Proje eklendi: {body.name}", ref=f"project:{pid}")
        return st.db.one("SELECT * FROM projects WHERE id=?", (pid,))

    @app.patch("/api/projects/{pid}")
    def project_patch(pid: int, body: ProjectPatch, user=Depends(current_user)):
        fields = {k: v for k, v in body.model_dump().items() if v is not None}
        if fields:
            fields["updated_at"] = now_iso()
            with st.db.tx() as t:
                t.execute(f"UPDATE projects SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?", (*fields.values(), pid))
        p = st.db.one("SELECT * FROM projects WHERE id=?", (pid,))
        if not p:
            raise HTTPException(404, "Proje yok")
        return p

    @app.delete("/api/projects/{pid}")
    def project_delete(pid: int, user=Depends(current_user)):
        p = st.db.one("SELECT * FROM projects WHERE id=?", (pid,))
        if not p:
            raise HTTPException(404, "Proje yok")
        aid = approvals.request(st.db, "delete_data", f"'{p['name']}' projesini sil (görevler projesiz kalır)",
                                {"project_id": pid}, executor_name="delete_project")
        return JSONResponse({"approval_required": True, "approval_id": aid}, status_code=202)

    # ---------------- hafıza ----------------


    @app.get("/api/memories")
    def memories(q: str | None = None, user=Depends(current_user)):
        return memory.list_all(st.db, q)

    @app.post("/api/memories")
    def memory_add(body: MemoryIn, user=Depends(current_user)):
        mid = memory.add(st.db, body.content, body.kind, "user", body.confidence, body.project_id, body.pinned)
        return st.db.one("SELECT * FROM memories WHERE id=?", (mid,))

    @app.patch("/api/memories/{mid}")
    def memory_patch(mid: int, body: MemoryPatch, user=Depends(current_user)):
        d = body.model_dump()
        if d.get("pinned") is not None:
            d["pinned"] = 1 if d["pinned"] else 0
        if not memory.update(st.db, mid, **d):
            raise HTTPException(404, "Kayıt yok veya değişiklik yok")
        return st.db.one("SELECT * FROM memories WHERE id=?", (mid,))

    @app.delete("/api/memories/{mid}")
    def memory_delete(mid: int, user=Depends(current_user)):
        if not memory.delete(st.db, mid):
            raise HTTPException(404, "Kayıt yok")
        return {"ok": True}

    @app.post("/api/memories/clear")
    def memory_clear(user=Depends(current_user)):
        aid = approvals.request(st.db, "delete_data", "Sabitlenmemiş tüm hafıza kayıtlarını sil",
                                {"keep_pinned": True}, executor_name="clear_memories")
        return JSONResponse({"approval_required": True, "approval_id": aid}, status_code=202)

    # ---------------- onaylar ----------------
    @app.get("/api/approvals")
    def approval_list(status: str | None = None, user=Depends(current_user)):
        if status:
            return st.db.query("SELECT * FROM approvals WHERE status=? ORDER BY id DESC LIMIT 200", (status,))
        return st.db.query("SELECT * FROM approvals ORDER BY status='pending' DESC, id DESC LIMIT 200")

    @app.post("/api/approvals/{aid}/{decision}")
    def approval_decide(aid: int, decision: str, user=Depends(current_user)):
        if decision not in ("approve", "reject"):
            raise HTTPException(404, "Bilinmeyen karar")
        try:
            return approvals.decide(st.db, aid, decision == "approve", user["username"])
        except KeyError as e:
            raise HTTPException(404, str(e))
        except ValueError as e:
            raise HTTPException(409, str(e))

    # ---------------- aktivite / rapor / sistem ----------------
    @app.get("/api/activity")
    def activity(limit: int = 100, before_id: int | None = None, user=Depends(current_user)):
        limit = max(1, min(limit, 500))
        if before_id:
            return st.db.query("SELECT * FROM activity WHERE id<? ORDER BY id DESC LIMIT ?", (before_id, limit))
        return st.db.query("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,))

    @app.get("/api/reports/daily")
    def report_daily(days: int = 14, user=Depends(current_user)):
        days = max(1, min(days, 90))
        since = (datetime.now(timezone.utc) - timedelta(days=days - 1)).strftime("%Y-%m-%d")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cost = st.db.query("SELECT substr(created_at,1,10) AS day, COALESCE(SUM(cost_usd),0) AS usd, COUNT(*) AS calls, "
                           "SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens, SUM(1-ok) AS errors "
                           "FROM llm_calls WHERE substr(created_at,1,10) >= ? GROUP BY day ORDER BY day", (since,))
        done = st.db.query("SELECT substr(finished_at,1,10) AS day, COUNT(*) AS n FROM tasks WHERE status='done' "
                           "AND substr(finished_at,1,10) >= ? GROUP BY day", (since,))
        failed = st.db.query("SELECT substr(finished_at,1,10) AS day, COUNT(*) AS n FROM tasks WHERE status='failed' "
                             "AND substr(finished_at,1,10) >= ? GROUP BY day", (since,))
        return {
            "range_start": since, "today": today,
            "cost_by_day": cost,
            "tasks_done_by_day": done,
            "tasks_failed_by_day": failed,
            "today_detail": {
                "done": st.db.query("SELECT id,title FROM tasks WHERE status='done' AND substr(finished_at,1,10)=? ORDER BY id", (today,)),
                "failed": st.db.query("SELECT id,title,last_error FROM tasks WHERE status='failed' AND substr(finished_at,1,10)=? ORDER BY id", (today,)),
                "in_progress": st.db.query("SELECT id,title,status FROM tasks WHERE status IN ('running','pending','waiting_approval') ORDER BY priority, id LIMIT 20"),
                "messages": st.db.one("SELECT COUNT(*) AS n FROM messages WHERE substr(created_at,1,10)=?", (today,))["n"],
            },
            "usd_try_rate": st.settings.usd_try_rate,
            "timezone_note": "Günler UTC'ye göre gruplanır.",
        }

    @app.get("/api/system")
    def system(user=Depends(current_user)):
        provs = []
        for name, p in st.router.providers.items():
            provs.append({"name": name, "configured": p.available()})
        return {
            "version": __version__,
            "server": sysinfo.snapshot(st.settings.data_dir),
            "budget": st.router.budget_status(),
            "models": {"fast": st.settings.model_fast, "smart": st.settings.model_smart,
                       "fallbacks": st.settings.model_fallbacks, "prices_as_of": PRICES_AS_OF},
            "providers": provs,
            "worker": {"enabled": st.worker is not None},
            "web": {"search_backend": st.web.search_backend, "fetch": True,
                    "searches_today": st.web.searches_today(), "daily_limit": st.settings.web_daily_limit},
            "briefing": {"time": st.settings.brief_time or None, "timezone": st.settings.timezone},
            "tasks": tasks.counts(st.db),
            "pending_approvals": st.db.one("SELECT COUNT(*) AS n FROM approvals WHERE status='pending'")["n"],
            "devices": [{"name": "BULUT HOME (bu sunucu)", "status": "online"},
                        {"name": "Ana PC (Windows, GTX 1650)", "status": "bağlı değil — Faz 4"}],
            "month_start": month_start_utc(),
            "backups": sorted((p.name for p in (st.settings.data_dir / "backups").glob("bulut-*.db")), reverse=True)
                       if (st.settings.data_dir / "backups").exists() else [],
        }

    # ---------------- brifing / web / araç kayıtları ----------------
    @app.get("/api/briefings")
    def briefing_list(limit: int = 14, user=Depends(current_user)):
        return st.db.query("SELECT id, day, content, source, note, created_at FROM briefings ORDER BY day DESC LIMIT ?",
                           (max(1, min(limit, 90)),))

    @app.post("/api/briefings/generate")
    async def briefing_generate(user=Depends(current_user)):
        b = await briefing.generate(st.db, st.router, st.settings.timezone, st.settings.usd_try_rate)
        return {k: b[k] for k in ("id", "day", "content", "source", "note", "created_at")}

    @app.get("/api/web/sources")
    def web_sources(limit: int = 100, user=Depends(current_user)):
        return st.db.query("SELECT * FROM web_sources WHERE url IS NOT NULL ORDER BY id DESC LIMIT ?", (max(1, min(limit, 500)),))

    @app.get("/api/tool-calls")
    def tool_calls(context: str | None = None, limit: int = 100, user=Depends(current_user)):
        limit = max(1, min(limit, 500))
        if context:
            return st.db.query("SELECT * FROM tool_calls WHERE context=? ORDER BY id DESC LIMIT ?", (context, limit))
        return st.db.query("SELECT * FROM tool_calls ORDER BY id DESC LIMIT ?", (limit,))

    @app.post("/api/system/check-providers")
    async def check_providers(user=Depends(current_user)):
        """Ücretsiz: token harcamadan anahtar/model erişimi kontrolü."""
        return {"results": await st.router.check_providers(), "usd_try_rate_set": bool(st.settings.usd_try_rate)}

    @app.get("/api/system/live-tests")
    def live_tests(user=Depends(current_user)):
        from .livetest import list_reports
        return list_reports(st.settings)

    @app.post("/api/system/live-test")
    async def live_test(body: LiveTestIn, user=Depends(current_user)):
        """ÜCRETLİ: gerçek API ile canlı test. Kullanıcının açık onay metni zorunlu."""
        if body.confirm.strip() != "CANLI TEST":
            raise HTTPException(400, "Onay metni hatalı. Ücretli canlı test için 'CANLI TEST' yaz.")
        from .livetest import run_live
        log_activity(st.db, "live_test", f"Canlı API testi {user['username']} tarafından başlatıldı")
        return await run_live(st.settings, st.db, st.router)

    @app.post("/api/system/backup")
    async def backup_now(user=Depends(current_user)):
        dest = await asyncio.to_thread(make_backup, st)
        return {"ok": True, "file": dest.name}

    # ---------------- statik ----------------
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/manifest.webmanifest")
    def manifest():
        return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")

    return app
