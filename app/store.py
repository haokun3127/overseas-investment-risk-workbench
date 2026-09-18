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
            db.execute('INSERT OR IGNORE INTO settings VALUES (?,?)', ('rules', json.dumps(DEFAULT_RULES, ensure_ascii=False)))
            db.execute("UPDATE jobs SET status='failed', error='服务重启中断了任务，请重试。', finished_at=? WHERE status='running'", (now(),))

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
