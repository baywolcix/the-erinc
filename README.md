# THE ERİNÇ Online v1.3

v1.2 üzerine kuruludur. Yeni özellikler:

- `Ahmet` (tam bu yazım): başlangıç 2.565 kütle (normal 65 + 2.500).
- `erenbakireymis`: bu isimli oyuncu oyundayken herkesin arka planı karanlık olur. Bu oyuncunun toplam kütlesi 1.500'e ulaşınca herkese `EREN PATLADI — PATLAK EREN` final ekranı gönderilir. Sunucu 9 saniyelik ara verir, sonra yeni maç başlar. Final ekranını gören oyuncular yeni tur için sayfayı yenileyebilir.
- Suçlu etkinliği: rastgele bir oyuncu 10 saniye boyunca suçlu olur; bu sürede daha küçük rakipler de suçluyu yiyebilir. Her 30–45 saniyede bir, önce ilk etkinlik 18 saniyede.
- v1.2 özellikleri korunur.

## GitHub / Render

ZIP'i açın. İçindeki `server.js`, `package.json`, `render.yaml`, `public/` ve README'yi GitHub deposunun **köküne** yükleyin. Render otomatik deploy tamamlandığında `/health` endpoint'i ile çalışmasını kontrol edin. Bu paketi ZIP olarak doğrudan GitHub'a yüklemeyin.

## Kontrol

`node --check server.js` ve istemci JS sözdizimi kontrolleri yapıldı. Canlı Render dağıtımı ve gerçek telefonlarda bağlantı testi yapılmadı.
