#!/usr/bin/env bash
# BULUT HOME — Debian 13 (trixie) ilk kurulum. Tekrar çalıştırılabilir (idempotent); mevcut veriye dokunmaz.
#
#   cd the-erinc/bulut-home && sudo scripts/install-debian.sh
#
# Seçenekler:
#   --skip-packages     apt paket kurulumunu atla (Docker zaten kuruluysa)
#   --non-interactive   anahtar sihirbazını sorma (.env'i sonra: python3 scripts/configure.py)
#   --with-tailscale    Tailscale'i resmi betikle kur ve 'tailscale serve' ile HTTPS yayınla
#   --force             Debian 13 dışı sistemde de devam et
# Ortam: BULUT_BASE_IMAGE (Docker Hub 429 için ayna), BULUT_CA_BUNDLE (TLS denetimli vekil sunucu)
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
require_root "$@"

SKIP_PKGS=0; INTERACTIVE=1; WITH_TS=0; FORCE=0
for a in "$@"; do
  case "$a" in
    --skip-packages) SKIP_PKGS=1 ;;
    --non-interactive) INTERACTIVE=0 ;;
    --with-tailscale) WITH_TS=1 ;;
    --force) FORCE=1 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) die "Bilinmeyen seçenek: $a" ;;
  esac
done

# 1) Sistem kontrolü
. /etc/os-release 2>/dev/null || true
if [ "${ID:-}" != "debian" ] || [ "${VERSION_ID:-}" != "13" ]; then
  [ "$FORCE" = 1 ] || die "Bu betik Debian 13 için yazıldı (bulunan: ${PRETTY_NAME:-bilinmiyor}). Yine de denemek için --force."
  c_warn "Debian 13 değil (${PRETTY_NAME:-?}); --force ile devam ediliyor."
fi
MEM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
c_info "Sistem: ${PRETTY_NAME:-?}, RAM ${MEM_MB} MB, çekirdek $(nproc)"
OWNER="${SUDO_USER:-$(id -un)}"

# 2) Paketler
if [ "$SKIP_PKGS" = 0 ]; then
  c_info "Paketler kuruluyor (docker.io, docker-compose, docker-buildx, git, sqlite3, python3, curl)…"
  as_root apt-get update -q
  as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -q \
    ca-certificates curl git sqlite3 python3 docker.io docker-compose docker-buildx
  as_root systemctl enable --now docker
  if [ "$OWNER" != "root" ] && ! id -nG "$OWNER" | grep -qw docker; then  # sudo'suz docker için
    as_root usermod -aG docker "$OWNER"
    c_warn "$OWNER docker grubuna eklendi; sudo'suz docker için oturumu kapatıp aç."
  fi
fi
command -v docker >/dev/null || die "docker bulunamadı"
compose version >/dev/null || die "docker compose çalışmıyor"
c_ok "Docker hazır: $(docker_cmd --version)"

# 3) Veri klasörü ve yapılandırma
mkdir -p "$DATA_DIR/backups"
as_root chown -R 1000:1000 "$DATA_DIR"
as_root chmod 750 "$DATA_DIR"
python3 "$BULUT_DIR/scripts/configure.py" --init
if [ "$OWNER" != "root" ]; then chown "$OWNER" "$BULUT_DIR/.env"; fi
if [ "$INTERACTIVE" = 1 ] && [ -t 0 ]; then
  c_info "Yapılandırma sihirbazı (boş geçilebilir; sonra: python3 scripts/configure.py)"
  if [ "$OWNER" != "root" ]; then sudo -u "$OWNER" python3 "$BULUT_DIR/scripts/configure.py"
  else python3 "$BULUT_DIR/scripts/configure.py"; fi
fi
python3 "$BULUT_DIR/scripts/configure.py" --show

# 4) Derle ve başlat (mevcut veri korunur; şema göçleri otomatik ve eklemelidir)
if [ -f "$DATA_DIR/bulut.db" ]; then
  c_info "Mevcut veritabanı bulundu; başlatmadan önce yedek alınıyor"
  backup_db "$DATA_DIR/backups/pre-update/bulut-install-$(date +%Y%m%d-%H%M%S).db"
fi
c_info "İmaj derleniyor (ilk seferde birkaç dakika sürebilir)…"
build_image latest || die "Derleme başarısız. Docker Hub 429 ise: BULUT_BASE_IMAGE=mirror.gcr.io/library/python:3.13-slim-trixie ile tekrar dene."
compose up -d
c_info "Sağlık kontrolü bekleniyor…"
wait_healthy 120 || { compose logs --tail 50 bulut; die "Uygulama sağlıklı başlamadı (kayıtlar yukarıda)."; }
c_ok "BULUT HOME çalışıyor: sürüm $(app_version) — http://127.0.0.1:8080"

# 5) İlk kurulum kodu
if [ -f "$DATA_DIR/.setup_token" ]; then
  echo; c_info "İLK KURULUM KODU (tek kullanımlık): $(as_root cat "$DATA_DIR/.setup_token")"
  echo "   Tarayıcıda aç → kullanıcı adı + parola (≥10 karakter) + bu kod."
fi

# 6) Tailscale (isteğe bağlı)
if [ "$WITH_TS" = 1 ]; then
  if ! command -v tailscale >/dev/null; then
    c_info "Tailscale kuruluyor (resmi betik: https://tailscale.com/install.sh)"
    curl -fsSL https://tailscale.com/install.sh | as_root sh
  fi
  as_root tailscale up || c_warn "tailscale up tamamlanmadı; tarayıcıdaki giriş bağlantısını kullan ve tekrar çalıştır."
  as_root tailscale serve --bg 8080 && c_ok "Tailscale HTTPS yayını açık: $(as_root tailscale serve status 2>/dev/null | head -1)"
  c_warn "HTTPS kullanırken .env içinde BULUT_COOKIE_SECURE=1 yap ve: docker compose up -d"
fi

echo
c_ok "Kurulum tamam. Sonraki adımlar: INSTALL_DEBIAN.md → 'Kurulumdan sonra'."
