#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/backup-ui}"
BACKUP_DIR="${BACKUP_DIR:-/opt/backup-ui.rollback}"
ARCHIVE="${1:-}"

if [[ -z "$ARCHIVE" ]]; then
  echo "Укажите архив rollback, например:"
  ls -1t "$BACKUP_DIR"/backup-ui-*.tar.gz 2>/dev/null | head
  exit 1
fi

echo "Останавливаю текущий backup-ui"
if [[ -d "$APP_DIR" ]]; then
  (cd "$APP_DIR" && docker compose down) || true
fi

echo "Восстанавливаю $ARCHIVE"
rm -rf "$APP_DIR"
mkdir -p "$(dirname "$APP_DIR")"
tar -C "$(dirname "$APP_DIR")" -xzf "$ARCHIVE"

echo "Запускаю восстановленную версию"
cd "$APP_DIR"
docker compose up -d backup-ui

