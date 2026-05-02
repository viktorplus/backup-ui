from __future__ import annotations

import shutil
import subprocess
import tarfile
import threading
from pathlib import Path
from typing import Any

from . import state


def start_restore_job(snapshot: str, component: str, mode: str, target: str, confirmation: str) -> int:
    job_id = state.create_job(None, "restore", f"Восстановление {component} из {snapshot}")
    thread = threading.Thread(
        target=_run_restore,
        args=(job_id, snapshot, component, mode, target, confirmation),
        daemon=True,
    )
    thread.start()
    return job_id


def _run_restore(job_id: int, snapshot: str, component: str, mode: str, target: str, confirmation: str) -> None:
    try:
        if confirmation != "ВОССТАНОВИТЬ":
            raise RuntimeError("Подтверждение не совпадает. Восстановление отменено.")

        component_dir = Path(snapshot) / component
        if not component_dir.exists():
            raise RuntimeError(f"Компонент не найден: {component_dir}")

        state.add_log(job_id, f"Начинаю восстановление компонента: {component}")
        if mode == "files":
            archive = component_dir / "files.tar.gz"
            if not archive.exists():
                raise RuntimeError("Архив файлов не найден")
            target_path = Path(target)
            target_path.mkdir(parents=True, exist_ok=True)
            with tarfile.open(archive, "r:gz") as tar:
                tar.extractall(target_path)
            state.add_log(job_id, f"Файлы распакованы в: {target_path}")
        elif mode == "database":
            dumps = list(component_dir.glob("*.dump"))
            if not dumps:
                raise RuntimeError("Dump базы не найден")
            if ":" not in target:
                raise RuntimeError("Для базы target должен быть формата container:database:user")
            parts = target.split(":")
            container, db = parts[0], parts[1]
            user = parts[2] if len(parts) > 2 else "signal"
            state.add_log(job_id, f"Восстанавливаю базу {db} в контейнере {container}")
            with dumps[0].open("rb") as fh:
                proc = subprocess.run(
                    ["docker", "exec", "-i", container, "pg_restore", "-U", user, "-d", db, "--clean", "--if-exists"],
                    stdin=fh,
                    stderr=subprocess.PIPE,
                    check=False,
                )
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr.decode("utf-8", "replace"))
        else:
            raise RuntimeError(f"Неизвестный режим восстановления: {mode}")

        state.finish_job(job_id, "success", "Восстановление завершено")
    except Exception as exc:
        state.add_log(job_id, f"Ошибка восстановления: {exc}", "error")
        state.finish_job(job_id, "failed", str(exc))

