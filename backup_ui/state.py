from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .settings import STATE_DB, ensure_dirs


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    ensure_dirs()
    conn = sqlite3.connect(STATE_DB)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            create table if not exists plans (
              id integer primary key autoincrement,
              name text not null,
              enabled integer not null default 0,
              schedule text not null default '',
              backup_root text not null,
              storage_json text not null,
              include_json text not null,
              retention_json text not null,
              created_at text not null,
              updated_at text not null
            );

            create table if not exists jobs (
              id integer primary key autoincrement,
              plan_id integer,
              kind text not null,
              status text not null,
              message text not null default '',
              snapshot_path text not null default '',
              started_at text not null,
              finished_at text
            );

            create table if not exists job_logs (
              id integer primary key autoincrement,
              job_id integer not null,
              created_at text not null,
              level text not null,
              message text not null
            );

            create table if not exists server_profiles (
              id integer primary key autoincrement,
              name text not null unique,
              hostname text not null,
              profile_json text not null,
              created_at text not null,
              updated_at text not null
            );
            """
        )


def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def loads(text: str, default: Any) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def create_job(plan_id: int | None, kind: str, message: str = "") -> int:
    with connect() as conn:
        cur = conn.execute(
            """
            insert into jobs (plan_id, kind, status, message, started_at)
            values (?, ?, 'running', ?, ?)
            """,
            (plan_id, kind, message, utc_now()),
        )
        return int(cur.lastrowid)


def add_log(job_id: int, message: str, level: str = "info") -> None:
    with connect() as conn:
        conn.execute(
            "insert into job_logs (job_id, created_at, level, message) values (?, ?, ?, ?)",
            (job_id, utc_now(), level, message),
        )


def finish_job(job_id: int, status: str, message: str, snapshot_path: str = "") -> None:
    with connect() as conn:
        conn.execute(
            """
            update jobs
               set status = ?, message = ?, snapshot_path = ?, finished_at = ?
             where id = ?
            """,
            (status, message, snapshot_path, utc_now(), job_id),
        )


def list_jobs(limit: int = 30) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "select * from jobs order by id desc limit ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_job(job_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("select * from jobs where id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def get_job_logs(job_id: int) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "select * from job_logs where job_id = ? order by id",
            (job_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_plans() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("select * from plans order by id desc").fetchall()
    plans: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["storage"] = loads(item.pop("storage_json"), [])
        item["include"] = loads(item.pop("include_json"), {})
        item["retention"] = loads(item.pop("retention_json"), {})
        plans.append(item)
    return plans


def get_plan(plan_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("select * from plans where id = ?", (plan_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["storage"] = loads(item.pop("storage_json"), [])
    item["include"] = loads(item.pop("include_json"), {})
    item["retention"] = loads(item.pop("retention_json"), {})
    return item


def save_plan(plan: dict[str, Any]) -> int:
    now = utc_now()
    with connect() as conn:
        if plan.get("id"):
            conn.execute(
                """
                update plans
                   set name = ?, enabled = ?, schedule = ?, backup_root = ?,
                       storage_json = ?, include_json = ?, retention_json = ?, updated_at = ?
                 where id = ?
                """,
                (
                    plan["name"],
                    int(plan.get("enabled", False)),
                    plan.get("schedule", ""),
                    plan["backup_root"],
                    dumps(plan.get("storage", [])),
                    dumps(plan.get("include", {})),
                    dumps(plan.get("retention", {})),
                    now,
                    plan["id"],
                ),
            )
            return int(plan["id"])
        cur = conn.execute(
            """
            insert into plans
              (name, enabled, schedule, backup_root, storage_json, include_json,
               retention_json, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan["name"],
                int(plan.get("enabled", False)),
                plan.get("schedule", ""),
                plan["backup_root"],
                dumps(plan.get("storage", [])),
                dumps(plan.get("include", {})),
                dumps(plan.get("retention", {})),
                now,
                now,
            ),
        )
        return int(cur.lastrowid)


def delete_plan(plan_id: int) -> None:
    with connect() as conn:
        conn.execute("delete from plans where id = ?", (plan_id,))


def snapshot_dirs(root: str | Path) -> list[Path]:
    path = Path(root)
    if not path.exists():
        return []
    return sorted(
        [item for item in path.iterdir() if item.is_dir() and item.name != "latest"],
        key=lambda p: p.name,
        reverse=True,
    )


def save_server_profile(profile: dict[str, Any]) -> int:
    now = utc_now()
    name = profile["name"]
    hostname = profile.get("hostname", name)
    with connect() as conn:
        row = conn.execute("select id from server_profiles where name = ?", (name,)).fetchone()
        if row:
            conn.execute(
                """
                update server_profiles
                   set hostname = ?, profile_json = ?, updated_at = ?
                 where id = ?
                """,
                (hostname, dumps(profile), now, row["id"]),
            )
            return int(row["id"])
        cur = conn.execute(
            """
            insert into server_profiles (name, hostname, profile_json, created_at, updated_at)
            values (?, ?, ?, ?, ?)
            """,
            (name, hostname, dumps(profile), now, now),
        )
        return int(cur.lastrowid)


def list_server_profiles() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("select * from server_profiles order by name").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["profile"] = loads(item.pop("profile_json"), {})
        result.append(item)
    return result
