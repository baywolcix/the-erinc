# Test Sonuçları

## 2026-11-16 — Oturum 3: gerçek kullanıma hazırlık

### Gerçek API ile canlı test yapıldı mı? **HAYIR.**
Bu oturumda API anahtarı yoktu; ücretli hiçbir model çağrısı yapılmadı. `tests/live` (3 test) atlandı.
Gerçek API'ye yapılan tek istek ücretsizdi: **geçersiz** bir anahtarla Models API (`GET /v1/models/claude-haiku-5-5`) → Anthropic sunucusu **401** döndü, uygulama "Anahtar reddedildi (401)" dedi. Bu, gerçek HTTP yolunu, SDK sürümünü ve hata eşlemesini doğrular; **model yanıtını ve araç kullanımını doğrulamaz.**

### Otomatik testler
| Komut | Sonuç |
|---|---|
| `python -m pytest -q` | **142 geçti, 3 atlandı** (`live`) |
| `-m fake_llm` | 43 — model yanıtları senaryolu (FakeProvider). Gerçek model davranışını doğrulamaz. |
| `-m sdk_http` | 8 — gerçek SDK + sahte HTTP (Models API kontrolü dahil) |
| `-m no_llm` | 95 — bildirim kuyruğu/teslimat, zamanlamalar, maskeleme, .env sihirbazı, web, auth, DB |
| `-m live` | 3 atlandı (anahtar yok) |
| `python tests/e2e_ui.py` | **E2E OK** — bildirim kutusu, zamanlama önizleme/oluşturma, ücretsiz anahtar kontrolü, yanlış onay metniyle canlı testin reddi |
| `shellcheck -x scripts/*.sh` | Temiz |

Canlı test düzeneğinin kendisi sahte sağlayıcıyla test edildi ve raporun **`real_api: false`** yazdığı doğrulandı (`test_live_harness_with_fake_is_not_reported_as_real`) — sahte bir test gerçek API testi gibi raporlanamaz.

### Docker
| Adım | Sonuç |
|---|---|
| Üretim Dockerfile'ı, `docker.io/python` taban | **429** (Docker Hub hız sınırı) — ortam engeli |
| Üretim Dockerfile'ı, `--build-arg BASE_IMAGE=mirror.gcr.io/library/python:3.13-slim-trixie` (Google'ın resmi Docker Hub aynası) | **Başarılı** — iki kez (ara sürüm ve son kod) |
| Son imaj: compose ile başlatma, `/api/health` 0.3.0, kullanıcı `bulut` | Başarılı, RAM ≈43 MiB |
| Konteynerde `app.cli status / check / live-test --yes` (anahtarsız) | status doğru; check "anahtar ayarlı değil" (çıkış 1); live-test **"ÇALIŞTIRILMADI"** (çıkış 3) |
| Kayıtlarda anahtar araması | 0 eşleşme |

### Debian betikleri — gerçekten çalıştırıldı (bu ortamda, root olarak)
Geçici klon + sahte "uzak" depo ile uçtan uca:
| Senaryo | Sonuç |
|---|---|
| `install-debian.sh --skip-packages --non-interactive --force` | .env (600) + gizli anahtar üretimi, derleme, başlatma, sağlık, ilk kurulum kodu ✓ |
| `update.sh`, uzakta yerel commit çatışması | `--ff-only` reddetti, **hiçbir şey değişmedi** ✓ |
| `update.sh`, **bozuk** sürüm (main.py sözdizimi hatası) | Yedek → derleme → sağlık başarısız → **otomatik geri alma**: önceki kod + imaj, sürüm 0.3.0, veri korundu, çıkış 1 ✓ |
| `update.sh`, iyi sürüm | 0.3.0 → 0.3.1-test, veri korundu ✓ |
| `backup.sh` | Çevrimiçi yedek + bütünlük kontrolü ✓ |
| `rollback.sh --restore-db --yes` | Kod/imaj geri, veritabanı güncelleme öncesine döndü, mevcut hali `pre-restore-*.db` olarak saklandı ✓ |
| `rollback.sh --db-only <pre-restore>` | Saklanan duruma geri dönüldü (sonradan eklenen kayıt geri geldi) ✓ |

Testin yakaladığı hata: `docker exec -T` (bu bayrak yalnızca `docker compose exec`'te var) → yedek alınamıyordu; güncelleme güvenli şekilde **hiçbir şeyi değiştirmeden** durdu. Düzeltildi.

### Test EDİLEMEYENLER
- **Gerçek model çağrısı** (sohbet/hafıza/görev aracı) — anahtar yok.
- **Mobil bildirim teslimatı** (ntfy.sh / Telegram'a gerçek gönderim) — ağ politikası genel siteleri engelliyor; biçim sahte HTTP ile doğrulandı.
- **Debian 13 paket adları** (`docker.io`, `docker-compose`, `docker-buildx`) — `deb.debian.org` bu ortamda engelli (`connect_rejected`). Paket adları bilgiye dayalı; `docker-buildx` kurulamazsa betik açık uyarı veriyor.
- Betiklerin **root olmayan kullanıcıyla sudo üzerinden** çalışması (`require_root` yeniden başlatma, git'in depo sahibi olarak çalışması) — burada yalnızca root ile çalıştırıldı.
- Tailscale kurulumu/`serve`, ASUS donanımı, kapak kapalıyken çalışma.


## 2026-11-16 — Oturum 2 (devam): araç kullanımı, web araştırması, günlük brifing

| Komut | Sonuç |
|---|---|
| `python -m pytest -q` | **93 geçti, 3 atlandı** (atlananlar: `live` — gerçek ücretli API, anahtar yok) |
| `-m fake_llm` | 36 geçti — model yanıtları/araç çağrıları senaryolu; araçların kendisi (DB, onay, görev, brifing) gerçek kod |
| `-m sdk_http` | 7 geçti — gerçek `anthropic` SDK / httpx2, sahte HTTP: tool_use ↔ tool_result gidiş-dönüşü, **thinking bloklarının aynen geri gönderilmesi**, `tool_choice` gönderilmemesi, yedek model iterasyonları, OpenAI uyumlu tool_calls dönüşümü |
| `-m no_llm` | 51 geçti — web (SSRF, yönlendirme, boyut, arama ayrıştırma, günlük sınır), brifing veri toplama/zamanlayıcı, auth, DB, onaylar |
| `-m live` | 3 atlandı |
| `python tests/e2e_ui.py` (Chromium, telefon + masaüstü) | **E2E OK** — sohbette araç zinciri (daily_summary → create_task → save_memory) ve araç bilgisi, brifing kartı "Şimdi oluştur", 8 bölüm, konsol hatası yok |

(Bir test hem `no_llm` modülünde hem `fake_llm` işaretli olduğu için kategori toplamı 94.)

### Docker (yeni kodla)
- Üretim Dockerfile'ı ile yeniden derleme **Docker Hub 429 (hız sınırı)** nedeniyle bu oturumda tekrarlanamadı (taban imaj bildirimi alınamadı). Dış sınır; kod hatası değil.
- Doğrulama için `bulut-home:test` (aynı `requirements.txt` ile önceden derlenmiş) üzerine güncel `app/` kopyalanarak imaj oluşturuldu ve compose ile çalıştırıldı:
  - v0.1 veritabanı (v1 şema) üzerinde başlatıldı → şema **v2'ye geçti**, `tool_calls/web_sources/briefings` tabloları oluştu, eski hafıza korundu.
  - Zamanlayıcı yerel saat 08:30'u geçtiği için açılışta bugünün brifing görevini açtı; işçi model olmadan **deterministik brifing** üretti (not alanında nedeni yazıyor).
  - `/api/system` web ve brifing durumunu gösteriyor. RAM ≈36 MiB.
- Bu sırada bulunan hata: brifing kendi görevini "tamamlanan iş" olarak listeliyordu → düzeltildi (`test_brief_tasks_not_listed_as_work`).

### Gerçek ağ
- Web sayfası okuma ücretsiz olduğu için gerçek siteye denendi: bu geliştirme ortamının ağ politikası genel sitelere bağlantıyı reddediyor (`connect_rejected`), yerel DNS de yok. **Gerçek web erişimi bu ortamda doğrulanamadı.** SSRF koruması gerçek ortamda doğru şekilde çalıştı (169.254.169.254 ve localhost engellendi).
- Web araması (Brave/SearXNG) anahtar/servis gerektirdiği için denenmedi.

### Bu aşamada bulunan diğer hata
- HTTP User-Agent başlığında Türkçe karakter ("kişisel") vardı → tüm web istekleri `UnicodeEncodeError` ile çökecekti. Testler yakaladı, düzeltildi.


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
