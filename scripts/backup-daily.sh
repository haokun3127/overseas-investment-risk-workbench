#!/bin/sh
# Daily backup of the database and uploads (run by rag-backup.timer). Keeps the newest KEEP_DAYS backups.
# Needs DATA_DIR and BACKUP_DIR from the service environment file; secrets in that file are not copied.
set -eu
: "${BACKUP_DIR:?BACKUP_DIR is not set}"
KEEP_DAYS="${KEEP_DAYS:-14}"
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-$APP_DIR/.venv/bin/python}"
mkdir -p "$BACKUP_DIR" && chmod 700 "$BACKUP_DIR"
target="$BACKUP_DIR/$(date +%Y%m%d-%H%M%S)"
cd "$APP_DIR" && "$PYTHON" -m scripts.manage backup --destination "$target"
"$PYTHON" - "$target/risk.db" <<'PY'
import sqlite3,sys
if sqlite3.connect(sys.argv[1]).execute('PRAGMA integrity_check').fetchone()[0]!='ok':sys.exit('backup integrity check failed')
PY
ls -1d "$BACKUP_DIR"/[0-9]*-[0-9]* 2>/dev/null | sort | head -n "-$KEEP_DAYS" | while read -r old; do rm -rf -- "$old"; done
