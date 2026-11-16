#!/usr/bin/env bash
# Veritabanı yedeği (uygulama çalışırken de tutarlı). Kullanım:
#   scripts/backup.sh                 → data/backups/manual/bulut-<zaman>.db
#   scripts/backup.sh /mnt/usb/bulut  → ayrıca bu klasöre kopyalar
#   scripts/backup.sh --with-env ...  → .env'i de (gizli anahtarlar!) 600 izinle yedekler
#   BULUT_BACKUP_KEEP=14 (varsayılan): manual/ içinde en yeni 14 yedek tutulur
# shellcheck source=scripts/lib.sh
source "$(dirname "$0")/lib.sh"
require_root "$@"

WITH_ENV=0; EXTRA=""
for a in "$@"; do
  case "$a" in
    --with-env) WITH_ENV=1 ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) EXTRA="$a" ;;
  esac
done
TS="$(date +%Y%m%d-%H%M%S)"
DEST="$DATA_DIR/backups/manual/bulut-$TS.db"
backup_db "$DEST"
c_ok "Yedek: $DEST ($(du -h "$DEST" | cut -f1))"
if [ "$WITH_ENV" = 1 ] && [ -f "$BULUT_DIR/.env" ]; then
  install -m 600 "$BULUT_DIR/.env" "$DATA_DIR/backups/manual/env-$TS"
  c_warn ".env yedeklendi (gizli anahtarlar içerir): data/backups/manual/env-$TS"
fi
if [ -n "$EXTRA" ]; then
  mkdir -p "$EXTRA"
  cp -p "$DEST" "$EXTRA/"
  [ "$WITH_ENV" = 1 ] && [ -f "$DATA_DIR/backups/manual/env-$TS" ] && cp -p "$DATA_DIR/backups/manual/env-$TS" "$EXTRA/"
  c_ok "Kopyalandı: $EXTRA/"
fi
KEEP="${BULUT_BACKUP_KEEP:-14}"
# shellcheck disable=SC2012  # dosya adlarını biz üretiyoruz (bulut-YYYYmmdd-HHMMSS.db)
mapfile -t OLD < <(ls -1t "$DATA_DIR"/backups/manual/bulut-*.db 2>/dev/null | tail -n +"$((KEEP + 1))")
for f in "${OLD[@]}"; do rm -f -- "$f"; done
[ "${#OLD[@]}" -gt 0 ] && c_info "${#OLD[@]} eski elle yedek döndürüldü (en yeni $KEEP tutuluyor)"
exit 0
