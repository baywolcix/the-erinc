# Sıradaki adımlar (öncelik sırasıyla)

## Oturum 3 sonrası
1. **ASUS'ta ilk kurulum** — `INSTALL_DEBIAN.md`. Sonuçları (paket kurulumu, derleme, `app.cli check`, `app.cli live-test`, test bildirimi) `TEST_RESULTS.md`'ye yaz.
2. Canlı testte araç kullanmayan/yanlış kullanan senaryo olursa persona/araç açıklamalarını gerçek model davranışına göre ayarla.
3. Web Push (iOS 16.4+ ana ekran PWA) — isteğe bağlı, ntfy yeterliyse gerekmez.
4. SearXNG'yi compose'a isteğe bağlı servis olarak ekleme (RAM ölçümüyle).
5. Ana PC ajanı (Faz 4), Yan Daire Git/PROGRESS.md okuma.

## Eski liste

1. **Canlıya alma (kullanıcı):** ASUS'a Debian 13 + Docker + Tailscale; `.env` doldur; `docker compose up -d --build`; ilk kurulum. Sonucu `TEST_RESULTS.md`'ye yaz.
0. **İlk canlı doğrulama (kullanıcı, ücretli ama çok küçük):** `.env`'e anahtar → `BULUT_LIVE_TESTS=1 python -m pytest -m live tests/live` (3 kısa Haiku çağrısı, < 0.01 USD). Sonra arayüzde "Bugün ne yaptık?" ile araç zincirini dene.
2. **Bildirimler:** Web Push (VAPID, ücretsiz) veya ntfy/Telegram — önemli olaylar (görev başarısız, onay bekleniyor, bütçe %80) anlık; günlük rapor.
3. ~~Günlük brifing~~ ✓ (oturum 2). Kalan: brifingi bildirim olarak gönderme, sesli brifing için sunucu tarafı TTS değerlendirmesi.
4. ~~Agent araçları~~ ✓ (oturum 2). Kalan: araç çağrılarını arayüzde konuşma içinde ayrıntılı gösterme; genel zamanlanmış görevler (`schedules` tablosu: "her pazartesi ilanları tara").
5. ~~Web araştırması~~ ✓ (oturum 2). Kalan: SearXNG'yi compose'a isteğe bağlı servis olarak ekleme (RAM ölçümüyle), web kaynaklarını arayüzde listeleme.
6. **Yan Daire entegrasyonu:** yetki verilmiş yerel klasörden `git status/log` ve `PROGRESS.md` okuma (salt okunur başlangıç).
7. **Ana PC ajanı:** Windows'ta küçük bir Python servisi; Tailscale üzerinden BULUT'a kalp atışı + iş çekme (pull) modeli; `kind='pc:*'` görevleri yalnızca PC çevrimiçiyken.
8. **İş fırsatları modülü:** portföy/yetenek profili hafızadan; ilan kaydı tablosu; teklif taslağı `llm` görevi; otomatik toplu mesaj YOK.
9. Bağlam yönetimi: uzun konuşmalarda özetleme; hafıza güven düzeyi azalması.
