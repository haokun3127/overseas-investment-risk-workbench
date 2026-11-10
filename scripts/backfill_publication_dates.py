"""Audit and backfill only evidenced publication dates; apply with the service stopped."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

from app.publication import from_text, from_snapshot, from_disclosure_url


def candidate(data, row, cache=None):
    path = (data / 'uploads' / row['file_path']).resolve() if row.get('file_path') else None
    if path and path.is_relative_to((data / 'uploads').resolve()) and path.is_file() and path.suffix.lower() in {'.html', '.htm', '.pdf'} and path.stat().st_size <= 16 * 1024 * 1024:
        content_type = 'application/pdf' if path.suffix.lower() == '.pdf' else 'text/html'
        cache = cache if cache is not None else {}
        key = (str(path), row['body'] if content_type == 'text/html' else '')
        if key not in cache:
            cache[key] = from_snapshot(path.read_bytes(), content_type, row['body'])
        result = cache[key]
    else:
        result = from_text(row['body'])
    if not result[0]:
        result = from_disclosure_url(row.get('url'))
    return result


def plan(data):
    data = Path(data).resolve()
    items = []
    cache = {}
    with sqlite3.connect(f'file:{data / "risk.db"}?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        profiles = {row[0] for row in db.execute('SELECT document_id FROM companies WHERE document_id IS NOT NULL')}
        for table in ('documents', 'web_pages'):
            rows = db.execute(f"SELECT * FROM {table} WHERE date='' ORDER BY id").fetchall()
            for raw in rows:
                row = dict(raw)
                if table == 'documents':
                    if row['id'] in profiles or '事实摘录' in row['source'] or row.get('quarantined_at'):
                        continue
                else:
                    row['file_path'] = row['snapshot']
                value, source, evidence = candidate(data, row, cache)
                if value:
                    path = (data / 'uploads' / row['file_path']).resolve() if row.get('file_path') else None
                    snapshot_hash = hashlib.sha256(path.read_bytes()).hexdigest() if path and path.is_relative_to((data / 'uploads').resolve()) and path.is_file() else ''
                    items.append({'table': table, 'id': row['id'], 'title': row['title'],
                                  'date': value, 'date_source': source, 'evidence': evidence,
                                  'snapshot_sha256': snapshot_hash,
                                  'body_sha256': hashlib.sha256(row['body'].encode()).hexdigest()})
    return {'schema': 1, 'data_dir': str(data), 'items': items}


def apply(data, report, backup):
    data, backup = Path(data).resolve(), Path(backup).resolve()
    if backup.exists() or backup == data / 'risk.db':
        raise ValueError('Backup must be a new file, not the live database')
    fresh = plan(data)
    if fresh != report:
        raise ValueError('Sources changed since audit; regenerate the plan')
    backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(data / 'risk.db') as db, sqlite3.connect(backup) as copy:
        db.backup(copy)
    backup.chmod(0o600)
    with sqlite3.connect(data / 'risk.db') as db:
        db.execute('BEGIN IMMEDIATE')
        for item in report['items']:
            table = item['table']
            assert table in ('documents', 'web_pages')
            assignment, args = 'date=?,date_source=?', [item['date'], item['date_source']]
            changed = db.execute(f"UPDATE {table} SET {assignment} WHERE id=? AND date=''", (*args, item['id'])).rowcount
            if changed != 1:
                raise ValueError('Date changed during apply; transaction cancelled')
    return len(report['items'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup')
    args = parser.parse_args()
    path = Path(args.report)
    if args.apply:
        assert args.backup
        count = apply(args.data, json.loads(path.read_text(encoding='utf-8')), args.backup)
        print(json.dumps({'applied': count, 'backup': args.backup}))
    else:
        result = plan(args.data)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'candidates': len(result['items']), 'report': str(path)}))
