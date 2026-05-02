# Production Deploy Через Docker

## Схема

Backup UI запускается отдельным контейнером:

```text
127.0.0.1:8090 -> backup-ui:8090
```

Доступ снаружи:

```bash
ssh -L 8090:127.0.0.1:8090 root@SERVER
```

Затем открыть:

```text
http://127.0.0.1:8090
```

## Монтирования

Обычный режим:

```text
/var/run/docker.sock -> docker API
/usr/bin/docker -> Docker CLI хоста для docker exec
/:ro -> /host/root:ro
/opt -> /host/opt:ro
/etc -> /host/etc:ro
/opt/backups -> /backups:rw
backup-ui-data -> /var/lib/backup-ui
backup-ui-logs -> /var/log/backup-ui
```

В обычном режиме `/opt` и `/etc` доступны только на чтение.

## Restore Mode

Для восстановления файлов на хост нужно временно включить override:

```bash
docker compose -f docker-compose.yml -f docker-compose.restore.yml up -d
```

После восстановления вернуться в read-only режим:

```bash
docker compose up -d
```

## Deploy

```bash
cd /opt/backup-ui
bash deploy/deploy.sh
```

Скрипт перед запуском делает rollback-архив текущего `/opt/backup-ui` в:

```text
/opt/backup-ui.rollback/
```

## Rollback

```bash
bash /opt/backup-ui/deploy/rollback.sh /opt/backup-ui.rollback/backup-ui-YYYYMMDD-HHMMSS.tar.gz
```

## Что Не Делает Deploy

- не запускает backup-планы;
- не включает расписание;
- не удаляет старые backup-копии;
- не меняет существующие проекты.
