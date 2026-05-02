from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .commands import run
from .settings import HOST_ETC, HOST_OPT


CONFIG_CANDIDATES = [
    "ssh",
    "systemd/system",
    "cron.d",
    "crontab",
    "nginx",
    "caddy",
]


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


def discover_postgres() -> list[dict[str, Any]]:
    containers = discover_docker_containers()
    pg_containers = [
        row.get("Names")
        for row in containers
        if "postgres" in (row.get("Image", "") + " " + row.get("Names", "")).lower()
    ]
    databases: list[dict[str, Any]] = []

    for container in pg_containers:
        if not container:
            continue
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
            continue
        for line in result.stdout.splitlines():
            if "|" not in line:
                continue
            name, size = line.split("|", 1)
            try:
                size_bytes = int(size)
            except ValueError:
                size_bytes = 0
            databases.append(
                {
                    "container": container,
                    "name": name,
                    "size_bytes": size_bytes,
                    "size_human": human_size(size_bytes),
                    "recommended": size_bytes < 2 * 1024 * 1024 * 1024,
                    "comment": "Большие базы лучше включать отдельным планом"
                    if size_bytes >= 2 * 1024 * 1024 * 1024
                    else "Можно включить в обычный проектный backup",
                }
            )
    return databases


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
    roots = ["/opt/backups", "/var/backups"]
    return {
        "local_roots": [
            {
                "path": root,
                "exists": Path(root).exists(),
                "writable": os.access(root, os.W_OK) if Path(root).exists() else False,
            }
            for root in roots
        ],
        "ssh_available": run(["sh", "-lc", "command -v ssh >/dev/null 2>&1"], timeout=5).code == 0,
        "rsync_available": run(["sh", "-lc", "command -v rsync >/dev/null 2>&1"], timeout=5).code == 0,
    }


def discover_all() -> dict[str, Any]:
    return {
        "projects": discover_projects(),
        "databases": discover_postgres(),
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
