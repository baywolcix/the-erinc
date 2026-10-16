# THE ERİNÇ — Beylerbeyi Savaşı ONLINE v1.1

## Yenilikler
- Toplam oyuncu kütlesi üst sınırı: **50.000**.
- Son zeytinli poğaça haritanın rastgele bir noktasında belirir ve toplam kütleyi **iki katına** çıkarır (50.000 üst sınırı geçilmez).
- **Space:** 16 parçaya kadar gerçek bölünme. Parçalar kaybolmaz; 12 saniye sonra yeterince yakınlarsa otomatik birleşir.
- **W:** En büyük parçadan 12 kütle harcayıp 10 kütlelik yem fırlatır. Diğer oyuncular yiyebilir.
- **umutsiker:** 1150 başlangıç kütlesi ve hareketli RGB çerçeve.
- Haritada beliren ⚡ bonusu 10 saniyeliğine **2x hız** verir.
- **kaptan** ve **samet:** büyük-küçük harfe duyarlı gökkuşağı skini, kendi ekranlarında pembe arka plan.

## GitHub ve Render
1. ZIP'i bilgisayarda aç. **ZIP'i değil, içindeki** `server.js`, `package.json`, `render.yaml`, `README.md`, `public` klasörünü GitHub `baywolcix/the-erinc` deposunun kök dizinine yükle (eski dosyaların üzerine yaz).
2. Render'da **New > Web Service** seçip GitHub deposunu bağla. Build command: `npm install`, Start command: `npm start`, plan: mevcutsa Free.
3. Render'ın verdiği `https://...onrender.com` adresinde oyunu açarak dene. `/health` adresi oyuncu sayısını döndürür.
4. `umutbulut.com/agar` için DirectAdmin `public_html/agar` klasörüne `public` klasörünün **içeriğini** yükle. `index.html` içindeki `const SERVER_URL=''` satırını `const SERVER_URL='https://SENIN-RENDER-ADRESIN.onrender.com'` şeklinde düzenle. HTTPS sitesi için güvenli WSS otomatik kullanılır.
5. Telefon ve bilgisayarda aynı anda bağlanıp test et.

**Önemli:** Sadece statik HTML yüklemek gerçek multiplayer sağlamaz; Render sunucusu çalışıyor olmalıdır. Ücretsiz plan uykuya geçebilir. Oyuncu ismiyle tetiklenen özel güçler herkese açıktır; sınıf oyunu için tasarlanmıştır.
