# Mimari (v0.2.0)

```
iPhone / Windows tarayıcı ──HTTPS (Tailscale Serve)──► 127.0.0.1:8080
                                                         │
                         ┌───────────────── bulut-home konteyneri (≤512 MB) ─────────────────┐
                         │ FastAPI (uvicorn, 1 işçi süreci)                                   │
                         │  ├─ /api/auth      scrypt parola, sunucu tarafı oturum, giriş sınırı│
                         │  ├─ /api/chat      chat.py → persona + hafıza + görev özeti        │
                         │  ├─ /api/tasks     tasks.py  (kuyruk + TaskWorker asyncio döngüsü)  │
                         │  ├─ /api/memories  memory.py (SQLite FTS5)                        │
                         │  ├─ /api/approvals approvals.py (kritik işlem kapısı)              │
                         │  ├─ /api/activity /reports /system /projects                      │
                         │  └─ /static        bağımlılıksız SPA (HTML/CSS/JS)                 │
                         │ llm/router.py ─► AnthropicProvider (resmi SDK)                     │
                         │               └► OpenAICompatProvider (httpx2)                     │
                         │ SQLite WAL  /data/bulut.db   + /data/backups/                     │
                         └────────────────────────────────────────────────────────────────────┘
```

## Modüller (`app/`)

| Dosya | Görev |
|---|---|
| `config.py` | Ortam değişkenleri, basit `.env` okuyucu, kalıcı oturum anahtarı |
| `db.py` | Şema, WAL, tek yazar kilidi, başlangıçta kilitli görev kurtarma, yedek, `log_activity` |
| `auth.py` | Tek sahip, scrypt, HMAC'li oturum token özeti, 15 dk/8 hatalı giriş sınırı |
| `llm/pricing.py` | USD/1M token tablo (tarihli), maliyet hesabı |
| `llm/providers.py` | Sağlayıcı arayüzü; Anthropic (Haiku/Sonnet 5.5, `effort`, sunucu tarafı refusal fallback) ve OpenAI uyumlu |
| `llm/router.py` | Katman seçimi (hızlı/akıllı), yedek zinciri, bütçe ön kontrolü, saatlik çağrı sınırı, `llm_calls` kaydı |
| `persona.py` | Jarvis benzeri Türkçe kişilik + sınırlar; hafıza/görevler "veri" olarak etiketli |
| `chat.py` | Kısa dönem: son 20 mesaj. Uzun dönem: sabit + FTS eşleşen hafızalar. `[[HATIRLA]]`/`[[GOREV]]` işaretlerini ayrıştırır |
| `memory.py` | Hafıza CRUD, Türkçe ek toleranslı önek araması, kopya birleştirme |
| `tasks.py` | Görev CRUD, dedupe, atomik sahiplenme, yeniden deneme (30s·2ⁿ), onaya düşürme (>5 TL), `plan` → alt görevler |
| `approvals.py` | Kritik işlem türleri, kayıtlı yürütücüler, tek seferlik yürütme |
| `sysinfo.py` | /proc tabanlı RAM/yük/disk (psutil yok) |
| `main.py` | HTTP katmanı, güvenlik başlıkları/CSP, CSRF başlığı, günlük yedek döngüsü |
| `cli.py` | Parola ayarlama, elle yedek |
| `tools.py` | Araç kayıt defteri: şema + kodda girdi doğrulama + kayıt; kritik araçlar yalnızca onay açar; bağlama göre araç setleri (`CHAT_TOOLS`, `TASK_TOOLS`) |
| `agent.py` | Manuel araç döngüsü: model → tool_use → araç → tool_result (tek mesajda) → model; 6 adım / 12 araç sınırı; rota sabitleme |
| `web.py` | Arama (Brave/SearXNG) + sayfa okuma; SSRF koruması, yönlendirme denetimi, boyut/süre sınırı, güvenilmeyen içerik sarmalama, `web_sources` kaydı |
| `briefing.py` | Günlük brifing: veri toplama (son 24 saat), deterministik metin, isteğe bağlı model özeti, günlük zamanlayıcı |

## Veri modeli

`users, sessions, login_attempts, projects, conversations, messages, llm_calls, memories (+memories_fts), tasks, approvals, activity, meta` + v2: `tool_calls, web_sources, briefings`.

Sohbet akışı: `chat.reply` → bağlam (son 20 mesaj + hafıza + görev özeti) → `agent.run` (araçlar) → son metin `messages`'a; araç çağrıları `tool_calls`'a.

Görev durumları: `pending → running → done | failed`, `pending → waiting_approval → pending | cancelled`, elle `cancelled/done/pending`.

## Güvenlik katmanları

1. Ağ: yalnızca localhost + Tailscale.
2. Kimlik: tek sahip, oturum çerezi `HttpOnly; SameSite=Strict` (+`Secure` HTTPS'te).
3. Durum değiştiren her `/api` isteğinde `X-Bulut: 1` başlığı zorunlu.
4. CSP `default-src 'self'`, satır içi betik yok.
5. Kritik işlemler `approvals.request()` dışında yürütülemez; `execute()` yalnızca `approved` kaydı bir kez çalıştırır.
6. Bütçe ve çağrı hızı sınırları router'da, model isteminden bağımsız; eşzamanlı çağrılar en kötü durum tutarını ayırır.
8. Model yalnızca kayıtlı araçları çağırabilir; kritik etkili araçlar onay kaydı açar. Web içeriği `<web_icerik>` içinde güvenilmeyen veri olarak verilir; yerel/özel ağ adreslerine istek atılamaz.
7. Gizli anahtarlar yalnızca ortamda; `data/` ve `.env` Git'e girmez.
