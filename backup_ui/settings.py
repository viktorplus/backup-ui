from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "Backup UI"
BASE_DIR = Path(os.environ.get("BACKUP_UI_HOME", "/var/lib/backup-ui"))
STATE_DB = Path(os.environ.get("BACKUP_UI_DB", BASE_DIR / "state.db"))
CONFIG_PATH = Path(os.environ.get("BACKUP_UI_CONFIG", BASE_DIR / "config.json"))
DEFAULT_BACKUP_ROOT = Path(os.environ.get("BACKUP_UI_BACKUP_ROOT", "/opt/backups/projects"))
LOG_PATH = Path(os.environ.get("BACKUP_UI_LOG", "/var/log/backup-ui.log"))
HOST_ROOT = Path(os.environ.get("BACKUP_UI_HOST_ROOT", "/"))
HOST_FS = Path(os.environ.get("BACKUP_UI_HOST_FS", "/host/root"))
HOST_OPT = Path(os.environ.get("BACKUP_UI_HOST_OPT", "/opt"))
HOST_ETC = Path(os.environ.get("BACKUP_UI_HOST_ETC", "/etc"))


def ensure_dirs() -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
