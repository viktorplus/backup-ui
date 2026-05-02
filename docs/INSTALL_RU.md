# Установка Backup UI

## 1. Скопировать проект на сервер

```bash
mkdir -p /opt/backup-ui
rsync -a ./ /opt/backup-ui/
```

## 2. Создать Python окружение

```bash
cd /opt/backup-ui
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
```

## 3. Запуск вручную

```bash
BACKUP_UI_HOME=/var/lib/backup-ui \
BACKUP_UI_BACKUP_ROOT=/opt/backups/projects \
.venv/bin/uvicorn backup_ui.app:app --host 127.0.0.1 --port 8090
```

Открывать через SSH tunnel:

```bash
ssh -L 8090:127.0.0.1:8090 root@SERVER
```

Затем открыть:

```text
http://127.0.0.1:8090
```

## 4. Systemd

```bash
cp systemd/backup-ui.service /etc/systemd/system/backup-ui.service
systemctl daemon-reload
systemctl enable --now backup-ui.service
```

## Безопасность

По умолчанию сервис слушает только `127.0.0.1`. Для доступа снаружи используйте SSH tunnel или reverse proxy с авторизацией.
