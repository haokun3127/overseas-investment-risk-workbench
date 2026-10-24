import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

DEFAULT_RULES = {
    "version": "draft-1", "confirmed": False,
    "categories": ["政策与监管", "法律与合规", "供应链与物流", "劳工与社会", "金融与汇率", "环境与安全"],
    "levels": {"red": "高风险：可能导致重大损失或业务中断，需优先复核。", "orange": "中风险：可能影响经营成本或进度，需制定应对措施。", "yellow": "一般关注风险：影响尚有限或需要持续关注。"},
    "notes": "初始示例规则，非甲方正式标准。请根据甲方确认的分类分级体系修改并确认。"
}

class Store:
    def __init__(self, directory):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "uploads").mkdir(exist_ok=True)
        self.path = directory / "risk.db"
        with self.db() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS documents(
                id INTEGER PRIMARY KEY, title TEXT NOT NULL, date TEXT NOT NULL DEFAULT \x27\x27,
                source TEXT NOT NULL DEFAULT \x27\x27, url TEXT NOT NULL DEFAULT \x27\x27, body TEXT NOT NULL,
                kind TEXT NOT NULL, allow_external INTEGER NOT NULL DEFAULT 0,
                demo INTEGER NOT NULL DEFAULT 0, digest TEXT NOT NULL UNIQUE,
                file_path TEXT NOT NULL DEFAULT \x27\x27, filename TEXT NOT NULL DEFAULT \x27\x27, created_at TEXT NOT NULL,
                date_source TEXT NOT NULL DEFAULT \x27\x27, date_legacy TEXT NOT NULL DEFAULT \x27\x27,
                archived_at TEXT NOT NULL DEFAULT \x27\x27, fetched_at TEXT NOT NULL DEFAULT \x27\x27,
                quarantined_at TEXT DEFAULT NULL, quarantine_reason TEXT NOT NULL DEFAULT \x27\x27);
            CREATE TABLE IF NOT EXISTS chunks(
                id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id),
                locator TEXT NOT NULL, text TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(
                id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id),
                status TEXT NOT NULL, error TEXT NOT NULL DEFAULT \x27\x27, created_at TEXT NOT NULL,
                started_at TEXT, finished_at TEXT, progress INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0);
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_job ON jobs(document_id) WHERE status IN (\x27queued\x27,\x27running\x27);
            CREATE TABLE IF NOT EXISTS analyses(
                id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id), job_id INTEGER,
                version INTEGER NOT NULL, decision TEXT NOT NULL, model TEXT NOT NULL, mode TEXT NOT NULL,
                rules_json TEXT NOT NULL, knowledge_json TEXT NOT NULL, result_json TEXT NOT NULL,
                created_at TEXT NOT NULL, duration_ms INTEGER NOT NULL, usage_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY, analysis_id INTEGER NOT NULL REFERENCES analyses(id),
                title TEXT NOT NULL, category TEXT NOT NULL, level TEXT NOT NULL, summary TEXT NOT NULL,
                impact TEXT NOT NULL, recommendation TEXT NOT NULL, evidence_json TEXT NOT NULL,
                review_status TEXT NOT NULL DEFAULT \x27pending\x27, review_note TEXT NOT NULL DEFAULT \x27\x27, reviewed_at TEXT);
            CREATE TABLE IF NOT EXISTS audit(
                id INTEGER PRIMARY KEY, action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL,
                company_id INTEGER DEFAULT NULL);
            CREATE TABLE IF NOT EXISTS review_history(
                id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES events(id),
                status TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS document_evidence(
                document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                supplement_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                analysis_id INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL, PRIMARY KEY(document_id,supplement_id));
            CREATE TABLE IF NOT EXISTS evidence_checklist(
                id INTEGER PRIMARY KEY, analysis_id INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
                title TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'manual', excerpt TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open', note TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, updated_by TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS checklist_by_analysis ON evidence_checklist(analysis_id);
            CREATE TABLE IF NOT EXISTS checklist_materials(
                item_id INTEGER NOT NULL REFERENCES evidence_checklist(id) ON DELETE CASCADE,
                supplement_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                PRIMARY KEY(item_id,supplement_id));
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(documents)")}
            for column, ddl in (
                ("zh_summary", "TEXT NOT NULL DEFAULT \x27\x27"),
                ("zh_keywords", "TEXT NOT NULL DEFAULT \x27\x27"),
                ("zh_state", "TEXT NOT NULL DEFAULT \x27\x27"),
                ("company_id", "INTEGER DEFAULT NULL"),
                ("date_source", "TEXT NOT NULL DEFAULT \x27\x27"),
                ("date_legacy", "TEXT NOT NULL DEFAULT \x27\x27"),
                ("archived_at", "TEXT NOT NULL DEFAULT \x27\x27"),
                ("fetched_at", "TEXT NOT NULL DEFAULT \x27\x27"),
                ("quarantined_at", "TEXT DEFAULT NULL"),
                ("quarantine_reason", "TEXT NOT NULL DEFAULT \x27\x27"),
            ):
                if column not in columns:
                    db.execute(f"ALTER TABLE documents ADD COLUMN {column} {ddl}")
            sess_cols = {row["name"] for row in db.execute("PRAGMA table_info(sessions)")}
            for column, ddl in (
                ("company_id", "INTEGER DEFAULT NULL"),
                ("username", "TEXT NOT NULL DEFAULT \x27\x27"),
                ("active_company", "INTEGER DEFAULT NULL"),
            ):
                if column not in sess_cols:
                    db.execute(f"ALTER TABLE sessions ADD COLUMN {column} {ddl}")
            audit_cols = {row["name"] for row in db.execute("PRAGMA table_info(audit)")}
            if "company_id" not in audit_cols:
                db.execute("ALTER TABLE audit ADD COLUMN company_id INTEGER DEFAULT NULL")
            db.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", ("rules", json.dumps(DEFAULT_RULES, ensure_ascii=False)))
            job_cols = {row['name'] for row in db.execute('PRAGMA table_info(jobs)')}
            for column, ddl in (
                ('rules_json', "TEXT NOT NULL DEFAULT ''"),
                ('rules_snapshot_origin', "TEXT NOT NULL DEFAULT ''"),
                ('supplements_json', "TEXT NOT NULL DEFAULT '[]'"),
                ('parent_analysis_id', 'INTEGER DEFAULT NULL'),
                ('checklist_json', "TEXT NOT NULL DEFAULT '[]'"),
            ):
                if column not in job_cols:
                    db.execute(f'ALTER TABLE jobs ADD COLUMN {column} {ddl}')
            # Existing queued tasks cannot recover submission-time rules. Freeze once,
            # explicitly mark the upgrade provenance, and never overwrite a snapshot.
            db.execute("UPDATE jobs SET rules_json=(SELECT value FROM settings WHERE key='rules'), rules_snapshot_origin='upgrade' WHERE status='queued' AND rules_json='' ")
            db.execute(
                "UPDATE documents SET date_source=\x27legacy\x27 "
                "WHERE date!=\x27\x27 AND date_source=\x27\x27"
            )
            for row in db.execute(
                "SELECT id,action,detail FROM audit WHERE company_id IS NULL AND detail!=\x27\x27"
            ).fetchall():
                match = re.search(r"(?:^|[ ,])company=(\d+)(?=,|$)", row["detail"])
                if not match and row["action"] in ("company_saved", "company_knowledge_synced"):
                    match = re.search(r"(?:^|[ ,])id=(\d+)(?=,|$)", row["detail"])
                if match:
                    db.execute(
                        "UPDATE audit SET company_id=? WHERE id=? AND company_id IS NULL",
                        (int(match.group(1)), row["id"]),
                    )
            db.execute("UPDATE jobs SET status=\x27failed\x27, error=\x27服务重启中断了任务，请重试。\x27, finished_at=? WHERE status=\x27running\x27", (now(),))

    def delete_documents(self, ids):
        ids = list(dict.fromkeys(int(i) for i in ids))
        if not ids:
            return {"documents": 0, "events": 0}
        marks = ",".join("?" * len(ids))
        with self.db() as db:
            if db.execute(f"SELECT 1 FROM jobs WHERE status IN ('queued','running') AND (document_id IN ({marks}) OR EXISTS(SELECT 1 FROM json_each(jobs.supplements_json) s WHERE json_extract(s.value,'$.document_id') IN ({marks}))) LIMIT 1", ids+ids).fetchone():
                raise ValueError("资料正在分析，请等待任务结束或取消后再删除。")
            tables = {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type=\x27table\x27")}
            files = [r["file_path"] for r in db.execute(f"SELECT file_path FROM documents WHERE id IN ({marks})", ids) if r["file_path"]]
            analyses = f"SELECT id FROM analyses WHERE document_id IN ({marks})"
            events = db.execute(f"SELECT COUNT(*) n FROM events WHERE analysis_id IN ({analyses})", ids).fetchone()["n"]
            db.execute(f"DELETE FROM review_history WHERE event_id IN (SELECT id FROM events WHERE analysis_id IN ({analyses}))", ids)
            db.execute(f"DELETE FROM events WHERE analysis_id IN ({analyses})", ids)
            db.execute(f"DELETE FROM analyses WHERE document_id IN ({marks})", ids)
            db.execute(f"DELETE FROM jobs WHERE document_id IN ({marks})", ids)
            db.execute(f"DELETE FROM chunks WHERE document_id IN ({marks})", ids)
            if "companies" in tables:
                db.execute(f"UPDATE companies SET document_id=NULL WHERE document_id IN ({marks})", ids)
            if "web_pages" in tables:
                for page in db.execute("SELECT id,imports_json FROM web_pages WHERE imports_json!=\x27{}\x27").fetchall():
                    imports = json.loads(page["imports_json"])
                    kept = {k: v for k, v in imports.items() if v not in ids}
                    if kept != imports:
                        db.execute("UPDATE web_pages SET imports_json=? WHERE id=?", (json.dumps(kept), page["id"]))
            deleted = db.execute(f"DELETE FROM documents WHERE id IN ({marks})", ids).rowcount
            orphans = [
                f for f in files
                if not db.execute("SELECT 1 FROM documents WHERE file_path=? LIMIT 1", (f,)).fetchone()
                and not ("web_pages" in tables and db.execute("SELECT 1 FROM web_pages WHERE snapshot=? LIMIT 1", (f,)).fetchone())
            ]
        for name in orphans:
            path = self.directory / "uploads" / name
            if path.parent == self.directory / "uploads" and path.is_file():
                path.unlink()
        return {"documents": deleted, "events": events}

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
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
        row = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(row["value"]) if row else None

    def enqueue_job(self, db, document_id, company_json, supplements=None, parent_analysis_id=None):
        rules_json = db.execute("SELECT value FROM settings WHERE key='rules'").fetchone()['value']
        if not json.loads(rules_json)['confirmed']:
            raise ValueError('请先确认甲方风险分类分级规则。')
        checklist=[]
        if parent_analysis_id:
            for item in db.execute('SELECT id,title,status,note,revision FROM evidence_checklist WHERE analysis_id=? ORDER BY id',(parent_analysis_id,)):
                item=dict(item)
                item['supplement_ids']=[r[0] for r in db.execute('SELECT supplement_id FROM checklist_materials WHERE item_id=? ORDER BY supplement_id',(item['id'],))]
                checklist.append(item)
        return db.execute("""INSERT INTO jobs(document_id,status,created_at,company_json,rules_json,
            rules_snapshot_origin,supplements_json,parent_analysis_id,checklist_json) VALUES (?,'queued',?,?,?,'submission',?,?,?)""",
            (document_id,now(),company_json,rules_json,json.dumps(supplements or [],ensure_ascii=False),parent_analysis_id,json.dumps(checklist,ensure_ascii=False))).lastrowid

    def supplement_snapshot(self, db, document_id):
        docs = db.execute('''SELECT d.*,o.company_id owner FROM document_evidence e
            JOIN documents d ON d.id=e.supplement_id JOIN documents o ON o.id=e.document_id
            WHERE e.document_id=? ORDER BY d.id''',(document_id,)).fetchall()
        if any(not d['allow_external'] or d['quarantined_at'] or d['company_id']!=d['owner'] for d in docs):
            raise ValueError('部分补充材料未授权外发或已隔离，请到待补证入口核对授权或移除关联。')
        if len(docs)>10 or sum(len(d['body']) for d in docs)>24000:
            raise ValueError('关联补充材料超过上限，请到待补证入口精简材料。')
        return [dict(c) for d in docs for c in db.execute('''SELECT c.id,c.document_id,c.locator,c.text,d.title
            FROM chunks c JOIN documents d ON d.id=c.document_id WHERE c.document_id=? ORDER BY c.id''',(d['id'],))]

    def set_setting(self, key, value):
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(value, ensure_ascii=False)))

    def audit(self, action, detail, company_id=None):
        with self.db() as db:
            db.execute(
                "INSERT INTO audit(action,detail,created_at,company_id) VALUES (?,?,?,?)",
                (action, detail, now(), company_id),
            )
