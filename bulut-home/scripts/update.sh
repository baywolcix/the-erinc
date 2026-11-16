#!/usr/bin/env bash
# BULUT HOME güncelleme: yedek → git pull → derle → başlat → sağlık kontrolü → başarısızsa OTOMATİK geri al.
#
#   scripts/update.sh            (uzak daldan --ff-only çeker)
#   scripts/update.sh --no-pull  (yalnızca mevcut kodu yeniden derle/başlat)
#
# Geri alma bilgisi: data/backups/pre-update/last-update.env  → scripts/rollback.sh
# Veritabanı göçleri eklemelidir (yalnızca yeni tablo/sütun); eski sürüm yeni şemayla çalışabilir.
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
require_root "$@"

PULL=1
for a in "$@"; do
  case "$a" in
    --no-pull) PULL=0 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) die "Bilinmeyen seçenek: $a" ;;
  esac
done
cd "$BULUT_DIR"
git_owner rev-parse --git-dir >/dev/null 2>&1 || die "Git deposu değil: $BULUT_DIR"
if [ -n "$(git_owner status --porcelain --untracked-files=no -- .)" ]; then
  die "bulut-home içinde commit edilmemiş değişiklik var; güncelleme durduruldu (git status)."
fi

PREV_COMMIT="$(git_owner rev-parse HEAD)"
TS="$(date +%Y%m%d-%H%M%S)"
STATE_DIR="$DATA_DIR/backups/pre-update"
mkdir -p "$STATE_DIR"
PREV_VERSION="$(app_version || true)"

# 1) Yedek
BACKUP="$STATE_DIR/bulut-$TS-${PREV_COMMIT:0:8}.db"
backup_db "$BACKUP"
c_ok "Yedek alındı: ${BACKUP#"$BULUT_DIR"/}"

# 2) Mevcut imajı geri alma için sakla
if image_exists "$IMAGE:latest"; then
  docker_cmd tag "$IMAGE:latest" "$IMAGE:rollback"
  c_ok "Önceki imaj $IMAGE:rollback olarak etiketlendi"
fi
cat > "$STATE_DIR/last-update.env" <<STATE
PREV_COMMIT=$PREV_COMMIT
PREV_VERSION=$PREV_VERSION
BACKUP_FILE=$BACKUP
UPDATED_AT=$TS
STATE

rollback_now() {
  c_err "$1 — otomatik geri alınıyor"
  git_owner reset -q --hard "$PREV_COMMIT"
  if image_exists "$IMAGE:rollback"; then docker_cmd tag "$IMAGE:rollback" "$IMAGE:latest"; fi
  compose up -d --force-recreate
  if wait_healthy 90; then
    c_warn "Önceki sürüme dönüldü ($(app_version)). Veritabanı DEĞİŞTİRİLMEDİ; gerekirse: scripts/rollback.sh --restore-db"
  else
    c_err "Geri alma sonrası da sağlıklı değil. Kayıtlar: docker compose logs bulut ; veritabanı yedeği: $BACKUP"
  fi
  exit 1
}

# 3) Kod
if [ "$PULL" = 1 ]; then
  BRANCH="$(git_owner rev-parse --abbrev-ref HEAD)"
  c_info "Güncelleniyor: origin/$BRANCH"
  git_owner fetch -q origin "$BRANCH" || die "git fetch başarısız (ağ?) — hiçbir şey değişmedi"
  git_owner merge -q --ff-only "origin/$BRANCH" || die "İleri sarılamıyor (yerel commit'ler var?) — hiçbir şey değişmedi"
fi
NEW_COMMIT="$(git_owner rev-parse HEAD)"
if [ "$NEW_COMMIT" = "$PREV_COMMIT" ] && [ "$PULL" = 1 ]; then
  c_ok "Zaten güncel (${NEW_COMMIT:0:8})."
  exit 0
fi
c_info "Kod: ${PREV_COMMIT:0:8} → ${NEW_COMMIT:0:8}"

# 4) Derle ve başlat
build_image latest || rollback_now "Derleme başarısız"
compose up -d --force-recreate || rollback_now "Başlatma başarısız"
wait_healthy 90 || rollback_now "Sağlık kontrolü başarısız"
c_ok "Güncelleme tamam: ${PREV_VERSION:-?} → $(app_version) (${NEW_COMMIT:0:8})"
