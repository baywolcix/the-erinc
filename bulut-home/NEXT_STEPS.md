# Sıradaki adımlar (öncelik sırasıyla)

1. **Canlıya alma (kullanıcı):** ASUS'a Debian 13 + Docker + Tailscale; `.env` doldur; `docker compose up -d --build`; ilk kurulum. Sonucu `TEST_RESULTS.md`'ye yaz.
2. **Bildirimler:** Web Push (VAPID, ücretsiz) veya ntfy/Telegram — önemli olaylar (görev başarısız, onay bekleniyor, bütçe %80) anlık; günlük rapor.
3. **Günlük brifing görevi:** zamanlanmış görev tablosu (`schedules`), her sabah raporu modelle kısa metne çevir (Haiku, düşük maliyet).
4. **Agent araçları (Faz 3):** model çağrısına tool use ekle — `create_task`, `search_memory`, `save_memory`, `list_tasks`; kritik araçlar yalnızca `approvals.request` üzerinden. İşaret (`[[...]]`) sistemini araçlarla değiştir.
5. **Web araştırması:** Anthropic sunucu tarafı `web_search_20260209`/`web_fetch_20260209` araçları (ücretli; bütçeye dahil) veya ücretsiz arama API'si; kaynak + tarih kaydı; web içeriği "güvenilmeyen veri" etiketli.
6. **Yan Daire entegrasyonu:** yetki verilmiş yerel klasörden `git status/log` ve `PROGRESS.md` okuma (salt okunur başlangıç).
7. **Ana PC ajanı:** Windows'ta küçük bir Python servisi; Tailscale üzerinden BULUT'a kalp atışı + iş çekme (pull) modeli; `kind='pc:*'` görevleri yalnızca PC çevrimiçiyken.
8. **İş fırsatları modülü:** portföy/yetenek profili hafızadan; ilan kaydı tablosu; teklif taslağı `llm` görevi; otomatik toplu mesaj YOK.
9. Bağlam yönetimi: uzun konuşmalarda özetleme; hafıza güven düzeyi azalması.
