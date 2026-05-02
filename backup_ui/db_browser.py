from __future__ import annotations

import shlex
from typing import Any

from .commands import run
from .discovery import discover_docker_containers, human_size


POSTGRES_MARKERS = ("postgres", "postgis")
MYSQL_MARKERS = ("mysql", "mariadb")


def discover_database_containers() -> list[dict[str, Any]]:
    rows = []
    for item in discover_docker_containers():
        name = item.get("Names", "")
        image = item.get("Image", "")
        text = f"{name} {image}".lower()
        engine = ""
        if any(marker in text for marker in POSTGRES_MARKERS):
            engine = "postgres"
        elif any(marker in text for marker in MYSQL_MARKERS):
            engine = "mysql"
        if not engine:
            continue
        rows.append(
            {
                "name": name,
                "image": image,
                "engine": engine,
                "state": item.get("State", ""),
                "status": item.get("Status", ""),
                "databases": list_databases(name, engine) if name and item.get("State") == "running" else [],
            }
        )
    return rows


def list_databases(container: str, engine: str) -> list[dict[str, Any]]:
    if engine == "postgres":
        return _postgres_databases(container)
    if engine == "mysql":
        return _mysql_databases(container)
    return []


def list_tables(container: str, engine: str, database: str) -> list[dict[str, Any]]:
    if engine == "postgres":
        return _postgres_tables(container, database)
    if engine == "mysql":
        return _mysql_tables(container, database)
    return []


def _postgres_databases(container: str) -> list[dict[str, Any]]:
    sql = "select datname, pg_database_size(datname) from pg_database where datistemplate=false order by datname"
    result = _docker_shell(
        container,
        f"psql -U ${{POSTGRES_USER:-postgres}} -d postgres -At -F '|' -c {shlex.quote(sql)}",
    )
    if result.code != 0:
        return [{"name": "ошибка доступа", "size": "-", "size_bytes": 0, "error": result.stderr.strip()}]
    rows = []
    for line in result.stdout.splitlines():
        parts = line.split("|")
        if len(parts) < 2:
            continue
        size = _int(parts[1])
        rows.append({"name": parts[0], "size": human_size(size), "size_bytes": size, "error": ""})
    return rows


def _postgres_tables(container: str, database: str) -> list[dict[str, Any]]:
    sql = """
select schemaname || '.' || relname,
       coalesce(n_live_tup, 0),
       pg_total_relation_size(quote_ident(schemaname) || '.' || quote_ident(relname))
  from pg_stat_user_tables
 order by pg_total_relation_size(quote_ident(schemaname) || '.' || quote_ident(relname)) desc,
          schemaname, relname
""".strip()
    result = _docker_shell(
        container,
        f"psql -U ${{POSTGRES_USER:-postgres}} -d {shlex.quote(database)} -At -F '|' -c {shlex.quote(sql)}",
    )
    if result.code != 0:
        return [{"name": "ошибка доступа", "rows": "-", "size": "-", "error": result.stderr.strip()}]
    rows = []
    for line in result.stdout.splitlines():
        parts = line.split("|")
        if len(parts) < 3:
            continue
        rows.append(
            {
                "name": parts[0],
                "rows": parts[1],
                "size": human_size(_int(parts[2])),
                "error": "",
            }
        )
    return rows


def _mysql_databases(container: str) -> list[dict[str, Any]]:
    query = """
select s.schema_name,
       coalesce(sum(t.data_length + t.index_length), 0)
  from information_schema.schemata s
  left join information_schema.tables t on t.table_schema = s.schema_name
 group by s.schema_name
 order by s.schema_name
""".strip()
    result = _mysql_shell(
        container,
        "-e " + shlex.quote(query),
    )
    if result.code != 0:
        return [{"name": "обнаружен контейнер, но нет доступа без настроек", "size": "-", "size_bytes": 0, "error": result.stderr.strip()}]
    rows = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0].strip():
            continue
        size = _int(parts[1]) if len(parts) > 1 else 0
        rows.append({"name": parts[0], "size": human_size(size), "size_bytes": size, "error": ""})
    return rows


def _mysql_tables(container: str, database: str) -> list[dict[str, Any]]:
    escaped_db = database.replace("'", "''")
    query = (
        "select table_name, table_rows, data_length + index_length "
        f"from information_schema.tables where table_schema = '{escaped_db}' "
        "order by data_length + index_length desc"
    )
    result = _mysql_shell(
        container,
        "-e " + shlex.quote(query),
    )
    if result.code != 0:
        return [{"name": "ошибка доступа", "rows": "-", "size": "-", "error": result.stderr.strip()}]
    rows = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        rows.append({"name": parts[0], "rows": parts[1], "size": human_size(_int(parts[2])), "error": ""})
    return rows


def _docker_shell(container: str, command: str):
    return run(["docker", "exec", container, "sh", "-lc", command], timeout=45)


def _mysql_shell(container: str, args: str):
    command = (
        'user="${MYSQL_USER:-root}"; '
        'password="${MYSQL_PASSWORD:-${MYSQL_ROOT_PASSWORD:-}}"; '
        'if [ -n "$password" ]; then '
        f'mysql -N -B -u"$user" -p"$password" {args}; '
        'else '
        f'mysql -N -B -u"$user" {args}; '
        'fi'
    )
    return _docker_shell(container, command)


def _int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
