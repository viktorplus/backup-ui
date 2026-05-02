from __future__ import annotations

import os
import ipaddress
import re
import shutil
import stat
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from .settings import DEFAULT_BACKUP_ROOT, HOST_FS


PROC_ROOT = HOST_FS / "proc"


def server_overview() -> dict[str, Any]:
    mem = _meminfo()
    load = _loadavg()
    disks = [
        _disk_row("/", HOST_FS),
        _disk_row("/opt", HOST_FS / "opt"),
        _disk_row("/opt/backups", HOST_FS / "opt" / "backups"),
        _disk_row(str(DEFAULT_BACKUP_ROOT), DEFAULT_BACKUP_ROOT),
    ]
    processes = list_processes(limit=1_000_000)
    return {
        "hostname": _host_name(),
        "os": _os_release(),
        "ips": _local_ips(),
        "cpu": _cpuinfo(),
        "memory": mem,
        "load": load,
        "uptime": _uptime(),
        "disks": disks,
        "process_count": len(processes),
        "top_processes": processes[:12],
    }


def list_processes(limit: int = 200) -> list[dict[str, Any]]:
    rows = []
    if not PROC_ROOT.exists():
        return rows

    for proc_dir in PROC_ROOT.iterdir():
        if not proc_dir.name.isdigit():
            continue
        item = _process_row(proc_dir)
        if item:
            rows.append(item)

    rows.sort(key=lambda x: (x["rss_bytes"], x["cpu_seconds"]), reverse=True)
    return rows[:limit]


def directory_listing(display_path: str | None) -> dict[str, Any]:
    display = _clean_display_path(display_path or "/")
    items: list[dict[str, Any]] = []
    error = ""

    try:
        real = _to_host_path(display)
        entries = sorted(real.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:500]
        for entry in entries:
            try:
                st = entry.lstat()
            except OSError:
                continue
            child_display = _join_display(display, entry.name)
            items.append(
                {
                    "name": entry.name,
                    "path": child_display,
                    "kind": _entry_kind(entry, st),
                    "size": human_size(st.st_size),
                    "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "mode": stat.filemode(st.st_mode),
                    "can_open": entry.is_dir() and not entry.is_symlink(),
                }
            )
    except Exception as exc:
        error = str(exc)
        real = HOST_FS / display.lstrip("/")

    parent = "/" if display == "/" else str(PurePosixPath(display).parent)
    return {
        "display_path": display,
        "real_path": str(real),
        "parent": parent,
        "items": items,
        "error": error,
        "truncated": len(items) >= 500,
    }


def _process_row(proc_dir: Path) -> dict[str, Any] | None:
    try:
        status = _parse_key_value(proc_dir / "status")
        stat_text = (proc_dir / "stat").read_text(encoding="utf-8", errors="replace")
        cmdline = (proc_dir / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace").strip()
    except OSError:
        return None

    stat_parts = _split_proc_stat(stat_text)
    state = status.get("State", "").split("\t")[-1] if status.get("State") else ""
    rss_kb = _kb_value(status.get("VmRSS", "0 kB"))
    cpu_seconds = 0.0
    if len(stat_parts) > 15:
        ticks = os.sysconf(os.sysconf_names.get("SC_CLK_TCK", "SC_CLK_TCK"))
        cpu_seconds = (int(stat_parts[13]) + int(stat_parts[14])) / max(ticks, 1)

    return {
        "pid": proc_dir.name,
        "ppid": status.get("PPid", ""),
        "user": status.get("Uid", "").split("\t")[0],
        "name": status.get("Name", stat_parts[1] if len(stat_parts) > 1 else ""),
        "state": state,
        "rss_bytes": rss_kb * 1024,
        "rss": human_size(rss_kb * 1024),
        "cpu_seconds": round(cpu_seconds, 1),
        "cmd": cmdline or status.get("Name", ""),
    }


def _split_proc_stat(text: str) -> list[str]:
    match = re.match(r"^(\d+) \((.*)\) ([A-Z]) (.*)$", text.strip())
    if not match:
        return text.split()
    return [match.group(1), match.group(2), match.group(3), *match.group(4).split()]


def _meminfo() -> dict[str, Any]:
    data = _parse_key_value(PROC_ROOT / "meminfo")
    total = _kb_value(data.get("MemTotal", "0 kB")) * 1024
    available = _kb_value(data.get("MemAvailable", "0 kB")) * 1024
    used = max(total - available, 0)
    return {
        "total": human_size(total),
        "used": human_size(used),
        "available": human_size(available),
        "used_percent": round((used / total * 100), 1) if total else 0,
    }


def _loadavg() -> dict[str, Any]:
    text = _read_first(PROC_ROOT / "loadavg")
    parts = text.split()
    return {
        "one": parts[0] if len(parts) > 0 else "0",
        "five": parts[1] if len(parts) > 1 else "0",
        "fifteen": parts[2] if len(parts) > 2 else "0",
        "running": parts[3] if len(parts) > 3 else "",
    }


def _uptime() -> dict[str, Any]:
    text = _read_first(PROC_ROOT / "uptime")
    seconds = float(text.split()[0]) if text else 0
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    return {"seconds": int(seconds), "human": f"{days} д {hours} ч {minutes} мин"}


def _cpuinfo() -> dict[str, Any]:
    path = PROC_ROOT / "cpuinfo"
    model = ""
    cores = 0
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("processor"):
                cores += 1
            if not model and line.startswith("model name"):
                model = line.split(":", 1)[1].strip()
    except OSError:
        cores = os.cpu_count() or 0
    return {"model": model or "unknown", "cores": cores}


def _disk_row(label: str, path: Path) -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(path)
        used = usage.total - usage.free
        return {
            "mount": label,
            "path": str(path),
            "total": human_size(usage.total),
            "used": human_size(used),
            "free": human_size(usage.free),
            "used_percent": round(used / usage.total * 100, 1) if usage.total else 0,
        }
    except OSError as exc:
        return {"mount": label, "path": str(path), "total": "-", "used": "-", "free": "-", "used_percent": 0, "error": str(exc)}


def _os_release() -> str:
    data = _parse_key_value(HOST_FS / "etc" / "os-release")
    return data.get("PRETTY_NAME", data.get("NAME", "unknown")).strip('"')


def _host_name() -> str:
    short_name = _read_first(HOST_FS / "etc" / "hostname") or _read_first(Path("/etc/hostname"))
    hosts = HOST_FS / "etc" / "hosts"
    if short_name and hosts.exists():
        try:
            for raw in hosts.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw.split("#", 1)[0].strip()
                if not line:
                    continue
                parts = line.split()
                names = parts[1:]
                if short_name in names:
                    for name in names:
                        if "." in name and name not in {"localhost.localdomain"}:
                            return name
        except OSError:
            pass
    return short_name or "unknown"


def _local_ips() -> list[str]:
    configured = _configured_ips()
    if configured:
        return configured

    ips: list[str] = []
    path = PROC_ROOT / "net" / "fib_trie"
    previous = ""
    try:
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            candidate = raw.strip().split()[-1] if raw.strip() else ""
            if re.match(r"^\d+\.\d+\.\d+\.\d+$", candidate):
                previous = candidate
            if "host LOCAL" in raw and previous and not previous.startswith("127."):
                if previous not in ips:
                    ips.append(previous)
    except OSError:
        pass
    return ips[:20]


def _configured_ips() -> list[str]:
    ips: list[str] = []
    candidates = []
    for root in [HOST_FS / "etc" / "netplan", HOST_FS / "etc" / "systemd" / "network"]:
        if root.exists():
            candidates.extend(path for path in root.rglob("*") if path.is_file())
    interfaces = HOST_FS / "etc" / "network" / "interfaces"
    if interfaces.exists():
        candidates.append(interfaces)
    interfaces_d = HOST_FS / "etc" / "network" / "interfaces.d"
    if interfaces_d.exists():
        candidates.extend(path for path in interfaces_d.rglob("*") if path.is_file())

    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in re.finditer(r"(?<![\w:])([0-9a-fA-F:.]+)/(?:\d{1,3})(?![\w:])", text):
            raw = match.group(1)
            try:
                ip = str(ipaddress.ip_address(raw))
            except ValueError:
                continue
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
        for match in re.finditer(r"^\s*address\s+([0-9a-fA-F:.]+)\s*$", text, flags=re.MULTILINE):
            raw = match.group(1)
            try:
                ip = str(ipaddress.ip_address(raw))
            except ValueError:
                continue
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)

    def rank(ip: str) -> tuple[int, str]:
        parsed = ipaddress.ip_address(ip)
        return (0 if parsed.is_global else 1, ip)

    return sorted(ips, key=rank)


def _parse_key_value(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                data[key] = value.strip()
            elif "=" in line:
                key, value = line.split("=", 1)
                data[key] = value.strip().strip('"')
    except OSError:
        pass
    return data


def _kb_value(value: str) -> int:
    match = re.search(r"(\d+)", value)
    return int(match.group(1)) if match else 0


def _read_first(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[0].strip()
    except (OSError, IndexError):
        return ""


def _clean_display_path(path: str) -> str:
    cleaned = "/" + path.strip().replace("\\", "/").lstrip("/")
    normalized = PurePosixPath(cleaned)
    parts = [part for part in normalized.parts if part not in {"", "/", "."}]
    safe: list[str] = []
    for part in parts:
        if part == "..":
            if safe:
                safe.pop()
        else:
            safe.append(part)
    return "/" + "/".join(safe) if safe else "/"


def _to_host_path(display_path: str) -> Path:
    relative = display_path.lstrip("/")
    candidate = (HOST_FS / relative).resolve()
    root = HOST_FS.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Путь выходит за пределы host root")
    return candidate


def _join_display(parent: str, child: str) -> str:
    if parent == "/":
        return f"/{child}"
    return f"{parent.rstrip('/')}/{child}"


def _entry_kind(path: Path, st: os.stat_result) -> str:
    if stat.S_ISLNK(st.st_mode):
        return "symlink"
    if path.is_dir():
        return "dir"
    if path.is_file():
        return "file"
    return "other"


def human_size(size: int) -> str:
    value = float(size)
    for unit in ["B", "K", "M", "G", "T"]:
        if value < 1024 or unit == "T":
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{size}B"
