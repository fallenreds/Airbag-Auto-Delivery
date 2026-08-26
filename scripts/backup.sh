#!/bin/sh
# Резервная копия боевых данных.
#
# База и media лежат не в docker-volume, а прямо в рабочей копии репозитория
# (`backend/db.sqlite3`, `backend/media/`), и оба пути в .gitignore. То есть
# данные существуют ровно в одном экземпляре: `git clean -xdf` на сервере
# сотрёт и базу, и платёжные документы клиентов одной командой.
#
# Копию базы снимаем через `sqlite3 .backup`, а не `cp`: файл пишется живым
# приложением, и обычное копирование может поймать его на середине транзакции.
#
# Ставится в cron, например ежедневно в 4 утра:
#   0 4 * * * /root/Airbag-Auto-Delivery/scripts/backup.sh >> /var/log/airbag-backup.log 2>&1
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${AIRBAG_BACKUP_DIR:-/var/backups/airbag}"
KEEP_DAYS="${AIRBAG_BACKUP_KEEP_DAYS:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$DEST"

echo "[backup] $STAMP → $DEST"

sqlite3 "$ROOT/backend/db.sqlite3" ".backup '$DEST/db-$STAMP.sqlite3'"
gzip -f "$DEST/db-$STAMP.sqlite3"

tar -czf "$DEST/media-$STAMP.tar.gz" -C "$ROOT/backend" media

# props.json бот не читает (реквизиты живут в модели BankDetails), но пока
# файл на сервере есть — пусть попадает в копию вместе с остальным.
[ -f "$ROOT/props.json" ] && cp "$ROOT/props.json" "$DEST/props-$STAMP.json"

find "$DEST" -type f -mtime "+$KEEP_DAYS" -delete

echo "[backup] готово:"
ls -la "$DEST" | tail -5
