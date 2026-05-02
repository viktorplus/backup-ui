# Roadmap Product-Версии Backup UI

Этот файл фиксирует рекомендации для будущего внедрения. Пункты ниже не реализованы полностью и требуют отдельного планирования, тестов и проверки безопасности.

## 1. Авторизация UI

Минимальная реализация:

- логин и пароль через переменные окружения или конфигурационный файл;
- пароль хранить только как hash;
- session cookie подписывать отдельным `BACKUP_UI_SESSION_SECRET`;
- без авторизации открывать только `/login` и health endpoint.

Пример переменных:

```text
BACKUP_UI_ADMIN_USER=admin
BACKUP_UI_ADMIN_PASSWORD_HASH=...
BACKUP_UI_SESSION_SECRET=...
```

Дальше можно добавить OIDC, GitHub OAuth, Google Workspace или LDAP.

## 2. Audit Log

Нужен журнал всех действий:

- кто;
- когда;
- с какого IP;
- что сделал;
- над каким объектом;
- результат;
- ошибка, если была.

Примеры событий:

```text
login_success
login_failed
backup_plan_created
backup_plan_updated
backup_started
backup_finished
restore_requested
restore_confirmed
retention_dry_run
retention_applied
server_profile_saved
directory_viewed
database_tables_viewed
```

Audit log не должен хранить пароли, токены, содержимое файлов и строки из баз.

## 3. Роли

Базовые роли:

```text
read-only
backup
restore
```

`read-only`:

- смотреть сервер;
- смотреть процессы;
- смотреть директории;
- смотреть список баз и таблиц;
- смотреть планы;
- смотреть копии;
- смотреть audit log.

`backup`:

- все возможности `read-only`;
- создавать и редактировать backup-планы;
- запускать backup;
- делать dry-run retention;
- применять retention, если это разрешено политикой.

`restore`:

- все возможности `backup`;
- запускать restore;
- включать restore mode;
- подтверждать опасные действия.

Для restore нужно двойное подтверждение:

```text
1. выбрать snapshot
2. выбрать компонент
3. выбрать target
4. ввести ВОССТАНОВИТЬ
5. сделать safety backup текущего target
6. только потом restore
```

## 4. Adapters Для Redis, MongoDB, SQLite

Нужен общий интерфейс адаптера:

```python
class DatabaseAdapter:
    def detect(container) -> bool
    def list_databases(container) -> list
    def list_objects(container, database) -> list
    def backup(container, database, target) -> BackupResult
    def restore(container, database, dump) -> RestoreResult
```

Redis:

- обнаружение по image/name `redis`;
- просмотр через `INFO`, `DBSIZE`, `CONFIG GET dir`, `CONFIG GET dbfilename`;
- backup через `BGSAVE` и копирование `dump.rdb`, либо `redis-cli --rdb`;
- restore через остановку Redis, замену RDB/AOF и запуск обратно.

MongoDB:

- обнаружение по `mongo`, `mongodb`;
- просмотр через `mongosh`;
- backup через `mongodump --archive --gzip`;
- restore через `mongorestore --archive --gzip`;
- большие коллекции показывать отдельно.

SQLite:

- обнаружение файлов `.sqlite`, `.sqlite3`, `.db` в project path;
- просмотр таблиц через `sqlite3`;
- backup через `sqlite3 file ".backup backup.sqlite"` или копию при остановленном сервисе;
- restore через safety copy и замену файла.

Для SQLite нельзя просто копировать активную базу, если приложение в нее пишет.

## 5. Шифрование Backup-Архивов

Рекомендуемый вариант: `age`.

Как должно работать:

- в настройках storage указывается public key;
- backup создает архив;
- архив шифруется;
- plaintext удаляется, если включена политика удаления;
- checksum считается по зашифрованному `.age`;
- restore требует private key.

Пример:

```bash
age -r PUBLIC_KEY -o files.tar.gz.age files.tar.gz
```

Private key не хранить в UI по умолчанию. Для restore лучше загружать ключ временно или монтировать secret-файл.

## 6. Проверка Restore В Sandbox

Цель: проверить, что backup восстанавливаемый, без изменения production.

Файлы:

- создать временный каталог в `/var/lib/backup-ui/sandbox`;
- распаковать архив;
- проверить checksum;
- показать top-level список файлов и размер.

PostgreSQL:

- поднять временный контейнер PostgreSQL той же major-версии;
- создать временную базу;
- выполнить `pg_restore`;
- проверить список таблиц;
- удалить контейнер.

MySQL/MariaDB:

- поднять временный контейнер нужного engine;
- импортировать dump;
- проверить `information_schema.tables`.

Redis:

- поднять временный Redis с копией RDB/AOF;
- проверить `DBSIZE`.

MongoDB:

- поднять временный Mongo;
- выполнить `mongorestore`;
- проверить коллекции.

В UI нужна отдельная кнопка `Проверить restore`. Это не настоящий restore.

## 7. Health Checks И Алерты

Read-only проверки:

- свободное место;
- доступность backup root;
- доступность docker socket;
- состояние контейнера `backup-ui`;
- возраст последнего успешного backup;
- ошибки последних jobs;
- доступность SSH storage;
- размер очереди и логов;
- overdue retention.

Примеры правил:

```text
disk_free_percent < 15%
disk_free_gb < 10
last_successful_backup_age > 24h
last_job_status == failed
backup_root_not_writable
ssh_storage_unreachable
```

Каналы алертов:

- UI banner;
- email;
- webhook;
- Telegram;
- Slack;
- ntfy.

Начать лучше с:

```text
UI banner + webhook + email
```

## Рекомендуемый Порядок Внедрения

1. Авторизация UI.
2. Audit log.
3. Роли.
4. Health checks.
5. Шифрование backup-архивов.
6. Sandbox restore.
7. Redis, MongoDB, SQLite adapters.
8. Расширенные алерты.

Без авторизации, audit log и ролей опасно расширять restore и adapters.
