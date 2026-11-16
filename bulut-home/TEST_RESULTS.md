# Test Sonuçları

## 2026-11-16 — Oturum 2: bağımsız denetim

### Oturum 1'deki 39 test gerçekte neyi doğruluyordu?

| Grup | Test sayısı | Ne doğrulanıyor | Ne doğrulanMIyor |
|---|---|---|---|
| `fake_llm` (FakeProvider) | 22 | Sohbet akışı, geçmişin modele gönderilmesi, işaret ayrıştırma, katman seçimi, yönlendiricinin yedek zinciri, bütçe/çağrı sınırı mantığı, görev kuyruğu, plan → alt görev | **Gerçek model davranışı ve gerçek API yanıtları.** Sahte sağlayıcı ne istenirse onu döndürür. |
| `sdk_http` (gerçek `anthropic` SDK / httpx2 + MockTransport) | 4 | SDK'nın kabul ettiği parametreler, gönderilen JSON gövdesi, beta başlığı, hata eşleme, yanıt ayrıştırma | Anthropic sunucusunun bu isteği gerçekten kabul ettiği (yanıtları elle yazdık) |
| `no_llm` | 13 | Kimlik doğrulama, CSRF, giriş sınırı, hafıza CRUD/FTS, onay mekanizması, yedek, fiyat hesabı | — |
| Gerçek API (`live`) | **0** | — | Hiçbir gerçek API çağrısı yapılmadı |

Sonuç: "sohbet çalışıyor" iddiası, gerçek modele karşı değil sahte sağlayıcıya karşı doğrulanmıştı. Gerçek API entegrasyonu hâlâ doğrulanmadı (anahtar yok, ücretli çağrı izinsiz yapılmadı). Bunun için `tests/live/` eklendi; varsayılan olarak atlanır.

Test işaretleri artık `pytest.ini` içinde tanımlı: `python -m pytest -m fake_llm | sdk_http | no_llm | live`.

### Denetimde bulunan ve düzeltilen sorunlar

| # | Alan | Sorun | Önem | Düzeltme | Test |
|---|---|---|---|---|---|
| 1 | Bütçe | Eşzamanlı iki istek bütçe kontrolünü aynı anda geçip sınırı birlikte aşabiliyordu | Yüksek | Uçuştaki çağrıların en kötü durum maliyeti ayrılıyor (`_reserve/_release`) | `test_concurrent_calls_cannot_jointly_exceed_budget`, `test_reservation_released_on_provider_error` |
| 2 | Bütçe | `fallbacks:"default"` hangi modele gideceği belirsizdi; yedek model (ör. Opus) daha pahalı olabilir, maliyet asıl modelin fiyatıyla kaydediliyordu | Yüksek | Sabit yedek model (`claude-sonnet-5-5→claude-sonnet-5`, `claude-opus-5-5→claude-opus-4-8`); ön kontrol iki çağrıyı da sayıyor; maliyet `usage.iterations` üzerinden her adımın kendi fiyatıyla | `test_worst_case_includes_refusal_fallback`, `test_cost_uses_each_iteration_model`, `test_fallback_iterations_are_parsed` |
| 3 | Bütçe | En kötü durum hesabı önbelleğe yazma primini (1.25x) saymıyordu | Orta | `worst_case_usd` | `test_worst_case_counts_cache_write_premium` |
| 4 | Bütçe | Haiku 5.5'in 100K token üstü fiyat kademesi yoktu (20 mesaj × 20K karakter ≈ 130K token mümkün) | Orta | `Price.long_threshold/long` | `test_haiku_long_prompt_tier` |
| 5 | Veritabanı | `db.tx()` iç içe çağrılırsa ("cannot start a transaction within a transaction") çöküyordu; araç sistemi bunu tetikleyecekti | Orta | SAVEPOINT ile yeniden girilebilir işlem | `test_nested_transactions_use_savepoints`, `test_inner_rollback_keeps_outer` |
| 6 | Onaylar | Onaylanan işlemin yürütücüsü hata verirse istisna API'ye 500 olarak sızıyor, hata kaydı kalmıyordu | Düşük | Hata yakalanıp aktiviteye `approval_failed` olarak yazılıyor | `test_failing_executor_is_reported` |
| 7 | Docker | TLS denetimli vekil sunucu arkasında `pip` derlemesi başarısız | Ortam | İsteğe bağlı `--secret id=ca_bundle` desteği | Gerçek derleme |

İncelenip sorun bulunmayanlar: parola özeti (scrypt), oturum token'ının yalnızca HMAC özetinin saklanması, SQL'e yalnızca beyaz listeli alan adlarının girmesi, CSP, kurulum kodunun tek kullanımlık olması, `.env`/`data/` Git dışı.

Bilinen ve kabul edilen sınırlar: Docker/Tailscale arkasında tüm istemciler aynı IP'den görünür; giriş sınırı o yüzden fiilen küreseldir (tailnet içinden biri sahibini 15 dk kilitleyebilir). Tek kullanıcılı tailnet için kabul edildi.

### Docker — gerçek derleme ve çalıştırma (bu oturumda yapıldı)

Ortam: Docker 29.9.2 (`dockerd` elle başlatıldı), cgroup v1, overlayfs. Bu Debian 13 / ASUS değil.

| Adım | Sonuç |
|---|---|
| `docker build` (ilk deneme) | **Başarısız** — ortamın HTTPS vekil sunucusu kendinden imzalı CA kullanıyor, pip doğrulayamadı |
| `docker build --secret id=ca_bundle,src=...` | **Başarılı**, imaj 243 MB (`python:3.13-slim-trixie`) |
| `docker compose up -d` | Başarılı; `restart=unless-stopped`, `mem_limit=512m` uygulandı |
| `/api/health` | 200 |
| HEALTHCHECK | `healthy` |
| Kurulum kodu kayıtlarda, kurulum → oturum | Başarılı; kurulum kodu dosyası kurulumdan sonra silindi |
| Anahtarsız sohbet | 503 + açık Türkçe hata (sahte yanıt yok) |
| Hafıza kaydı → `docker compose restart` → hâlâ var | Başarılı (kalıcı volume) |
| Süreç kullanıcısı | `uid=1000(bulut)`, root değil |
| Bellek | ≈34 MiB / 512 MiB (boşta) |
| Yerel ağ IP'sinden erişim | Erişilemez (yalnızca 127.0.0.1'e bağlı — beklenen) |


## 2026-11-16 — Oturum 1

Ortam: Linux 6.18 konteyneri (Debian/ASUS değil), Python 3.13, FastAPI 0.163.1, anthropic 2.8.0, SQLite 3.53.1, Chromium (Playwright).

| Test | Sonuç |
|---|---|
| `python -m pytest -q tests` (auth, sohbet, router/bütçe, görev kuyruğu, hafıza, onaylar, Anthropic istek biçimi) | **39 geçti, 0 başarısız** |
| `python tests/e2e_ui.py` — 390×844 telefon ve 1280×800 masaüstü: kurulum, giriş, sohbet, işaret ayrıştırma, 8 bölümün tamamı, görev ekleme, hafıza, proje silme → onay → red, geçmiş yükleme, yatay taşma yok, konsol hatası yok | **E2E OK** |
| Gerçek sunucu duman testi (`uvicorn app.main:create_app --factory`, API anahtarı olmadan): health 200, kurulum 200, sohbet → 503 "sağlayıcı yapılandırılmamış" mesajı | **Beklendiği gibi** |
| Bellek: test sırasında BULUT süreci RSS ≈ 100 MB | Ölçüldü |

### Test edilmeyenler
- Gerçek model API çağrısı (anahtar yok). Model katmanı testlerde sahte sağlayıcı kullanıyor; Anthropic istek biçimi SDK + sahte HTTP katmanıyla doğrulandı.
- `docker build` / `docker compose up` (Docker daemon yoktu).
- Debian 13 / ASUS donanımı, Tailscale Serve, iPhone Safari'de ses.
