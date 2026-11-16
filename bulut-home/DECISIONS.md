# Kararlar

| Tarih | Karar | Neden |
|---|---|---|
| 2026-11-16 | BULUT HOME, `baywolcix/the-erinc` deposunda `bulut-home/` alt klasörü olarak başladı | Oturumun erişebildiği tek depo buydu; mevcut oyun dosyalarına dokunulmadı. İleride ayrı depoya taşınabilir (klasör kendi içinde bağımsız). |
| 2026-11-16 | Python 3.13 + FastAPI + uvicorn, tek süreç | Düşük RAM (~100 MB RSS ölçüldü), asyncio ile arka plan işçisi aynı süreçte. Celery/Redis gibi ek servis yok. |
| 2026-11-16 | SQLite (WAL) + FTS5, vektör DB yok | 8 GB RAM; kişisel ölçekte tam metin arama yeterli. Gerekirse sonra `sqlite-vec` eklenebilir. |
| 2026-11-16 | Frontend derleme adımsız vanilla JS | Node derleme zinciri yok, Debian'da ek bağımlılık yok, CSP sıkı tutulabiliyor. |
| 2026-11-16 | Varsayılan modeller: `claude-haiku-5-5` (hızlı), `claude-sonnet-5-5` (akıllı) | Kullanıcı aylık 200–500 TL hedefi ve "basit işte ekonomik model" istedi. Haiku 5.5 tabloda $0.10/$0.50 per 1M (2026-11-03 önbellek listesi). Opus 5.5 (`claude-opus-5-5`) `.env`'den seçilebilir. |
| 2026-11-16 | Katman seçimi sezgisel (uzunluk + anahtar kelime), sınıflandırma için ek model çağrısı yok | Her mesajda ekstra maliyet ve gecikme olmasın. Kullanıcı arayüzden Hızlı/Akıllı seçebilir. |
| 2026-11-16 | Anthropic çağrılarında `output_config.effort` (hızlı: low, akıllı: medium); `temperature`/`thinking` gönderilmiyor | 5.5 modellerinde sampling parametreleri 400 verir; düşünme varsayılan uyarlanabilir. |
| 2026-11-16 | Sonnet/Opus 5.5 çağrılarında sunucu tarafı reddetme yedeği (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`) açık | Güvenlik sınıflandırıcısı yanlış pozitiflerinde yanıt kaybolmasın. Kapatmak istenirse `providers.py` `_FALLBACK_MODELS`. |
| 2026-11-16 | İkinci sağlayıcı OpenAI uyumlu genel istemci | Tek sağlayıcıya kilitlenmemek; DeepSeek/OpenRouter/Groq vb. aynı kodla. |
| 2026-11-16 | Bütçe TL cinsinden, kur elle girilir; kur veya fiyat yoksa ücretli çağrı yapılmaz | Canlı kur/fiyat doğrulanamıyor; tahmini veriyi kesin gibi kullanmamak. Güvenli taraf: engelle. |
| 2026-11-16 | Her çağrı öncesi en kötü durum (tahmini giriş + max_tokens) maliyet kontrolü | Sınırı aşmadan durdurmak için. |
| 2026-11-16 | Tek görevin tahmini maliyeti >5 TL ise `spend_money` onayı | Kodda zorunlu onay örneği; eşik `tasks.APPROVAL_THRESHOLD_TRY`. |
| 2026-11-16 | Kullanıcının arayüzden tek hafıza kaydı / konuşma silmesi onaysız; proje silme ve toplu hafıza silme onaylı | Spec: kullanıcı hafızayı silebilmeli. Toplu/önemli silmeler Onay Merkezi'nden. |
| 2026-11-16 | Otomatik yedek döndürme (son 7) onaysız | BULUT'un kendi ürettiği yedek dosyaları; kullanıcı verisi değil. |
| 2026-11-16 | Ses: tarayıcının Web Speech API'si (bas-konuş + sesli okuma) | Ücretsiz, sunucuda kaynak harcamaz. Not: Chrome konuşma tanımada sesi Google sunucularına gönderir. Whisper'lı yerel/ana PC çözümü Faz 4. |
| 2026-11-16 | Sohbetten hafıza/görev üretimi model çıktısındaki `[[HATIRLA]]`/`[[GOREV]]` işaretleriyle | Ek çağrı yok. Model yalnızca güvenli işlemleri (hafıza notu, elle görev) önerebilir; kritik işlem tetikleyemez. |
| 2026-11-16 | Reddetme yedeği `"default"` yerine sabit model (`sonnet-5-5→sonnet-5`, `opus-5-5→opus-4-8`) | Bütçe ön kontrolü yedek modelin fiyatını bilmeli; maliyet `usage.iterations` ile adım adım hesaplanıyor. |
| 2026-11-16 | Eşzamanlı çağrılar için bellek içi bütçe rezervasyonu | Tek süreç olduğu için yeterli; çok süreçli yapıya geçilirse DB tabanlı rezervasyon gerekir. |
| 2026-11-16 | Araç kullanımı manuel döngüyle (SDK tool runner değil) | Onay kapısı, girdi doğrulama, kayıt ve OpenAI uyumlu sağlayıcı desteği bizim kodumuzda kalsın. |
| 2026-11-16 | `tool_choice` gönderilmiyor (otomatik), `strict` kullanılmıyor | 5.5 modellerinde zorlanmış araç seçimi 400 veriyor; girdiler zaten kodda doğrulanıyor. |
| 2026-11-16 | Araç döngüsünde rota sabit | Thinking blokları modele bağlı; döngü ortasında başka sağlayıcıya atlamak biçim/doğrulama hatası doğurur. Hata olursa yanıt başarısız sayılır. |
| 2026-11-16 | Arka plan görevlerinin araç seti daraltıldı | Görevlerin kendiliğinden görev üretip çoğalmasını (agent döngüsü) engellemek. |
| 2026-11-16 | Web araması: Brave API veya kendi SearXNG; Anthropic sunucu tarafı web_search şimdilik kullanılmadı | Sağlayıcıdan bağımsız kalmak ve maliyeti ayrı izlemek. Anthropic aracı ücretli ve yalnızca Claude ile çalışır; sonra seçenek olarak eklenebilir. |
| 2026-11-16 | Web isteklerinde SSRF koruması: yalnızca küresel IP'ler, yerel ağ adları engelli, her yönlendirme yeniden denetlenir | BULUT ev ağında ve tailnet'te çalışıyor; model/web içeriği iç servislere istek attıramamalı. Bilinen sınır: DNS rebinding penceresi. |
| 2026-11-16 | Brifing verisi deterministik, model yalnızca metne çeviriyor | Uydurma iş/sayı olmasın; model yoksa da brifing üretilsin. Günde bir deneme (başarısız olsa bile tekrar açılmaz). |
| 2026-11-16 | Anahtarlar yalnızca sunucuda `scripts/configure.py` ile `.env`'e; arayüzden anahtar girişi yok | Web üzerinden gizli değer taşımak ve DB'de saklamak saldırı yüzeyini büyütür. Arayüz yalnızca "ayarlı mı / geçerli mi" gösterir. |
| 2026-11-16 | Anahtar doğrulama Models API ile | Token harcamaz; anahtar + model erişimi doğrulanır. |
| 2026-11-16 | Canlı testler geçici DB'de, maliyet ana bütçeye kopyalanır, $0.05 tavan, açık onay metni | Gerçek veriyi kirletmeden, bütçeyi atlamadan, kazara tetiklenmeden. |
| 2026-11-16 | Mobil bildirim: ntfy + Telegram (Web Push şimdilik yok) | Web Push için VAPID şifreleme kütüphanesi (cryptography) ve iOS'ta ana ekrana eklenmiş PWA gerekir; ntfy/Telegram tek HTTP isteği, ek bağımlılık yok, iPhone uygulaması var. Web Push sonra eklenebilir. |
| 2026-11-16 | Bildirim teslimi DB kuyruğundan (outbox) | Yeniden başlatmada kaybolmasın, geçici ağ hatası yeniden denensin. |
| 2026-11-16 | Zamanlama biçimi sade (daily/weekly/monthly/every), cron değil | Hem kullanıcı hem model için anlaşılır; yanlış yazımı ayrıştırıcı reddeder. |
| 2026-11-16 | Zamanlama: slot PK + "önceki görev açıksa atla" + kaçırılanlar için tek telafi | Çift çalışma, yığılma ve açılışta görev seli olmasın. |
| 2026-11-16 | Modelin oluşturduğu ücretli zamanlama onaya kadar kapalı; sahibinin arayüzden oluşturduğu doğrudan açık | Tekrarlayan harcama "para harcama" sayılır; sahibinin açık eylemi zaten onaydır. |
| 2026-11-16 | `update.sh` başarısızlıkta kodu ve imajı otomatik geri alır ama veritabanını almaz | Göçler eklemeli; otomatik DB geri yükleme aradaki veriyi siler. DB geri yükleme açık komutla ve önce güvenlik kopyası alınarak. |
| 2026-11-16 | Dockerfile `ARG BASE_IMAGE` | Docker Hub 429'da resmi ayna (mirror.gcr.io) kullanılabilsin; varsayılan değişmedi. |
