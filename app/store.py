import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

DEFAULT_RULES = {
    'version': 'draft-1', 'confirmed': False,
    'categories': ['政策与监管', '法律与合规', '供应链与物流', '劳工与社会', '金融与汇率', '环境与安全'],
    'levels': {'red': '高风险：可能导致重大损失或业务中断，需优先复核。', 'orange': '中风险：可能影响经营成本或进度，需制定应对措施。', 'yellow': '一般关注风险：影响尚有限或需要持续关注。'},
    'notes': '初始示例规则，非甲方正式标准。请根据甲方确认的分类分级体系修改并确认。'
}

class Store:
    def __init__(self, directory):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'uploads').mkdir(exist_ok=True)
        self.path = directory / 'risk.db'
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS documents(
                id INTEGER PRIMARY KEY, title TEXT NOT NULL, date TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '', body TEXT NOT NULL,
                kind TEXT NOT NULL, allow_external INTEGER NOT NULL DEFAULT 0,
                demo INTEGER NOT NULL DEFAULT 0, digest TEXT NOT NULL UNIQUE,
                file_path TEXT NOT NULL DEFAULT '', filename TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS chunks(
                id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id),
                locator TEXT NOT NULL, text TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(
                id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id),
                status TEXT NOT NULL, error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                started_at TEXT, finished_at TEXT, progress INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0);
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_job ON jobs(document_id) WHERE status IN ('queued','running');
            CREATE TABLE IF NOT EXISTS analyses(
                id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id), job_id INTEGER,
                version INTEGER NOT NULL, decision TEXT NOT NULL, model TEXT NOT NULL, mode TEXT NOT NULL,
                rules_json TEXT NOT NULL, knowledge_json TEXT NOT NULL, result_json TEXT NOT NULL,
                created_at TEXT NOT NULL, duration_ms INTEGER NOT NULL, usage_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY, analysis_id INTEGER NOT NULL REFERENCES analyses(id),
                title TEXT NOT NULL, category TEXT NOT NULL, level TEXT NOT NULL, summary TEXT NOT NULL,
                impact TEXT NOT NULL, recommendation TEXT NOT NULL, evidence_json TEXT NOT NULL,
                review_status TEXT NOT NULL DEFAULT 'pending', review_note TEXT NOT NULL DEFAULT '', reviewed_at TEXT);
            CREATE TABLE IF NOT EXISTS audit(
                id INTEGER PRIMARY KEY, action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS review_history(
                id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES events(id),
                status TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL);
            ''')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(documents)')}
            for column, ddl in (('zh_summary', "TEXT NOT NULL DEFAULT ''"), ('zh_keywords', "TEXT NOT NULL DEFAULT ''"), ('zh_state', "TEXT NOT NULL DEFAULT ''")):
                if column not in columns: db.execute(f'ALTER TABLE documents ADD COLUMN {column} {ddl}')
            db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', ('rules', json.dumps(DEFAULT_RULES, ensure_ascii=False)))
            db.execute("UPDATE jobs SET status='failed', error='服务重启中断了任务，请重试。', finished_at=? WHERE status='running'", (now(),))

    def delete_documents(self, ids):
        """Remove documents with everything derived from them (chunks, jobs, analyses, events and review
        history); companies and website pages that point at them are unlinked. Returns deleted counts."""
        ids = list(dict.fromkeys(int(i) for i in ids))
        if not ids: return {'documents': 0, 'events': 0}
        marks = ','.join('?' * len(ids))
        with self.db() as db:
            if db.execute(f"SELECT 1 FROM jobs WHERE document_id IN ({marks}) AND status IN ('queued','running') LIMIT 1", ids).fetchone():
                raise ValueError('资料正在分析，请等待任务结束或取消后再删除。')
            tables = {r['name'] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            files = [r['file_path'] for r in db.execute(f'SELECT file_path FROM documents WHERE id IN ({marks})', ids) if r['file_path']]
            analyses = f'SELECT id FROM analyses WHERE document_id IN ({marks})'
            events = db.execute(f'SELECT COUNT(*) n FROM events WHERE analysis_id IN ({analyses})', ids).fetchone()['n']
            db.execute(f'DELETE FROM review_history WHERE event_id IN (SELECT id FROM events WHERE analysis_id IN ({analyses}))', ids)
            db.execute(f'DELETE FROM events WHERE analysis_id IN ({analyses})', ids)
            db.execute(f'DELETE FROM analyses WHERE document_id IN ({marks})', ids)
            db.execute(f'DELETE FROM jobs WHERE document_id IN ({marks})', ids)
            db.execute(f'DELETE FROM chunks WHERE document_id IN ({marks})', ids)
            if 'companies' in tables: db.execute(f'UPDATE companies SET document_id=NULL WHERE document_id IN ({marks})', ids)
            if 'web_pages' in tables:
                for page in db.execute("SELECT id,imports_json FROM web_pages WHERE imports_json!='{}'").fetchall():
                    imports = json.loads(page['imports_json']); kept = {k: v for k, v in imports.items() if v not in ids}
                    if kept != imports: db.execute('UPDATE web_pages SET imports_json=? WHERE id=?', (json.dumps(kept), page['id']))
            deleted = db.execute(f'DELETE FROM documents WHERE id IN ({marks})', ids).rowcount
            # Attachments are removed only when nothing else (another document, a website snapshot) still uses them.
            orphans = [f for f in files if not db.execute('SELECT 1 FROM documents WHERE file_path=? LIMIT 1', (f,)).fetchone()
                       and not ('web_pages' in tables and db.execute('SELECT 1 FROM web_pages WHERE snapshot=? LIMIT 1', (f,)).fetchone())]
        for name in orphans:
            path = self.directory / 'uploads' / name
            if path.parent == self.directory / 'uploads' and path.is_file(): path.unlink()
        return {'documents': deleted, 'events': events}

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def rows(self, sql, args=()):
        with self.db() as db:
            return [dict(r) for r in db.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.rows(sql, args)
        return rows[0] if rows else None

    def setting(self, key):
        row = self.one('SELECT value FROM settings WHERE key=?', (key,))
        return json.loads(row['value']) if row else None

    def set_setting(self, key, value):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value, ensure_ascii=False)))

    def audit(self, action, detail):
        with self.db() as db:
            db.execute('INSERT INTO audit(action,detail,created_at) VALUES (?,?,?)', (action, detail, now()))
