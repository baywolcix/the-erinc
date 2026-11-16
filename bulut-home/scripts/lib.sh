#!/usr/bin/env bash
# BULUT HOME betikleri için ortak yardımcılar. Doğrudan çalıştırılmaz; diğer betikler `source` eder.
set -euo pipefail

BULUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$BULUT_DIR/data"
IMAGE="${BULUT_IMAGE:-bulut-home}"
HEALTH_URL="${BULUT_HEALTH_URL:-http://127.0.0.1:8080/api/health}"

c_info() { printf '\033[36m▸ %s\033[0m\n' "$*"; }
c_ok()   { printf '\033[32m✓ %s\033[0m\n' "$*"; }
c_warn() { printf '\033[33m! %s\033[0m\n' "$*" >&2; }
c_err()  { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; }
die()    { c_err "$*"; exit 1; }

# root değilsek sudo ile çalıştır
as_root() { if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi; }

# Betiği root olarak yeniden başlat (data/ klasörü konteyner kullanıcısına (uid 1000) ait, okumak için root gerekir)
require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    command -v sudo >/dev/null || die "Root yetkisi gerekiyor (sudo yok)."
    exec sudo -E bash "$0" "$@"
  fi
}

# Git komutlarını depo sahibinin kullanıcısıyla çalıştır (root ile çalıştırmak dosya sahipliğini bozar)
REPO_OWNER="$(stat -c %U "$BULUT_DIR" 2>/dev/null || id -un)"
git_owner() {
  if [ "$(id -u)" -eq 0 ] && [ "$REPO_OWNER" != "root" ]; then
    sudo -u "$REPO_OWNER" -H git -C "$BULUT_DIR" "$@"
  else
    git -C "$BULUT_DIR" "$@"
  fi
}

# docker: kullanıcı docker grubunda değilse sudo ile
docker_cmd() {
  if docker info >/dev/null 2>&1; then docker "$@"; else as_root docker "$@"; fi
}

compose() {
  if docker_cmd compose version >/dev/null 2>&1; then
    (cd "$BULUT_DIR" && docker_cmd compose "$@")
  elif command -v docker-compose >/dev/null 2>&1; then
    (cd "$BULUT_DIR" && if docker info >/dev/null 2>&1; then docker-compose "$@"; else as_root docker-compose "$@"; fi)
  else
    die "docker compose bulunamadı (docker-compose paketi kurulu mu?)"
  fi
}

# İmajı derle. İsteğe bağlı: BULUT_BASE_IMAGE (ör. mirror.gcr.io/library/python:3.13-slim-trixie), BULUT_CA_BUNDLE
build_image() {
  local tag="${1:-latest}"
  local args=(build -t "$IMAGE:$tag")
  [ -n "${BULUT_BASE_IMAGE:-}" ] && args+=(--build-arg "BASE_IMAGE=$BULUT_BASE_IMAGE")
  [ -n "${BULUT_CA_BUNDLE:-}" ] && args+=(--secret "id=ca_bundle,src=$BULUT_CA_BUNDLE")
  args+=("$BULUT_DIR")
  DOCKER_BUILDKIT=1 docker_cmd "${args[@]}"
}

image_exists() { docker_cmd image inspect "$1" >/dev/null 2>&1; }

wait_healthy() {
  local timeout="${1:-90}" i=0
  while [ "$i" -lt "$timeout" ]; do
    if curl -fsS --max-time 3 "$HEALTH_URL" >/dev/null 2>&1; then return 0; fi
    sleep 2; i=$((i + 2))
  done
  return 1
}

app_version() { curl -fsS --max-time 3 "$HEALTH_URL" 2>/dev/null | sed -n 's/.*"version":"\([^"]*\)".*/\1/p'; }

container_running() { [ "$(docker_cmd inspect -f '{{.State.Running}}' bulut-home 2>/dev/null || echo false)" = "true" ]; }

# Tutarlı (çevrimiçi) SQLite yedeği. $1 = hedef dosya
backup_db() {
  local dest="$1"
  mkdir -p "$(dirname "$dest")"
  chown 1000:1000 "$(dirname "$dest")" 2>/dev/null || true   # konteyner kullanıcısı yazabilsin
  if [ ! -f "$DATA_DIR/bulut.db" ]; then c_warn "Veritabanı yok, yedek atlandı"; return 0; fi
  if container_running; then
    local rel="${dest#"$DATA_DIR"/}"
    [ "$rel" = "$dest" ] && die "Yedek hedefi data/ altında olmalı: $dest"
    docker_cmd exec -T bulut-home python -c "import sqlite3,sys;s=sqlite3.connect('/data/bulut.db');d=sqlite3.connect(sys.argv[1]);s.backup(d);d.close()" "/data/$rel" \
      || die "Çevrimiçi yedek alınamadı"
  elif command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$DATA_DIR/bulut.db" ".backup '$dest'"
  else
    python3 -c "import sqlite3,sys;s=sqlite3.connect(sys.argv[1]);d=sqlite3.connect(sys.argv[2]);s.backup(d);d.close()" "$DATA_DIR/bulut.db" "$dest"
  fi
  # bütünlük kontrolü
  python3 -c "import sqlite3,sys;r=sqlite3.connect(sys.argv[1]).execute('PRAGMA integrity_check').fetchone()[0];sys.exit(0 if r=='ok' else 1)" "$dest" \
    || die "Yedek bütünlük kontrolünden geçmedi: $dest"
  chmod 600 "$dest" 2>/dev/null || true
}
