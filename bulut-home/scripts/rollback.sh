#!/usr/bin/env bash
# Son güncellemeyi geri al (data/backups/pre-update/last-update.env).
#
#   scripts/rollback.sh                       kodu ve imajı önceki sürüme döndür (veritabanına dokunmaz)
#   scripts/rollback.sh --restore-db          ayrıca veritabanını güncelleme öncesi yedeğe döndür
#   scripts/rollback.sh --restore-db DOSYA    belirli bir yedeğe döndür
#   scripts/rollback.sh --db-only DOSYA       yalnızca veritabanını geri yükle
#   --yes                                     onay sorma
# Veritabanı geri yüklenmeden önce mevcut hali data/backups/pre-restore-*.db olarak saklanır (veri kaybolmaz).
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
require_root "$@"

RESTORE=0; DB_ONLY=0; FILE=""; YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --restore-db) RESTORE=1; if [ -n "${2:-}" ] && [ "${2#--}" = "$2" ]; then FILE="$2"; shift; fi ;;
    --db-only) RESTORE=1; DB_ONLY=1; FILE="${2:-}"; [ -n "$FILE" ] || die "--db-only bir dosya ister"; shift ;;
    --yes) YES=1 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) die "Bilinmeyen seçenek: $1" ;;
  esac
  shift
done
cd "$BULUT_DIR"
STATE="$DATA_DIR/backups/pre-update/last-update.env"
PREV_COMMIT=""; BACKUP_FILE=""
if [ -f "$STATE" ]; then
  PREV_COMMIT="$(sed -n 's/^PREV_COMMIT=//p' "$STATE")"
  BACKUP_FILE="$(sed -n 's/^BACKUP_FILE=//p' "$STATE")"
elif [ "$DB_ONLY" = 0 ]; then
  die "Geri alınacak güncelleme kaydı yok ($STATE)"
fi
[ -z "$FILE" ] && FILE="$BACKUP_FILE"

confirm() { [ "$YES" = 1 ] && return 0; read -r -p "$1 [evet/hayır]: " ans; [ "$ans" = "evet" ]; }

if [ "$DB_ONLY" = 0 ]; then
  [ -n "$(git_owner status --porcelain --untracked-files=no -- .)" ] && die "Commit edilmemiş değişiklik var; önce temizle."
  confirm "Kod ${PREV_COMMIT:0:8} sürümüne ve önceki imaja döndürülsün mü?" || die "İptal"
  git_owner reset -q --hard "$PREV_COMMIT"
  if image_exists "$IMAGE:rollback"; then docker_cmd tag "$IMAGE:rollback" "$IMAGE:latest"
  else c_warn "$IMAGE:rollback imajı yok; önceki kod yeniden derleniyor"; build_image latest; fi
fi

if [ "$RESTORE" = 1 ]; then
  [ -f "$FILE" ] || die "Yedek dosyası yok: $FILE"
  python3 -c "import sqlite3,sys;r=sqlite3.connect(sys.argv[1]).execute('PRAGMA integrity_check').fetchone()[0];sys.exit(0 if r=='ok' else 1)" "$FILE" \
    || die "Yedek bozuk görünüyor: $FILE"
  confirm "Veritabanı '$FILE' yedeğine döndürülsün mü? (Mevcut hali saklanacak; o andan sonraki değişiklikler geri yüklenen sürümde olmaz)" || die "İptal"
  compose stop bulut
  SAFE="$DATA_DIR/backups/pre-restore-$(date +%Y%m%d-%H%M%S).db"
  if [ -f "$DATA_DIR/bulut.db" ]; then backup_db "$SAFE"; c_ok "Mevcut veritabanı saklandı: $SAFE"; fi
  as_root install -m 640 -o 1000 -g 1000 "$FILE" "$DATA_DIR/bulut.db.restore"
  as_root rm -f "$DATA_DIR/bulut.db-wal" "$DATA_DIR/bulut.db-shm"
  as_root mv -f "$DATA_DIR/bulut.db.restore" "$DATA_DIR/bulut.db"
  c_ok "Veritabanı geri yüklendi"
fi

compose up -d --force-recreate
wait_healthy 90 || die "Sağlıklı başlamadı: docker compose logs bulut"
c_ok "Geri alma tamam. Sürüm: $(app_version)"
