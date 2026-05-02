#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/backup-ui}"
BACKUP_DIR="${BACKUP_DIR:-/opt/backup-ui.rollback}"
TS="$(date +%Y%m%d-%H%M%S)"

log() {
  echo "[$(date -Is)] $*"
}

log "Подготовка rollback-копии"
mkdir -p "$BACKUP_DIR"
if [[ -d "$APP_DIR" ]]; then
  tar -C "$(dirname "$APP_DIR")" -czf "${BACKUP_DIR}/backup-ui-${TS}.tar.gz" "$(basename "$APP_DIR")"
  log "Rollback archive: ${BACKUP_DIR}/backup-ui-${TS}.tar.gz"
fi

log "Создание каталогов"
mkdir -p "$APP_DIR" /opt/backups
chmod 700 /opt/backups

log "Сборка контейнера"
cd "$APP_DIR"
docker compose build backup-ui

log "Проверка конфигурации compose"
docker compose config >/tmp/backup-ui-compose-${TS}.yml

log "Запуск контейнера"
docker compose up -d backup-ui

log "Проверка health HTTP"
sleep 3
curl -fsS http://127.0.0.1:8090/ >/dev/null

log "Готово. UI доступен через SSH tunnel: ssh -L 8090:127.0.0.1:8090 root@SERVER"

