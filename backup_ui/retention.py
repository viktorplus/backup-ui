from __future__ import annotations

import shutil
from pathlib import Path

from .state import snapshot_dirs


def plan_retention(root: str, rules: dict) -> dict:
    snapshots = snapshot_dirs(root)
    keep_last = int(rules.get("keep_last", 0) or 0)
    max_total_gb = float(rules.get("max_total_gb", 0) or 0)
    protected = set(rules.get("pinned", []))

    keep = set(p.name for p in snapshots[:keep_last])
    keep.update(protected)
    delete: list[Path] = [p for p in snapshots if p.name not in keep]

    if max_total_gb > 0:
        total = sum(_dir_size(p) for p in snapshots)
        max_bytes = int(max_total_gb * 1024 * 1024 * 1024)
        for snap in reversed(snapshots):
            if total <= max_bytes:
                break
            if snap.name in keep or snap in delete:
                continue
            delete.append(snap)
            total -= _dir_size(snap)

    return {
        "keep": [p.name for p in snapshots if p not in delete],
        "delete": [{"name": p.name, "path": str(p), "size": _dir_size(p)} for p in delete],
    }


def apply_retention(root: str, rules: dict, dry_run: bool = True) -> dict:
    result = plan_retention(root, rules)
    if not dry_run:
        for item in result["delete"]:
            path = Path(item["path"])
            if path.exists() and path.is_dir() and path.parent == Path(root):
                shutil.rmtree(path)
    return result


def _dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())

