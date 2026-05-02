# Backup UI

Backup UI - self-hosted web interface for Linux/Docker servers. It helps inspect a server, discover projects and databases, create backup plans, run backups manually, review snapshots, and prepare restore operations.

The application is designed to run as a separate Docker container on each server. By default it binds only to `127.0.0.1:8090`; access it through an SSH tunnel or a protected reverse proxy.

## Features

- server overview: hostname, IP, OS, uptime, CPU, memory, disks, load average;
- process list and read-only directory browser;
- Docker project discovery in `/opt`;
- PostgreSQL, MySQL and MariaDB container discovery;
- read-only database and table overview without reading table rows;
- server profile snapshot without secrets;
- backup plans for projects, config files and databases;
- local and SSH/rsync storage targets;
- manual backup runs;
- retention dry-run and manual retention apply;
- restore workflow with explicit confirmation;
- separate Docker Compose restore override for host write access.

## Requirements

On the target server:

- Linux with Docker Engine;
- Docker Compose v2;
- Git;
- SSH access for administration.

Install the usual packages on Ubuntu/Debian:

```bash
apt-get update
apt-get install -y git docker.io docker-compose-plugin
```

## Install

```bash
git clone https://github.com/viktorplus/backup-ui.git /opt/backup-ui
cd /opt/backup-ui
docker compose up -d --build
```

Open an SSH tunnel from your workstation:

```bash
ssh -L 8090:127.0.0.1:8090 root@SERVER
```

Then open:

```text
http://127.0.0.1:8090
```

## Update

```bash
cd /opt/backup-ui
git pull
docker compose up -d --build
```

For a deployment with an automatic rollback archive:

```bash
cd /opt/backup-ui
bash deploy/deploy.sh
```

The deploy script archives the previous `/opt/backup-ui` into:

```text
/opt/backup-ui.rollback/
```

## Rollback

List available rollback archives:

```bash
ls -1t /opt/backup-ui.rollback/backup-ui-*.tar.gz
```

Restore one archive:

```bash
bash /opt/backup-ui/deploy/rollback.sh /opt/backup-ui.rollback/backup-ui-YYYYMMDD-HHMMSS.tar.gz
```

## Security

Do not expose Backup UI directly to the internet.

The container has access to:

- Docker socket;
- read-only host root mount;
- backup directory write mount;
- host Docker CLI.

Use one of these access patterns:

- SSH tunnel;
- VPN;
- reverse proxy with TLS, authentication and IP restrictions.

Never commit or publish:

- backup archives;
- database dumps;
- private SSH keys;
- `.env` files with secrets;
- application state database;
- private server profile notes.

## Documentation

- `docs/INSTALL_RU.md`
- `docs/DEPLOY_DOCKER_RU.md`
- `docs/OPERATIONS_RU.md`
- `docs/SECURITY_RU.md`
- `docs/ROADMAP_RU.md`
