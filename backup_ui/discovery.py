from __future__ import annotations

import json
import os
import shlex
from typing import Any

from .commands import run
from .settings import DEFAULT_BACKUP_ROOT, HOST_ETC, HOST_FS, HOST_OPT


CONFIG_CANDIDATES = [
    "ssh",
    "systemd/system",
    "cron.d",
    "crontab",
    "nginx",
    "caddy",
]

POSTGRES_MARKERS = ("postgres", "postgis")
MYSQL_MARKERS = ("mysql", "mariadb")
MYSQL_SYSTEM_DATABASES = {"information_schema", "mysql", "performance_schema", "sys"}


def _docker_json(format_expr: str, command: list[str]) -> list[dict[str, Any]]:
    result = run(command + ["--format", format_expr], timeout=30)
    if result.code != 0:
        return []
    rows = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def discover_docker_containers() -> list[dict[str, Any]]:
    return _docker_json(
        "{{json .}}",
        ["docker", "ps", "-a"],
    )


def discover_projects() -> list[dict[str, Any]]:
    projects: dict[str, dict[str, Any]] = {}

    for compose in HOST_OPT.glob("**/docker-compose.yml") if HOST_OPT.exists() else []:
        root = compose.parent
        name = root.name
        if name == "app" and root.parent.name:
            name = root.parent.name
        projects[name] = {
            "name": name,
            "path": str(root),
            "kind": "docker-compose",
            "recommended": True,
            "comment": "Найден docker-compose.yml",
        }

    for child in HOST_OPT.iterdir() if HOST_OPT.exists() else []:
        if child.is_dir() and child.name not in projects:
            projects[child.name] = {
                "name": child.name,
                "path": str(child),
                "kind": "directory",
                "recommended": child.name not in {"backups", "containerd"},
                "comment": "Каталог в /opt",
            }

    containers = discover_docker_containers()
    for item in containers:
        name = item.get("Names") or item.get("Names", "")
        if name and name not in projects:
            projects[name] = {
                "name": name,
                "path": "",
                "kind": "container",
                "recommended": False,
                "comment": "Контейнер без найденного каталога проекта",
            }

    return sorted(projects.values(), key=lambda x: x["name"])


def discover_databases() -> list[dict[str, Any]]:
    containers = discover_docker_containers()
    databases: list[dict[str, Any]] = []

    for row in containers:
        container = row.get("Names")
        if not container:
            continue
        text = (row.get("Image", "") + " " + row.get("Names", "")).lower()
        if any(marker in text for marker in POSTGRES_MARKERS):
            databases.extend(_discover_postgres_databases(container))
        elif any(marker in text for marker in MYSQL_MARKERS):
            databases.extend(_discover_mysql_databases(container))
    return databases


def discover_postgres() -> list[dict[str, Any]]:
    return [db for db in discover_databases() if db["engine"] == "postgres"]


def _discover_postgres_databases(container: str) -> list[dict[str, Any]]:
    databases: list[dict[str, Any]] = []
    cmd = [
        "docker",
        "exec",
        container,
        "sh",
        "-lc",
        "psql -U ${POSTGRES_USER:-postgres} -d postgres -At -c "
        "\"select datname || '|' || pg_database_size(datname) "
        "from pg_database where datistemplate=false order by datname\"",
    ]
    result = run(cmd, timeout=30)
    if result.code != 0:
        return [
            {
                "engine": "postgres",
                "container": container,
                "name": "ошибка доступа",
                "size_bytes": 0,
                "size_human": "-",
                "recommended": False,
                "comment": "PostgreSQL найден, но список баз недоступен без корректных учетных данных",
            }
        ]
    for line in result.stdout.splitlines():
        if "|" not in line:
            continue
        name, size = line.split("|", 1)
        size_bytes = _int(size)
        databases.append(_database_row("postgres", container, name, size_bytes))
    return databases


def _discover_mysql_databases(container: str) -> list[dict[str, Any]]:
    query = """
select s.schema_name,
       coalesce(sum(t.data_length + t.index_length), 0)
  from information_schema.schemata s
  left join information_schema.tables t on t.table_schema = s.schema_name
 group by s.schema_name
 order by s.schema_name
""".strip()
    command = (
        'user="${MYSQL_USER:-root}"; '
        'password="${MYSQL_PASSWORD:-${MYSQL_ROOT_PASSWORD:-}}"; '
        'if [ -n "$password" ]; then '
        f'mysql -N -B -u"$user" -p"$password" -e {shlex.quote(query)}; '
        'else '
        f'mysql -N -B -u"$user" -e {shlex.quote(query)}; '
        'fi'
    )
    result = run(["docker", "exec", container, "sh", "-lc", command], timeout=30)
    if result.code != 0:
        return [
            {
                "engine": "mysql",
                "container": container,
                "name": "ошибка доступа",
                "size_bytes": 0,
                "size_human": "-",
                "recommended": False,
                "comment": "MySQL/MariaDB найден, но список баз недоступен без корректных учетных данных",
            }
        ]
    databases: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0].strip():
            continue
        if parts[0] in MYSQL_SYSTEM_DATABASES:
            continue
        size_bytes = _int(parts[1]) if len(parts) > 1 else 0
        databases.append(_database_row("mysql", container, parts[0], size_bytes))
    return databases


def _database_row(engine: str, container: str, name: str, size_bytes: int) -> dict[str, Any]:
    large = size_bytes >= 2 * 1024 * 1024 * 1024
    return {
        "engine": engine,
        "container": container,
        "name": name,
        "size_bytes": size_bytes,
        "size_human": human_size(size_bytes),
        "recommended": not large,
        "comment": "Большие базы лучше включать отдельным планом"
        if large
        else "Можно включить в обычный проектный backup",
    }


def discover_configs() -> list[dict[str, Any]]:
    items = []
    for raw in CONFIG_CANDIDATES:
        path = HOST_ETC / raw
        if path.exists():
            items.append(
                {
                    "name": f"etc_{raw}".replace("/", "_").strip("_"),
                    "path": str(path),
                    "recommended": raw in {"ssh", "systemd/system"},
                    "comment": "Конфигурационный файл или каталог",
                }
            )
    for caddyfile in list(HOST_OPT.glob("*/Caddyfile")) + list(HOST_OPT.glob("*/*/Caddyfile")) if HOST_OPT.exists() else []:
        items.append(
            {
                "name": "opt_" + "_".join(caddyfile.relative_to(HOST_OPT).parts),
                "path": str(caddyfile),
                "recommended": True,
                "comment": "Caddyfile из /opt",
            }
        )
    return items


def discover_storage() -> dict[str, Any]:
    roots = [
        (str(DEFAULT_BACKUP_ROOT), DEFAULT_BACKUP_ROOT),
        ("/opt/backups", HOST_OPT / "backups"),
        ("/var/backups", HOST_FS / "var" / "backups"),
    ]
    return {
        "local_roots": [
            {
                "path": display,
                "actual_path": str(actual),
                "exists": actual.exists(),
                "writable": os.access(actual, os.W_OK) if actual.exists() else False,
            }
            for display, actual in roots
        ],
        "ssh_available": run(["sh", "-lc", "command -v ssh >/dev/null 2>&1"], timeout=5).code == 0,
        "rsync_available": run(["sh", "-lc", "command -v rsync >/dev/null 2>&1"], timeout=5).code == 0,
    }


def discover_all() -> dict[str, Any]:
    return {
        "projects": discover_projects(),
        "databases": discover_databases(),
        "configs": discover_configs(),
        "storage": discover_storage(),
    }


def human_size(size: int) -> str:
    value = float(size)
    for unit in ["B", "K", "M", "G", "T"]:
        if value < 1024 or unit == "T":
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{size}B"


def _int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
