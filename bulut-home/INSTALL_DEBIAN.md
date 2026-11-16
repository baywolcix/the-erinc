# BULUT HOME — ASUS üzerinde ilk kurulum (Debian 13)

Hedef: ASUS VivoBook X415JA (i3-1005G1, 8 GB RAM), 7/24 açık, ekransız (SSH) çalışabilir.
Süre: Debian kurulumu hariç ~20–30 dakika. Gerekenler: internet, bir USB bellek (Debian için), telefonunda Tailscale uygulaması.

> Bu belgede `$` ile başlayan satırları ASUS'ta terminale yaz. `#` ile başlayanlar açıklamadır.

---

## 0. Debian 13'ü kur (bir kez)

1. Başka bir bilgisayarda https://www.debian.org/download adresinden **Debian 13 "trixie" netinst (amd64)** ISO'sunu indir, Rufus/Etcher ile USB'ye yaz.
2. ASUS'ta USB'den başlat (açılışta **F2** → Boot menüsü veya **Esc**).
3. Kurulumda:
   - Dil Türkçe olabilir; **ana bilgisayar adı**: `bulut-home`.
   - Root parolası belirle **ve** kendi kullanıcını oluştur (ör. `umut`).
   - Disk: "Tüm diski kullan" (diskteki her şey silinir — önce yedekle).
   - Yazılım seçimi: **masaüstünü kaldır** (RAM tasarrufu), **SSH sunucusu** ve **standart sistem araçları** işaretli kalsın.
4. Kurulum bitince USB'yi çıkar, yeniden başlat, kullanıcınla giriş yap.

Dizüstü kapağı kapalıyken uyumasın:
```
$ sudo sed -i 's/^#\?HandleLidSwitch=.*/HandleLidSwitch=ignore/; s/^#\?HandleLidSwitchExternalPower=.*/HandleLidSwitchExternalPower=ignore/' /etc/systemd/logind.conf
$ sudo systemctl restart systemd-logind
```

Kullanıcına sudo yetkisi ver (kurulumda root parolası belirlediysen gerekir):
```
$ su -c "apt-get install -y sudo && usermod -aG sudo $USER"
# ardından oturumu kapatıp aç (exit, tekrar giriş)
```

## 1. Depoyu indir

```
$ sudo apt-get update && sudo apt-get install -y git
$ git clone -b claude/bulut-home-ai-assistant-116nno https://github.com/baywolcix/the-erinc.git
$ cd the-erinc/bulut-home
```
Depo özelse GitHub kullanıcı adı ve bir **Personal Access Token** (parola yerine) ister.

## 2. Kurulum betiğini çalıştır

```
$ sudo scripts/install-debian.sh
```
Betik sırayla:
1. Docker, docker compose, BuildKit, git, sqlite3, python3 kurar ve Docker'ı açılışta başlatır.
2. `data/` klasörünü ve `.env` dosyasını (izin 600, rastgele oturum anahtarıyla) hazırlar.
3. **Yapılandırma sihirbazını** açar (aşağıya bak). Her alanı boş geçebilirsin, sonra tekrar çalıştırırsın.
4. İmajı derler (ilk sefer birkaç dakika), başlatır, sağlık kontrolünü bekler.
5. Ekrana **İLK KURULUM KODU**nu yazar — bir kenara not et.

Sihirbazın soruları:
| Alan | Ne girmeli |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys → yeni anahtar (`sk-ant-...`). Ekranda görünmez. |
| `BULUT_USD_TRY_RATE` | Bugünkü dolar kuru (ör. `41.2`). **Boş kalırsa ücretli çağrı yapılmaz.** |
| `BULUT_MONTHLY_BUDGET_TRY` | Aylık sınır, ör. `400`. |
| `NTFY_TOPIC` | Bildirim konusu: uzun ve tahmin edilemez, ör. `bulut-7f3k9q2m1x8z` (12–64 karakter). |
| Diğerleri | İsteğe bağlı; boş geç. |

Hata alırsan:
- **"429 Too Many Requests"** (Docker Hub sınırı):
  `sudo BULUT_BASE_IMAGE=mirror.gcr.io/library/python:3.13-slim-trixie scripts/install-debian.sh --skip-packages`
- **"docker-buildx kurulamadı"**: Docker'ın resmi Debian deposunu ekle (https://docs.docker.com/engine/install/debian/), `docker-buildx-plugin` kur, betiği `--skip-packages` ile tekrar çalıştır.

## 3. İlk giriş (ASUS'un kendisinden veya SSH tüneliyle)

Ekransız kullanıyorsan kendi bilgisayarından tünel aç:
```
# Windows PowerShell / macOS / Linux:
ssh -L 8080:127.0.0.1:8080 umut@<ASUS-yerel-IP>
```
Tarayıcıda **http://127.0.0.1:8080** → kullanıcı adı, parola (en az 10 karakter) ve **ilk kurulum kodu**. Kod tek kullanımlıktır.

## 4. Telefondan erişim: Tailscale

```
$ curl -fsSL https://tailscale.com/install.sh | sh
$ sudo tailscale up            # ekrandaki bağlantıyı aç, Tailscale hesabınla onayla
$ sudo tailscale serve --bg 8080
$ tailscale serve status        # https://bulut-home.<tailnet>.ts.net adresini gösterir
```
(Ya da kurulumu `sudo scripts/install-debian.sh --skip-packages --with-tailscale` ile yaptır.)

HTTPS açıldıktan sonra çerezi güvenli yap:
```
$ python3 scripts/configure.py   # BULUT_PUBLIC_URL = https://bulut-home.<tailnet>.ts.net
$ sed -i 's/^BULUT_COOKIE_SECURE=.*/BULUT_COOKIE_SECURE=1/' .env
$ docker compose up -d
```
iPhone: Tailscale uygulamasını kur, aynı hesapla giriş yap → Safari'de adresi aç → Paylaş → **Ana Ekrana Ekle**.

## 5. API anahtarını doğrula (ücretsiz) ve canlı test (ücretli, kuruşlar)

```
$ docker compose exec bulut python -m app.cli check      # token harcamaz: anahtar ve model erişimi
$ docker compose exec bulut python -m app.cli live-test  # GERÇEK API: sohbet + hafıza arama + görev oluşturma
```
`live-test` önce tahmini en kötü maliyeti gösterir ve `evet` yazmanı ister (sert tavan $0.05). Sonuç `data/live_tests/` altına yazılır; arayüzde Sistem → "Canlı API testi" de aynı işi yapar.

## 6. Mobil bildirim (ntfy)

1. Telefona **ntfy** uygulamasını kur (App Store / Google Play).
2. "+" → sunucu `ntfy.sh` (veya kendi sunucun) → konu: `.env`'deki `NTFY_TOPIC`.
3. BULUT'ta Sistem → **Test bildirimi gönder**. Telefona "BULUT test bildirimi" gelmeli.

Gelen olaylar: görev başarısız (kritik), onay bekleyen işlem (kritik), bütçe %80 / %100, önemli görev tamamlandı, günlük brifing. Sessiz saatler için `.env` → `BULUT_NOTIFY_QUIET=23:00-08:00`.
Gizlilik: ntfy.sh herkese açıktır, konu adını bilen mesajları okuyabilir. Konu adını paylaşma; istersen `BULUT_NOTIFY_DETAILS=0` ile yalnızca başlık gönder.

## Kurulumdan sonra: günlük kullanım

| İş | Komut (`the-erinc/bulut-home` içinde) |
|---|---|
| Durum | `docker compose ps` · `curl -s 127.0.0.1:8080/api/health` |
| Kayıtlar | `docker compose logs --tail 100 bulut` |
| Ayar değiştir | `python3 scripts/configure.py` → `docker compose up -d` |
| Ayarları gör (gizliler gizli) | `python3 scripts/configure.py --show` |
| Elle yedek | `sudo scripts/backup.sh` (USB'ye de: `sudo scripts/backup.sh /media/usb/bulut`) |
| Güncelle | `sudo scripts/update.sh` |
| Son güncellemeyi geri al | `sudo scripts/rollback.sh` |
| Veritabanını da geri al | `sudo scripts/rollback.sh --restore-db` |
| Belirli bir yedeğe dön | `sudo scripts/rollback.sh --db-only data/backups/manual/bulut-....db` |
| Parola sıfırla | `docker compose exec bulut python -m app.cli set-password umut` |

### Güncelleme nasıl çalışır?
`update.sh`: (1) çalışırken tutarlı veritabanı yedeği alır ve bütünlüğünü kontrol eder, (2) çalışan imajı `bulut-home:rollback` olarak saklar, (3) `git pull --ff-only`, (4) derler ve başlatır, (5) 90 sn içinde sağlıklı değilse **otomatik olarak önceki koda ve imaja döner**. Veritabanına otomatik dokunmaz (göçler yalnızca ekleme yapar); gerekirse `rollback.sh --restore-db`. Geri yüklemeden önce mevcut veritabanı `data/backups/pre-restore-*.db` olarak saklanır — hiçbir veri kaybolmaz.

### Yedekler nerede?
- `data/backups/bulut-*.db` — uygulamanın günlük otomatik yedeği (son 7)
- `data/backups/manual/` — `backup.sh` ile (son 14)
- `data/backups/pre-update/` — her güncellemeden önce (silinmez; ara sıra elle temizle)
- **Öneri:** Haftada bir USB'ye/başka makineye kopyala: `sudo scripts/backup.sh /media/usb/bulut --with-env` (`--with-env` gizli anahtarları da kopyalar; o USB'yi güvenli tut).

### Kaynak kullanımı
Boşta ~35–80 MB RAM (ölçüldü), konteyner sınırı 512 MB. 8 GB RAM'in büyük kısmı diğer servislere (ör. ayrı Docker servisi olarak borsa botu) kalır.
