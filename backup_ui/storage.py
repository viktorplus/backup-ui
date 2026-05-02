from __future__ import annotations

from pathlib import Path

from .commands import run


def sync_to_targets(snapshot: Path, targets: list[dict], log) -> None:
    for target in targets:
        if not target.get("enabled", True):
            continue
        kind = target.get("type", "local")
        if kind == "local":
            root = Path(target["path"])
            root.mkdir(parents=True, exist_ok=True)
            destination = root / snapshot.name
            if destination.resolve() == snapshot.resolve():
                log(f"Локальное хранилище уже указывает на snapshot: {destination}")
                continue
            log(f"Копирую snapshot в локальное хранилище: {destination}")
            result = run(["cp", "-a", str(snapshot), str(destination)], timeout=3600)
            if result.code != 0:
                raise RuntimeError(f"Ошибка локального копирования: {result.stderr}")
        elif kind == "ssh":
            remote = target["remote"]
            path = target["path"].rstrip("/")
            log(f"Копирую snapshot на SSH-хранилище: {remote}:{path}")
            run(["ssh", remote, "mkdir", "-p", path], timeout=60)
            result = run(["rsync", "-a", "--delete", f"{snapshot}/", f"{remote}:{path}/{snapshot.name}/"], timeout=7200)
            if result.code != 0:
                raise RuntimeError(f"Ошибка SSH/rsync копирования: {result.stderr}")
        else:
            raise RuntimeError(f"Неизвестный тип хранилища: {kind}")

