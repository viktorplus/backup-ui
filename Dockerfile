FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BACKUP_UI_HOME=/var/lib/backup-ui \
    BACKUP_UI_BACKUP_ROOT=/backups/projects \
    BACKUP_UI_HOST_FS=/host/root \
    BACKUP_UI_HOST_OPT=/host/opt \
    BACKUP_UI_HOST_ETC=/host/etc

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       docker.io \
       openssh-client \
       rsync \
       ca-certificates \
       gzip \
       tar \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt pyproject.toml ./
COPY backup_ui ./backup_ui
RUN pip install --no-cache-dir -U pip \
    && pip install --no-cache-dir -r requirements.txt

EXPOSE 8090
CMD ["uvicorn", "backup_ui.app:app", "--host", "0.0.0.0", "--port", "8090"]
