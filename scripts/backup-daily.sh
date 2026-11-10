#!/bin/sh
set -eu
: "${BACKUP_DIR:?BACKUP_DIR is not set}"
APP_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON="${PYTHON:-$APP_DIR/.venv/bin/python}"
cd "$APP_DIR"
exec "$PYTHON" -m scripts.backup_daily
