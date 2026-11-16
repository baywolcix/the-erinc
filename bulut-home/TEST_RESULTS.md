# Test Sonuçları

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
