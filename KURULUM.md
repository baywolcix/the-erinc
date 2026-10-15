# THE ERİNÇ: Beylerbeyi Savaşı — Online 2.0

Altı orijinal dairesel karakter görseliyle aynı haritada en fazla 10 gerçek oyuncu. Beş kişi de oynayabilir, minimum oyuncu beklemesi yok. Bot yok. İsim yazıp karakter seçmek yeterli.

## Pakette ne var?

| Klasör / dosya | Kullanımı |
| --- | --- |
| `github-upload/` | Tam Node.js sunucusu, oyun, testler ve Render ayarı. GitHub'a **bu klasörün içindekiler** yüklenir. |
| `directadmin-upload/agar/` | `umutbulut.com/agar/` için yalnızca statik oyun dosyaları. |
| `TEST-RAPORU.md` | Yerel test sonuçları ve sınırları. |
| `GORSEL-KAYNAKLARI.json` | Eski konuşmadan alınan altı görselin dosya eşleşmesi ve SHA-256 değerleri. |

Eski konuşmadaki offline demo v1.1 kodu, erişilebilen kayıtta yalnızca içerik referansı olarak bulunuyordu; kullanılabilir HTML/ZIP alınamadı. Bu yüzden onun birebir kod dönüşümü yerine aynı konsepti, altı özgün görseli ve talep edilen kuralları kullanan yeni bir online 2.0 hazırlandı. Görseller yeniden üretilmedi veya değiştirilmedi; tarayıcıda daire içinde gösterilir.

## 1 — Önce kendi bilgisayarında dene

1. [Node.js](https://nodejs.org/) 22 veya üzerini kur. Node.js 24 ile test edildi.
2. ZIP'i bir klasöre çıkar. ZIP içinden doğrudan çalıştırma.
3. Windows'ta `github-upload/BASLAT-WINDOWS.cmd` dosyasını aç. Alternatif: bu klasörde terminal açıp `node server.js` çalıştır.
4. Tarayıcıdan **http://localhost:3000** adresini aç.
5. İkinci bir sekmede başka isimle gir; iki oyuncu da aynı haritadadır.

`npm install` gerekmez. MIT lisanslı standart `ws` 8.22.0 kitaplığı `vendor/ws/` içinde, kendi lisansıyla pakete dahil edildi. Node.js dışında kurulum veya internetten bağımlılık indirme yok.

Aynı Wi-Fi'daki telefondan denemek için bilgisayarın yerel IPv4 adresini bul, örneğin `http://192.168.1.20:3000`. Sunucu açık kalmalı. Windows güvenlik duvarı sorarsa özel ağ erişimine izin ver. Telefonun `localhost` adresi bilgisayarın değildir. Bu yerel test için HTTPS gerekmez.

Dosyaya çift tıklayıp `index.html` açmak online sunucuyu başlatmaz.

## 2 — GitHub'a sürükleyip yükle

1. GitHub'da yeni bir repository oluştur; örnek ad: `the-erinc-online`. Görselleri herkese açık paylaşmak istemiyorsan private seç.
2. Boş depoda “uploading an existing file” bağlantısını veya **Add file → Upload files** seçeneğini aç.
3. ZIP'ten çıkan **`github-upload` klasörünün içindekileri** seçip yükleme alanına sürükle. `server.js`, `package.json`, `render.yaml`, `game.js`, `public`, `vendor`, `test` depo kökünde olmalı.
4. “Commit changes” ile kaydet. `vendor` ve altı skinin olduğu `public/assets/skins` klasörleri mutlaka yüklenmeli.

Depoda `github-upload/package.json` yerine doğrudan `package.json` görünmeli. Üst klasörü yanlışlıkla yüklediysen Render'da Root Directory alanını `github-upload` yapman gerekir. En kolay yol klasör içeriğini köke yüklemektir. `directadmin-upload` klasörünü bu depoya yüklemene gerek yok.

## 3 — Render'da oyun sunucusunu aç

### Kolay yol: Blueprint

1. [Render](https://dashboard.render.com/) hesabına gir, **New → Blueprint** seç.
2. GitHub deponu bağla; private depo kullanıyorsan Render'a o depoyu okuma izni ver.
3. `render.yaml` algılanır. Oluşturulacak `the-erinc-online` servisini ve planını kontrol edip kurulumu başlat.
4. Servis “Live” olduktan sonra kendi adresini kopyala: örneğin `https://the-erinc-online-xxxx.onrender.com`.
5. Bu adresin sonunda `/health` aç. `{"ok":true,...}` görmelisin.
6. Aynı adresin ana sayfası oyunu açar. Bu sayfada ayrıca sunucu adresi düzenlemek gerekmez.

### Alternatif: Web Service

Blueprint yerine **New → Web Service** ile de kurabilirsin:

| Alan | Değer |
| --- | --- |
| Runtime / Language | Node |
| Root Directory | Boş; dosyalar depo kökündeyse |
| Build Command | `node --check server.js` |
| Start Command | `node server.js` |
| Health Check Path | `/health` |
| Environment: `NODE_VERSION` | `24` |
| Environment: `ALLOWED_ORIGINS` | `https://umutbulut.com,https://www.umutbulut.com` |

Portu Render'ın verdiği `PORT` değişkeninden alır, `0.0.0.0` üzerinde dinler. WebSocket yolu **`/ws`**. Ayrı port açma veya Socket.IO kurulumu gerekmez.

**Tek sunucu instance'ı kullan.** Oda bellekte tutulur; çoklu instance ortak durum paylaşmaz. Yeniden başlatma/dağıtım sırasında skorlar ve etkinlik saati sıfırlanır. Ücretsiz servis kullanılmadığında uyuyabilir; ilk bağlantıda bekleme olabilir. Plan koşullarını Render panelinden kontrol et. Kesintisiz sınıf oyunu için uyumayan plan tercih edilebilir.

## 4 — `umutbulut.com/agar/` dosyalarını DirectAdmin'e yükle

1. `directadmin-upload/agar/config.js` dosyasını düz metin düzenleyicide aç.
2. Örnek servis adresini **kendi gerçek Render adresinle** değiştir:

```js
window.ERINC_CONFIG = {
  serverUrl: 'wss://the-erinc-online-xxxx.onrender.com/ws'
};
```

Buradaki `xxxx` örnektir. Render adresin neyse aynısını kullan; başlangıcı **`wss://`**, sonu **`/ws`** olmalı. `https://` veya `ws://` yazma.

3. DirectAdmin → File Manager / Dosya Yöneticisi → `domains/umutbulut.com/public_html/` klasörüne git. Bazı hesaplarda yalnızca `public_html/` görünür; alan adının belge kökünü kullan.
4. Paket içindeki `agar` klasörünü bütün içeriğiyle buraya yükle. Zaten `agar` klasörü varsa içeriğini yedekleyip yenisiyle değiştir.
5. Sonuç şu olmalı:

```text
public_html/
└── agar/
    ├── index.html
    ├── config.js
    ├── client.js
    ├── style.css
    └── assets/
        ├── icon.svg
        └── skins/
            ├── skin-1.jpeg
            ├── skin-2.jpeg
            ├── skin-3.jpeg
            ├── skin-4.jpeg
            ├── skin-5.jpeg
            └── skin-6.jpeg
```

6. Alan adı için SSL sertifikasının etkin olduğundan emin ol. **https://umutbulut.com/agar/** adresini aç. Adresin sonundaki `/` önemlidir; göreli dosya yolları bununla doğru çözülür.
7. Bir arkadaşın başka telefon/bilgisayardan aynı adrese girsin. “Masanın liderleri” alanında iki ismi birlikte görmelisiniz.

DirectAdmin'de Node.js gerekmez. DirectAdmin oyunun görünümünü sunar; gerçek zamanlı oyun Render'da çalışır. Arkadaşlarına Render adresini vermen gerekmez; herkes `umutbulut.com/agar/` üzerinden katılabilir. Render ana sayfasından girenler de aynı odadadır.

## Oynanış

- **Fare:** imleci ekran merkezinden gitmek istediğin yöne götür; merkeze yaklaştırınca yavaşlar.
- **WASD veya yön tuşları:** klavyeyle hareket et.
- **Mobil:** sol alttaki sanal yön çubuğunu sürükle, durmak için bırak. Çoklu dokunma sırasında ilk parmak kontrolü tutar.
- Haritadaki renkli kırıntılar **+2 kütle** verir. Büyüdükçe yavaşlarsın.
- Birini yutmak için en az **1,25 kat kütleye** sahip olup yeterince üstüne gelmen gerekir. Kütlesinin %80'i sana geçer.
- Doğunca **4 saniye kalkan** vardır: yutulamaz, başkasını yutamaz ve poğaçayı alamazsın.
- Yutulunca 1,5 saniye sonra yeniden doğabilirsin. İsim ve skin korunur.
- Kütle üst sınırı 14.000'dir. Bölünme ve kütle fırlatma bu sürüme dahil değildir.
- Her **5 dakikada bir** harita merkezinde tek bir **son zeytinli poğaça** belirir. İlk alan +600 kütle ve bir poğaça galibiyeti kazanır; herkese duyurulur. 60 saniyede alınmazsa kaybolur. Etkinlik tüm oyuncular için sunucu saatine bağlıdır; sayfa yenilemek geri sayımı sıfırlamaz.
- Küçük harita oyuncuları ve aktif poğaçayı gösterir. Altın ok merkeze yönlendirir.

### İsim kodları — büyük/küçük harfe duyarlı

| Tam isim | Etki |
| --- | --- |
| `kaptan` | Dairesel gökkuşağı bayrağı skin + **bu oyuncunun ekranında** pembe harita |
| `samet` | Dairesel gökkuşağı bayrağı skin + **bu oyuncunun ekranında** pembe harita |
| `umutsiker` | 70 yerine **2.500 kütle** ile devasa başlangıç; yeniden doğuşta da geçerli |
| `Kaptan`, `SAMET`, `Umutsiker` vb. | Özel etki yok |

Diğer oyuncular gökkuşağı skinini görür; kendi arka planları normal kalır. İsimlerin başındaki/sonundaki boşluklar temizlenir. Aynı tam isim aynı anda iki kişiye verilmez. Bu isimler eğlencelik kodlardır, hesap veya kimlik doğrulama sistemi değildir.

## Bağlantı ve sorun giderme

| Belirti | Kontrol |
| --- | --- |
| Sunucuya ulaşılamıyor | Önce Render ana adresini ve `/health` sayfasını aç. Servis uyuyorsa açılmasını bekleyip tekrar katıl. |
| Render açılıyor ama alan adından girilemiyor | DirectAdmin `config.js` adresini; Render `ALLOWED_ORIGINS` değerini kontrol et. Domaini protokolüyle, yol veya sonda `/` olmadan yaz. |
| HTTPS'te bağlantı kurulmuyor | `serverUrl` **wss://** olmalı; sertifika geçerli olmalı. |
| Skinler görünmüyor | `assets/skins/` klasörünün tamamı, dosya isimleri ve harfleri aynı mı? Adres sonu `/agar/` mı? |
| Eski dosyalar görünüyor | Ctrl+F5 veya mobil tarayıcı önbelleğini yenile. CDN kullanıyorsan dosyaların önbelleğini temizle. |
| Pastane dolu | 10 oyuncu sınırı. Çıkış düğmesiyle yer hemen boşalır; kopan bağlantı kalp atışı kontrolüyle temizlenir. |
| Bu isim kullanılıyor | Farklı isim kullan; eski sekmeyi kapat. Bağlantı aniden koptuysa temizlenmesi yaklaşık 30 saniye sürebilir. |
| Dağıtım sırasında oyun koptu | İstemci yeniden bağlanmayı dener. Skor ve konum yeniden başlar; başarısızsa menüden yeniden katıl. |

Başka domain kullanacaksan Render'daki `ALLOWED_ORIGINS` listesine ekle, örneğin `https://oyun.ornek.com`. Aynı Render adresinden ve aynı yerel adres üzerinden açılan sayfalar otomatik kabul edilir. Liste tüm WebSocket istemcileri için kimlik doğrulama sağlamaz; tarayıcı köken kontrolüdür.

## Testleri tekrar çalıştır

`github-upload` klasöründe:

```sh
node --test test/*.test.js
```

Node.js 22+ gereklidir. Bu testler oyun kurallarını ve 10 gerçek WebSocket bağlantısını yerelde doğrular. Arkadaşlarınla canlı alan adında kısa kabul testi de yap: aynı odada isimleri gör, hareket et, 11. kişinin giremediğini dene, beş dakikalık poğaçayı birlikte gözle.

## Teknik yapı ve kapsam

Sunucu 30 kez/sn simülasyon yapar, durumu yaklaşık 15 kez/sn yayınlar. İstemci çizimi yumuşatır. Sunucu kütle, hız, çarpışma, skor, yeniden doğuş ve etkinlik kararlarını verir. İstemci yalnızca yön gönderir; istemciden gelen kütle veya konum dikkate alınmaz. Mesaj boyutu/hızı sınırı, boşta bağlantı temizliği ve ping/pong kontrolü vardır. En fazla 10 kişilik tek oda; veritabanı, kalıcı hesap veya oda listesi yok.

### Resmî dağıtım kaynakları

- [Render WebSocket desteği](https://render.com/docs/websocket)
- [Render Blueprint ayarları](https://render.com/docs/blueprint-spec)
- [Render sağlık kontrolleri](https://render.com/docs/health-checks)

Canlı GitHub yüklemesi, Render kurulumu ve DirectAdmin yüklemesi bu paketin hazırlanması sırasında yapılmadı; yukarıdaki adımlar hesaplarında uygulanmalıdır.
