# THE ERİNÇ: Beylerbeyi Savaşı

10 oyuncuya kadar tek haritada gerçek WebSocket multiplayer. Altı özgün skin, canlı sıralama, mobil joystick, 5 dakikada bir son zeytinli poğaça.

Node.js 22+ ile `node server.js`, sonra `http://localhost:3000`. Kurulum bağımlılığı yok; `ws` 8.22.0 MIT lisansıyla `vendor/ws` içinde bulunur.

Test: `node --test test/*.test.js`

Render: New → Blueprint → bu repo. `render.yaml` hazır. Alternatif: Node Web Service, build `node --check server.js`, start `node server.js`, health `/health`.

DirectAdmin: `public` içeriğini `public_html/agar/` içine kopyala, `config.js` içindeki `serverUrl` değerini kendi `wss://SERVIS.onrender.com/ws` adresinle değiştir. Render `ALLOWED_ORIGINS` = `https://umutbulut.com,https://www.umutbulut.com`. DirectAdmin'de Node.js gerekmez.

`kaptan` ve `samet` tam isimleri gökkuşağı skin ve oyuncuya özel pembe arka plan; `umutsiker` 2500 kütle. Harf duyarlı. Normal başlangıç 70 kütle. Tek oda, en fazla 10 kişi. Yeniden başlatmada skor sıfırlanır. Tek Render instance kullan.

WebSocket `/ws`, HTTP health `/health`, statik oyun `/`. Veritabanı gerekmez. Kapsamlı Türkçe kurulum rehberi teslim ZIP'inin kökündeki `KURULUM.md` dosyasındadır.
