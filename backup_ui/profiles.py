from __future__ import annotations

from typing import Any

from .discovery import discover_docker_containers
from .server_status import server_overview


def current_server_profile() -> dict[str, Any]:
    overview = server_overview()
    db_containers = []
    for item in discover_docker_containers():
        text = f"{item.get('Names', '')} {item.get('Image', '')}".lower()
        if any(marker in text for marker in ["postgres", "postgis", "mysql", "mariadb"]):
            db_containers.append(
                {
                    "name": item.get("Names", ""),
                    "image": item.get("Image", ""),
                    "state": item.get("State", ""),
                    "status": item.get("Status", ""),
                }
            )
    return {
        "name": overview["hostname"],
        "hostname": overview["hostname"],
        "ips": overview["ips"],
        "os": overview["os"],
        "cpu": overview["cpu"],
        "memory": overview["memory"],
        "disk_free": overview["disks"][0]["free"] if overview["disks"] else "",
        "backup_roots": [disk["mount"] for disk in overview["disks"]],
        "database_containers": db_containers,
        "notes": "Профиль собран автоматически из read-only данных сервера.",
    }
