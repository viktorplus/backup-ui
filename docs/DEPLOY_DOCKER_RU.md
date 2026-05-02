# Production Deploy Через Docker

## Назначение

Docker Compose - основной production-способ запуска Backup UI.

Схема по умолчанию:

```text
127.0.0.1:8090 -> backup-ui:8090
```

UI не открывает порт наружу.

## Первый Запуск

```bash
git clone https://github.com/viktorplus/backup-ui.git /opt/backup-ui
cd /opt/backup-ui
docker compose up -d --build
```

Доступ:

```bash
ssh -L 8090:127.0.0.1:8090 root@SERVER
```

Открыть:

```text
http://127.0.0.1:8090
```

## Монтирования

Обычный режим:

```text
/var/run/docker.sock -> /var/run/docker.sock
/usr/bin/docker -> /usr/bin/docker:ro
/:ro -> /host/root:ro
/opt -> /host/opt:ro
/etc -> /host/etc:ro
/opt/backups -> /backups:rw
backup-ui-data -> /var/lib/backup-ui
backup-ui-logs -> /var/log/backup-ui
```

Назначение:

- Docker socket нужен для анализа контейнеров и `docker exec`;
- `/host/root`, `/host/opt`, `/host/etc` доступны только на чтение;
- `/backups` доступен на запись для backup-копий;
- state DB и логи лежат в Docker volumes.

## Обновление

Простое обновление:

```bash
cd /opt/backup-ui
git pull
docker compose up -d --build
```

Обновление с rollback-архивом:

```bash
cd /opt/backup-ui
bash deploy/deploy.sh
```

## Rollback

```bash
ls -1t /opt/backup-ui.rollback/backup-ui-*.tar.gz
bash /opt/backup-ui/deploy/rollback.sh /opt/backup-ui.rollback/backup-ui-YYYYMMDD-HHMMSS.tar.gz
```

Rollback восстанавливает файлы приложения. Docker volumes `backup-ui-data` и `backup-ui-logs` не удаляются.

## Restore Mode

Обычный режим не дает UI писать в `/opt` и `/etc` хоста. Для восстановления файлов можно временно включить override:

```bash
cd /opt/backup-ui
docker compose -f docker-compose.yml -f docker-compose.restore.yml up -d
```

После восстановления вернуться в read-only режим:

```bash
docker compose up -d
```

## Что Не Делает Deploy

- не запускает backup-планы;
- не включает расписание;
- не применяет retention;
- не запускает restore;
- не удаляет старые backup-копии;
- не меняет существующие проекты.
