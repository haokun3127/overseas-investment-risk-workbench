"""Verified daily backup with an atomic, credential-free status marker."""
import json
import os
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from app.config import Settings
from scripts.manage import backup


def run(data, destination, keep=14):
    data, destination = Path(data).resolve(), Path(destination).resolve()
    if destination == data or data in destination.parents or destination in data.parents:
        raise ValueError('Backup and data directories must be separate')
    if keep < 0:
        raise ValueError('KEEP_DAYS must be non-negative; zero disables pruning')
    destination.mkdir(parents=True, exist_ok=True)
    destination.chmod(0o700)
    status = destination / 'status.json'
    def record(state, **extra):
        tmp = destination / 'status.next.json'
        tmp.write_text(json.dumps({'state':state,'checked_at':datetime.now(timezone.utc).isoformat(),**extra}), encoding='utf-8')
        tmp.chmod(0o600)
        tmp.replace(status)
    record('running')
    target = destination / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    try:
        backup(data, target)
        with sqlite3.connect(f'file:{target / "risk.db"}?mode=ro', uri=True) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Backup integrity check failed')
        completed = sorted(p for p in destination.iterdir() if p.is_dir() and not p.is_symlink()
                           and re.fullmatch(r'\d{8}-\d{6}(?:-\d{6})?', p.name)
                           and (p/'backup.json').is_file() and (p/'risk.db').is_file() and (p/'uploads').is_dir())
        if keep:
            for old in completed[:-keep]:
                if old.resolve().parent != destination or old == target or old.is_symlink():
                    raise ValueError('Unsafe retention target')
                shutil.rmtree(old)
        record('completed', backup=target.name)
        return target
    except Exception as error:
        record('failed', error=f'{type(error).__name__}: {error}')
        raise


if __name__ == '__main__':
    os.umask(0o077)
    settings = Settings()
    if not settings.backup_dir:
        raise SystemExit('BACKUP_DIR is not set')
    run(settings.data_dir, settings.backup_dir, int(os.environ.get('KEEP_DAYS','14')))
