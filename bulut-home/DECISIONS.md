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
