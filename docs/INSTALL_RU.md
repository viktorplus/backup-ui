# Установка Backup UI

Основной способ установки на новый сервер - `git clone`.

## Требования

На сервере нужны:

- Linux;
- Docker Engine;
- Docker Compose v2;
- Git;
- SSH-доступ для администратора.

Ubuntu/Debian:

```bash
apt-get update
apt-get install -y git docker.io docker-compose-plugin
```

## Установка

```bash
git clone https://github.com/viktorplus/backup-ui.git /opt/backup-ui
cd /opt/backup-ui
docker compose up -d --build
```

## Доступ

UI по умолчанию слушает только `127.0.0.1:8090` на сервере.

С локальной машины открыть tunnel:

```bash
ssh -L 8090:127.0.0.1:8090 root@SERVER
```

Открыть в браузере:

```text
http://127.0.0.1:8090
```

## Проверка

```bash
cd /opt/backup-ui
docker compose ps
curl -fsS http://127.0.0.1:8090/ >/dev/null && echo OK
```

## Обновление

```bash
cd /opt/backup-ui
git pull
docker compose up -d --build
```

## Обновление С Rollback-Архивом

```bash
cd /opt/backup-ui
bash deploy/deploy.sh
```

Скрипт перед запуском создает архив текущего приложения:

```text
/opt/backup-ui.rollback/backup-ui-YYYYMMDD-HHMMSS.tar.gz
```

## Откат

```bash
ls -1t /opt/backup-ui.rollback/backup-ui-*.tar.gz
bash /opt/backup-ui/deploy/rollback.sh /opt/backup-ui.rollback/backup-ui-YYYYMMDD-HHMMSS.tar.gz
```

## Systemd Без Docker

Docker Compose - рекомендуемый production-способ. Systemd-вариант нужен только если вы сознательно хотите запускать приложение как Python-сервис на хосте.

```bash
cd /opt/backup-ui
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
cp systemd/backup-ui.service /etc/systemd/system/backup-ui.service
systemctl daemon-reload
systemctl enable --now backup-ui.service
```

## Безопасность

Не публикуйте UI напрямую в интернет. Используйте SSH tunnel, VPN или reverse proxy с авторизацией.
