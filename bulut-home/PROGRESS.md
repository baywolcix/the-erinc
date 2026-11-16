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
