from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from . import state
from .storage import sync_to_targets


def start_backup_job(plan: dict[str, Any]) -> int:
    job_id = state.create_job(plan.get("id"), "backup", f"Запуск backup-плана: {plan['name']}")
    thread = threading.Thread(target=_run_backup, args=(job_id, plan), daemon=True)
    thread.start()
    return job_id


def _log(job_id: int, message: str, level: str = "info") -> None:
    state.add_log(job_id, message, level)


def _run_backup(job_id: int, plan: dict[str, Any]) -> None:
    try:
        root = Path(plan["backup_root"])
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        snapshot = root / timestamp
        snapshot.mkdir(parents=True, exist_ok=False)

        _log(job_id, f"Создан каталог snapshot: {snapshot}")
        metadata = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "plan": plan,
            "projects": [],
            "databases": [],
            "configs": [],
            "comments": ["Backup создан через Backup UI. Все действия записаны на русском языке."],
        }

        include = plan.get("include", {})
        for project in include.get("projects", []):
            _backup_path(job_id, snapshot, project["name"], project["path"], "project")
            metadata["projects"].append(project)

        for config in include.get("configs", []):
            _backup_path(job_id, snapshot, config["name"], config["path"], "config")
            metadata["configs"].append(config)

        for db in include.get("databases", []):
            if db.get("skip"):
                _write_text(
                    snapshot / _safe_name(db["name"]) / f"SKIPPED_DATABASE_{db['name']}.txt",
                    f"База {db['name']} пропущена по настройке плана.\n",
                )
                _log(job_id, f"База пропущена: {db['name']}")
                continue
            _dump_database(job_id, snapshot, db)
            metadata["databases"].append(db)

        _write_text(snapshot / "metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
        _write_checksums(snapshot)
        (root / "latest").unlink(missing_ok=True)
        try:
            (root / "latest").symlink_to(snapshot, target_is_directory=True)
        except OSError:
            _write_text(root / "LATEST.txt", str(snapshot))

        sync_to_targets(snapshot, plan.get("storage", []), lambda msg: _log(job_id, msg))
        state.finish_job(job_id, "success", "Backup завершен успешно", str(snapshot))
    except Exception as exc:
        _log(job_id, f"Ошибка backup: {exc}", "error")
        state.finish_job(job_id, "failed", str(exc))


def _backup_path(job_id: int, snapshot: Path, name: str, source: str, kind: str) -> None:
    safe = _safe_name(name)
    dest = snapshot / safe
    dest.mkdir(parents=True, exist_ok=True)
    source_path = Path(source)
    _write_text(dest / "source_path.txt", source)
    _write_restore_note(dest / "RESTORE.md", safe, kind)

    if not source_path.exists():
        _write_text(dest / "MISSING.txt", f"Путь не найден: {source}\n")
        _log(job_id, f"Путь не найден, пропускаю: {source}", "warning")
        return

    archive = dest / "files.tar.gz"
    _log(job_id, f"Архивирую {kind}: {source}")
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(source_path, arcname=source_path.name, recursive=True)


def _dump_database(job_id: int, snapshot: Path, db: dict[str, Any]) -> None:
    safe = _safe_name(db["name"])
    dest = snapshot / safe
    dest.mkdir(parents=True, exist_ok=True)
    dump_path = dest / f"{safe}.dump"
    container = db["container"]
    user = db.get("user") or "signal"

    _write_restore_note(dest / "RESTORE.md", safe, "database")
    _log(job_id, f"Создаю dump базы {db['name']} из контейнера {container}")
    with dump_path.open("wb") as fh:
        proc = subprocess.run(
            ["docker", "exec", container, "pg_dump", "-U", user, "-d", db["name"], "-Fc", "-Z6"],
            stdout=fh,
            stderr=subprocess.PIPE,
            check=False,
        )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace"))


def _write_restore_note(path: Path, name: str, kind: str) -> None:
    text = f"""# Восстановление {name}

Тип: {kind}

Перед восстановлением остановите сервис проекта и сделайте safety backup текущего состояния.

Файлы:

```bash
tar -xzf files.tar.gz -C /tmp/restore-check
```

База PostgreSQL, если рядом есть `.dump`:

```bash
docker exec -i CONTAINER pg_restore -U USER -d DB --clean --if-exists < DB.dump
```

Автоматическое восстановление через UI требует подтверждения словом `ВОССТАНОВИТЬ`.
"""
    _write_text(path, text)


def _write_checksums(snapshot: Path) -> None:
    rows = []
    for path in sorted(p for p in snapshot.rglob("*") if p.is_file() and p.name != "SHA256SUMS"):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(f"{digest}  {path.relative_to(snapshot).as_posix()}")
    _write_text(snapshot / "SHA256SUMS", "\n".join(rows) + "\n")
    total = sum(p.stat().st_size for p in snapshot.rglob("*") if p.is_file())
    _write_text(snapshot / "SIZE.txt", f"{total} bytes\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in name).strip("-") or "item"


def delete_snapshot(path: Path) -> None:
    if path.exists() and path.is_dir():
        shutil.rmtree(path)

