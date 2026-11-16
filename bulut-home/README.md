# BULUT HOME

Kişisel, tek sahipli yapay zekâ asistanı. Hedef cihaz: ASUS VivoBook X415JA (i3-1005G1, 8 GB RAM), Debian 13, 7/24 açık.

Şu an çalışanlar (v0.2.0): modelin gerçek araç kullanımı (hafıza, görevler, projeler, günlük özet, web araması/okuma), günlük brifing (zamanlanmış, model yoksa veri özeti), sohbet (kalıcı geçmiş), sağlayıcı bağımsız model katmanı, aylık TL bütçe koruması ve maliyet kaydı, uzun dönem hafıza (görüntüle/düzelt/sil), kalıcı görev kuyruğu ve arka plan işçisi, hedefi alt görevlere ayırma, onay merkezi (kodda zorunlu), aktivite akışı, günlük rapor grafikleri, sistem durumu, otomatik günlük veritabanı yedeği, tarayıcı tabanlı bas-konuş/sesli okuma. Ayrıntı: `PROGRESS.md`.

## Hızlı başlangıç (Debian 13, Docker)

```bash
sudo apt install -y docker.io docker-compose   # Debian 13 depo paketleri; ya da Docker'ın resmi deposu
git clone <bu depo> && cd the-erinc/bulut-home
cp .env.example .env
nano .env        # ANTHROPIC_API_KEY, BULUT_USD_TRY_RATE (güncel kur), BULUT_MONTHLY_BUDGET_TRY
mkdir -p data && sudo chown 1000:1000 data
docker compose up -d --build
docker compose logs bulut | grep "kurulum kodu"   # ilk kurulum kodu
```

Tarayıcıda `http://127.0.0.1:8080` → kullanıcı adı + parola (en az 10 karakter) + kurulum kodu. Kod tek kullanımlıktır.

> Docker imajı oturum 2'de gerçekten derlendi ve çalıştırıldı (bkz. `TEST_RESULTS.md`). TLS denetimli bir vekil sunucu arkasındaysan: `docker build --secret id=ca_bundle,src=/yol/ca.crt -t bulut-home:latest .`

## Telefondan / Windows'tan güvenli erişim: Tailscale

Servis yalnızca `127.0.0.1:8080`'e bağlanır; internete açılmaz. Tailnet içinden HTTPS ile yayınla:

```bash
sudo tailscale up
sudo tailscale serve --bg 8080        # https://<makine-adı>.<tailnet>.ts.net
```

Ardından `.env` içinde `BULUT_COOKIE_SECURE=1` yapıp `docker compose up -d`. iPhone'da Safari → Paylaş → "Ana Ekrana Ekle" ile uygulama gibi açılır.

## Docker'sız çalıştırma (Windows'ta geliştirme dahil)

```bash
cd bulut-home
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                              # düzenle
uvicorn app.main:create_app --factory --port 8080
```

## Yönetim

```bash
docker compose exec bulut python -m app.cli set-password umut   # parola sıfırla (tüm oturumlar düşer)
docker compose exec bulut python -m app.cli backup              # elle yedek
```

Yedekler `data/backups/` altında; günde bir otomatik alınır, en yeni 7 tanesi tutulur.

## Testler

```bash
pip install -r requirements-dev.txt
python -m pytest -q tests          # birim + API testleri (ağ çağrısı yok)
python -m pytest -m fake_llm       # yalnızca sahte model sağlayıcılı testler (gerçek API'yi doğrulamaz)
python -m pytest -m sdk_http       # gerçek SDK + sahte HTTP (istek biçimi)
BULUT_LIVE_TESTS=1 python -m pytest -m live tests/live   # GERÇEK ücretli API (birkaç kuruş), anahtar gerekir
python tests/e2e_ui.py             # tarayıcı testi: Node + Playwright gerekir
```

## Web araştırması ve günlük brifing

- Arama için `.env`'de `BRAVE_API_KEY` (Brave Search API) **veya** `SEARXNG_URL` (kendi SearXNG sunucun, JSON çıktısı açık) ayarla. İkisi de yoksa model web araması aracını görmez; sayfa okuma (`web_fetch`) yine çalışır.
- Web istekleri yerel ağa / tailnet'e gidemez (SSRF koruması). Günlük arama sınırı: `BULUT_WEB_DAILY_LIMIT`.
- Günlük brifing her gün `BULUT_BRIEF_TIME` (varsayılan 08:30, `BULUT_TIMEZONE`) saatinde hazırlanır; Raporlar sayfasından elle de oluşturulabilir. Model yoksa veya bütçe doluysa gerçek verilerden düz rapor üretilir.

## Model ve bütçe

- Varsayılan: basit işler `claude-haiku-5-5`, karmaşık işler `claude-sonnet-5-5`. `.env`'den değiştirilebilir (`sağlayıcı:model`).
- İkinci sağlayıcı: OpenAI uyumlu herhangi bir API (DeepSeek, OpenRouter, Groq…) `OPENAI_COMPAT_*` ile. Fiyatını girmezsen bütçe korunamayacağı için o sağlayıcı ücretli çağrıda kullanılmaz.
- Her çağrıdan önce en kötü durum maliyeti hesaplanır; aylık sınırı aşacaksa çağrı **yapılmaz**. Kur girilmemişse de ücretli çağrılar kapalıdır.
- Saatte en fazla 120 model çağrısı (döngü koruması).
- Fiyat tablosu `app/llm/pricing.py` içindedir, tarihi yazılıdır, canlı doğrulanmaz.

Kapsam dışı: borsa botu. Aynı cihazda ayrı bir Docker servisi olarak çalışabilir; BULUT'un görev/agent sistemine bağlı değildir.
