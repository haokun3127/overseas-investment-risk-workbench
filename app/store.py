import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

# lv1 is the most severe. Do not reuse red/orange/yellow: the old yellow meant the lightest grade.
LEVELS = {
    "lv1": "I级 红色预警（阈值60%以下）：该风险程度很高，将对项目的运作、可持续性造成重大、严重影响，造成实质损失，并会引发连锁反应，可能无法避免。需要进行损失控制，进行风险处置。",
    "lv2": "II级 黄色预警（阈值60%–70%）：该风险程度高，将持续一定时间，会造成实质损失及间接损失，对投资项目造成较大影响，可能会产生连锁反应。需要进行损失控制，处理风险。",
    "lv3": "III级 蓝色预警（阈值70%–80%）：该风险程度中等，将持续一定时间，对投资项目会造成影响，可能造成一定实质损失及间接损失，但不会产生连锁反应。需要进行风险规避。",
    "lv4": "IV级 灰色预警（阈值80%–90%）：该风险程度较小，持续时间较短，不会产生连锁反应，无实质损失，但有可能造成间接损失，对投资项目可能造成影响。需要对风险进行关注并监控。",
    "lv5": "V级 绿色预警（阈值90%–100%）：接到动态信息，该风险点持续短、不会造成连锁反应，对项目投资不会造成影响，无实质和间接损失。（以预防为主）一般无需处理，可以忽略。",
}
LEGACY_LEVELS = {
    "red": "高风险（旧标准）",
    "orange": "中风险（旧标准）",
    "yellow": "一般关注（旧标准）",
}
LEVEL_LABELS = {'lv1':'红色风险','lv2':'黄色风险','lv3':'蓝色风险','lv4':'灰色预警（历史原始值）','lv5':'绿色预警（历史原始值）',**LEGACY_LEVELS,'non_risk':'绿色 · 无风险'}
LEVEL_ORDER = [*LEVELS, *LEGACY_LEVELS]

DEFAULT_RULES = {
    "version": "client-risk-taxonomy-20261026",
    "confirmed": False,
    "categories": [
        "政权更迭",
        "军事政变",
        "战争及内乱",
        "政府征收和国有化风险",
        "汇兑限制",
        "政府腐败",
        "中止/终止特许经营权",
        "财政偿债能力不足",
        "东道国违反合同风险",
        "东道国被其他国家或国际组织制裁风险",
        "对华友好度",
        "地缘政治与大国博弈",
        "法律政策变动",
        "法律透明度",
        "法律制度健全性",
        "准入审批限制风险",
        "安全审查风险",
        "反垄断审查风险",
        "执法效率",
        "执法力度",
        "司法公平",
        "司法效率",
        "执行风险",
        "腐败风险",
        "人权风险",
        "违反东道国其他法律被处罚",
        "与被制裁企业交易",
        "跨境数据流动",
        "合同执行风险",
        "法律救济与适用风险",
        "知识产权保护风险",
        "知识产权纠纷风险",
        "劳工组织维权风险",
        "劳工诉讼风险",
        "聘用当地或外籍员工要求",
        "环保抗议风险",
        "环保诉讼风险",
        "环境行政审查风险",
        "宗教冲突风险",
        "文化冲突风险",
        "社会动乱风险",
        "刑事犯罪风险",
        "人员流动性限制",
        "经济贸易限制",
        "其他限制性措施"
    ],
    "levels": dict(LEVELS),
    "notes": "来源：甲方《海外利益风险预警防控体系的构建》中的投资政治、法律、社会风险指标体系。\ncategory 只能填写 categories 中的三级指标名称，必须与名单完全一致。一级、二级只用于理解归类，不能写入 category。\n一条资料涉及多个三级指标时拆成多条事件。对不上任何三级指标时不要硬归类，也不要使用政策与监管、法律与合规、供应链与物流、劳工与社会、金融与汇率、环境与安全这些旧分类。\n政治风险\n政治稳定：政权更迭（政党变更、政府换届）；军事政变（极端的政权颠覆）；战争及内乱（战争及内部战乱）\n政府行为风险：政府征收和国有化风险（政府将投资财产收归国有的强制性措施）；汇兑限制（东道国外汇限制的程度）；政府腐败（行政管理过程中的腐败）\n政府违约风险：中止/终止特许经营权（政府部门未履行特许协议的权利义务）；财政偿债能力不足（政府偿付公共债务本息的能力不足）；东道国违反合同风险（东道国未履行合同义务）\n国际关系风险：东道国被其他国家或国际组织制裁风险（贸易限制、制裁等外部压力）；对华友好度（双边投资政策、政治关系、投资情绪）；地缘政治与大国博弈（地缘关系导致的国际关系风险）\n法律风险\n法律环境风险：法律政策变动（影响投资的法律政策变动）；法律透明度（法律是否可以获得）；法律制度健全性（立法完善度）\n外资管理风险：准入审批限制风险（审批透明度、耗时或审批制度变动）；安全审查风险（安全审查制度及其变动）；反垄断审查风险（反垄断制度及其政策变动）\n执法风险：执法效率（执法效率低下影响营商环境）；执法力度（法律执行缺乏力度）\n司法风险：司法公平（司法独立、错案纠错或司法腐败）；司法效率（结案率、平均结案耗时）；执行风险（执行期限、执行率）\n合规风险：腐败风险（跨国经营中的腐败或商业贿赂被处罚）；人权风险（违反东道国人权法律法规被处罚）；违反东道国其他法律被处罚（违反东道国其他法律法规被处罚）；与被制裁企业交易（因合作方被制裁造成损失）；跨境数据流动（违反东道国跨境数据流动法律法规）\n合同风险：合同执行风险（合同执行耗时长、成本高）；法律救济与适用风险（缺少与东道国政府的争端解决机制）\n知识产权风险：知识产权保护风险（知识产权保护不足或违法）；知识产权纠纷风险（因知识产权问题引发法律纠纷）\n社会风险\n劳工风险：劳工组织维权风险（劳工抗议、罢工）；劳工诉讼风险（劳动集体诉讼、劳动争议）；聘用当地或外籍员工要求（要求聘用当地劳工或限制外籍员工）\n环境保护风险：环保抗议风险（环保集会、游行）；环保诉讼风险（环保诉讼造成损失）；环境行政审查风险（环境评估或环境行政处罚）\n宗教文化风险：宗教冲突风险（宗教信仰导致的纠纷或宗教法律化）；文化冲突风险（社会文化认同差异引起的矛盾）\n社会治安风险：社会动乱风险（治安紊乱、社会不稳定造成的动乱）；刑事犯罪风险（刑事犯罪影响投资成本或人员安全）\n重大公共卫生风险：人员流动性限制（重大公共卫生事件导致的人员流动和交通限制）；经济贸易限制（与重大公共卫生事件相关的经贸限制）；其他限制性措施（重大公共卫生事件导致的其他限制）"
}

CLASSIFICATION_BOUNDARIES = '''客户分类边界澄清（适用于本体系，不推算案例结论）：
“法律政策变动”须有法律、法规或普遍适用的监管规则被制定、修改、废止或新适用的直接事实。现有制度下对个别经营者的年度生产销售指标、数量配额或作业计划核定，不仅因属于政府政策或数字发生变化就成为法律政策变动。不得从生产额度变化猜测法律已经修订。
“准入审批限制风险”针对市场进入、新投资设立、初始经营资格等准入审批。已在营主体按原制度申请年度生产销售配额，不仅因存在行政批准程序就成为市场准入限制。
若同时没有法律规范变更或初始准入限制的直接证据，但生产停顿等经营损害已明确，则风险仍成立；现有三级不覆盖这种行政数量配置时填“对不上”，保留等级、引文和人工复核，不猜测政府征收、违约或新法。
上述是按事实区分机制，不是用配额等关键词排除其他风险。另有普遍规则改变或市场准入受限的直接证据时，仍分别保留其真实类别。'''
EVIDENCE_APPLICATION_BOUNDARIES = '''主体与影响证据的适用边界：
先分别核实行为人、受影响企业和承担法律责任者。政府官员受贿、公共决策失序导致投资安排受阻，属于政府行为对企业的外部影响。不能因为企业参加的联合体或合作方涉案，就推定被分析企业自身实施商业贿赂或已受处罚。“腐败风险”的既定定义包含企业因腐败或商业贿赂被处罚，须有能对应被分析企业或其承担责任实体的处罚事实；新闻指控、联合体成员身份、官员或其他成员被调查，不能替代该事实。另有独立的企业受罚证据时再保留该项，不机械排除多指标。
严格区分违规行为持续时间、执法处理跨度与项目受损持续时间。多年交易或多年调查，并不自动证明项目多年遭受较大经营损害。不同机关针对同一事实的和解、处罚与抵扣金额，不得重复累加为企业已付损失。
分级只使用已知影响及有具体事实支撑的发展趋势。确定的有限和解付款、交易或支付链整改，即使有一定直接损失，也不因泛称银行审查、声誉、未来罚款就自动升级；没有较大持续项目影响或风险扩散的具体证据时，按lv3的中等实质影响审视，而非仅因出现罚款就判lv2。缺少总金额本身也不能用来降低已经明确发生的重大运营或人身损害。已发生重大资本占用并延续追偿、高额多主体执法且需持续调整业务、实际生产或建设明显受阻等事实，仍按其真实持续程度和经营影响判断lv2及以上，不采用统一金额阈值。'''
DEFAULT_RULES['version'] = 'client-risk-taxonomy-20261101-evidence'
DEFAULT_RULES['notes'] += '\n\n' + CLASSIFICATION_BOUNDARIES + '\n\n' + EVIDENCE_APPLICATION_BOUNDARIES


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
        from .legal_knowledge import migrate
        migrate(self)
        from .meeting import initialize
        initialize(self)

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
        from .meeting import current_rules
        rules_json = json.dumps(current_rules(json.loads(rules_json)), ensure_ascii=False)
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
        if any(d['quarantined_at'] or d['company_id']!=d['owner'] for d in docs):
            raise ValueError('部分补充材料已隔离或归属不一致，请到待补证入口核对或移除关联。')
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
