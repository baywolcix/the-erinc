# İlerleme

## Oturum 1 — 2026-11-16

Faz 1 tamamlandı, Faz 2'nin çoğu yapıldı.

### Çalışan ve test edilenler
- [x] Proje iskeleti (`bulut-home/`), `.env.example`, `.gitignore` (gizli anahtar/veri Git dışı)
- [x] SQLite şeması (WAL, FTS5), varsayılan projeler: Yan Daire, Mağaranın Dışı, İş ve Gelir
- [x] Kimlik doğrulama: tek seferlik kurulum kodu, scrypt, oturum, çıkış, hatalı giriş sınırı, CSRF başlığı
- [x] Model katmanı: Anthropic SDK + OpenAI uyumlu; katman seçimi; yedek zinciri; hata kaydı
- [x] Bütçe: aylık TL sınırı, kur/fiyat yoksa engel, en kötü durum ön kontrolü, saatlik çağrı sınırı, `llm_calls` maliyet kaydı
- [x] Sohbet: kalıcı geçmiş, konuşma listesi, silme, kısa + uzun dönem bağlam
- [x] Hafıza: ekle/ara/düzelt/sabitle/sil, kaynak-tarih-güven alanları, sohbetten otomatik kayıt
- [x] Görevler: kalıcı kuyruk, dedupe, atomik sahiplenme, yeniden deneme, hata kaydı, yeniden başlatma kurtarması, `llm` ve `plan` (alt görev) yürütücüleri, sohbetten görev
- [x] Onay Merkezi: kritik işlem türleri, kodda zorunlu, tek seferlik yürütme; proje silme / toplu hafıza silme / pahalı görev bağlı
- [x] Aktivite akışı, günlük rapor (maliyet + görev grafikleri), sistem sayfası (RAM, disk, bütçe, sağlayıcılar)
- [x] Günlük otomatik yedek + elle yedek
- [x] Mobil öncelikli koyu arayüz (8 bölüm), PWA manifesti, bas-konuş + sesli okuma (tarayıcı API'si)
- [x] Dockerfile + docker-compose (512 MB sınır, yalnızca localhost)

### Doğrulanmamış / yarım
- [ ] Gerçek Anthropic/DeepSeek API'siyle canlı çağrı yapılmadı (anahtar yok). İstek biçimi sahte HTTP katmanıyla SDK üzerinden doğrulandı.
- [ ] Debian 13 / ASUS üzerinde çalıştırılmadı; geliştirme ortamı Linux (kernel 6.18) konteyneriydi
- [ ] iPhone Safari'de bas-konuş denenmedi (Safari'nin Web Speech desteği kısmi)
- [ ] Bildirimler (anlık/push) yok — Faz 3
- [ ] Web araştırması, tarayıcı otomasyonu, Git/PROGRESS.md okuma, ana PC bağlantısı yok — Faz 3/4

## Oturum 2 — 2026-11-16

### Denetim ve düzeltmeler
- [x] 39 testin neyi doğruladığı sınıflandırıldı (`pytest.ini` işaretleri: fake_llm / sdk_http / no_llm / live). Ayrıntı: `TEST_RESULTS.md`
- [x] Bütçe: eşzamanlı istek rezervasyonu, sabit reddetme yedeği + iki çağrılık en kötü durum, önbelleğe yazma primi, Haiku uzun istem kademesi, adım bazlı maliyet
- [x] Veritabanı: iç içe işlemler (SAVEPOINT)
- [x] Onaylar: yürütücü hatası kaydı
- [x] Docker imajı gerçekten derlendi ve çalıştırıldı (kalıcılık, healthcheck, uid 1000, 512 MB sınırı doğrulandı)
- [x] Opt-in canlı API testleri (`tests/live/`, varsayılan atlanır)

### Faz 2 — tamamlananlar (oturum 2)
- [x] **Gerçek araç kullanımı (tool use):** `app/tools.py` + `app/agent.py`. Model 12 araç kullanabiliyor: search_memory, save_memory, update_memory, delete_memory (yalnızca onay ister), list_tasks, get_task, create_task, update_task_status, list_projects, daily_summary, web_search, web_fetch
  - Girdiler kodda doğrulanır; araç hatası modele `is_error` ile döner, sohbet çökmez
  - Her çağrı `tool_calls` tablosuna + aktiviteye yazılır; `/api/tool-calls`
  - Döngü sınırları: yanıt başına 6 model adımı, 12 araç çağrısı; döngü boyunca aynı model (thinking blokları modele bağlı)
  - Arka plan `llm` görevleri daraltılmış araç seti kullanır (görev oluşturamaz/kapatamaz/silme isteyemez)
  - OpenAI uyumlu sağlayıcı için tool_calls dönüşümü
  - Eski `[[HATIRLA]]/[[GOREV]]` işaretleri geri uyumluluk için hâlâ ayrıştırılıyor
- [x] **Web araştırması:** `app/web.py` — Brave Search API veya SearXNG ile arama; sayfa okuma (SSRF koruması, yönlendirme denetimi, 2 MB / 15 sn sınırı, yalnızca metin); sonuçlar "güvenilmeyen veri" etiketli; kaynaklar `web_sources` tablosunda (adres, başlık, tarih, bağlam); günlük arama sınırı
- [x] **Günlük brifing:** `app/briefing.py` — gerçek kayıtlardan veri; model varsa kısa metin, yoksa deterministik rapor; her gün `BULUT_BRIEF_TIME`'da (varsayılan 08:30 İstanbul) zamanlayıcı görevi; Raporlar'da kart + "Şimdi oluştur" + "Sesli dinle"
- [x] Şema v2 göçü (mevcut veritabanında test edildi)

### Doğrulanmamış / yarım (oturum 2 sonu)
- [ ] Gerçek model API'si ile araç kullanımı (anahtar yok; istek biçimi SDK + sahte HTTP ile doğrulandı). İlk canlı deneme: `BULUT_LIVE_TESTS=1 python -m pytest -m live tests/live`
- [ ] Gerçek web erişimi (geliştirme ortamı ağı genel siteleri engelliyor)
- [ ] Üretim Dockerfile'ı ile yeni kodun temiz derlemesi (Docker Hub 429); doğrulama imajıyla çalıştırıldı
- [ ] Bildirimler (anlık) — sıradaki

## Oturum 3 — 2026-11-16: gerçek kullanıma hazırlık (v0.3.0)

- [x] **Güvenli anahtar kurulumu:** `scripts/configure.py` (sunucuda, stdlib; getpass, `.env` atomik + 600, değerleri asla basmaz), `app.cli check` (Models API, token harcamaz), arayüzde "Anahtarları kontrol et". Anahtarsız bölümler çalışmaya devam eder.
- [x] **Gizli değer maskeleme:** `app/redact.py` — aktivite, hata kayıtları, araç kayıtları, bildirimler ve Python logları; bilinen anahtar değerleri + desenler (sk-ant, Bearer, Telegram, ntfy).
- [x] **Kullanıcı başlatmalı canlı testler:** `app/livetest.py` — sohbet, hafıza arama (araç), görev oluşturma (araç). CLI `live-test` (onay sorar) veya arayüzde "CANLI TEST" onay metni. Geçici DB, maliyet ana bütçeye yazılır, sert tavan $0.05, rapor `data/live_tests/`. Sahte sağlayıcıyla `real_api: false`.
- [x] **Bildirimler:** `app/notify.py` — uygulama içi kutu + ntfy + Telegram; kalıcı teslim kuyruğu, 1/5/30 dk yeniden deneme, sessiz saat, en düşük seviye, ayrıntı gizleme, dedupe. Olaylar: görev başarısız/tamamlandı, onay bekliyor, bütçe %80/%100, brifing hazır. Aktivite sayfasında kutu + rozet, Sistem'de test bildirimi.
- [x] **Genel zamanlanmış görevler:** `app/schedules.py` — daily/weekly/monthly/every; slot başına tek çalışma (PK), yeniden başlatmaya dayanıklı, kaçırılanlar için tek telafi, önceki görev açıksa atlama; model ücretli zamanlama oluşturursa onaya kadar kapalı. Görevler sayfasında yönetim + önizleme; araçlar: create_schedule, list_schedules, disable_schedule.
- [x] **Debian betikleri:** `install-debian.sh`, `update.sh` (otomatik geri almalı), `rollback.sh` (`--restore-db`, `--db-only`), `backup.sh`, ortak `lib.sh`. Uçtan uca denendi (bkz. TEST_RESULTS).
- [x] **INSTALL_DEBIAN.md:** ASUS için adım adım.
- [x] **Docker:** üretim Dockerfile'ı ayna taban imajıyla gerçekten derlendi; `BASE_IMAGE` argümanı eklendi.
- [x] Şema v3 (notifications, notification_deliveries, schedules, schedule_runs).

### Doğrulanmamış (oturum 3 sonu)
- [ ] Gerçek API ile canlı test (anahtar gerekiyor) → ASUS'ta `app.cli live-test`
- [ ] Gerçek ntfy/Telegram teslimatı
- [ ] Debian 13 paket adları ve root olmayan kullanıcıyla betikler (ASUS'ta ilk kurulumda doğrulanacak)
