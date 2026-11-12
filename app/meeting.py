"""Business rules agreed on 2026-11-11. Historical analyses remain immutable."""
import json
import re
import unicodedata

VERSION = '20261112-workflow-r12'
TARGET_LEVELS = {
    'lv1': '红色风险：对项目运作或可持续性造成重大严重影响，已经或可能造成实质损失及连锁反应，需要及时处置。',
    'lv2': '黄色风险：影响持续一定时间，造成实质或间接损失，对项目造成较大影响，需要处理风险。',
    'lv3': '蓝色风险：对项目造成一定影响，需要采取规避、关注与监控措施。',
}
LEGACY_MAPPING = {'lv4':'lv3','lv5':'non_risk','red':'lv1','orange':'lv2','yellow':'lv3'}


def current_rules(rules):
    result = json.loads(json.dumps(rules, ensure_ascii=False))
    result['levels'] = dict(rules['levels']) if set(rules.get('levels', {})) == set(TARGET_LEVELS) else dict(TARGET_LEVELS)
    result['version'] = str(rules['version']).split('+meeting-')[0] + '+meeting-20261111'
    result['notes'] = result.get('notes', '').replace('对不上', '其他')
    note = '本次采用红黄蓝三级风险；绿色只对应 decision=non_risk，无风险不生成风险事件。不得输出旧灰色或绿色风险等级，不使用百分比阈值。无法准确匹配类型时填写其他。'
    if note not in result.get('notes', ''):
        result['notes'] = result.get('notes', '') + '\n' + note
    return result


def effective_decision_sql(alias='a'):
    """Current business decision without rewriting the immutable model result."""
    return (f"CASE WHEN {alias}.decision='risk' "
            f"AND EXISTS(SELECT 1 FROM events e WHERE e.analysis_id={alias}.id AND e.deleted_at IS NULL AND e.level='non_risk') "
            f"AND NOT EXISTS(SELECT 1 FROM events e WHERE e.analysis_id={alias}.id AND e.deleted_at IS NULL AND e.level!='non_risk') "
            f"THEN 'non_risk' ELSE {alias}.decision END")


def normalized_text(text):
    # Do not remove punctuation, numbers, units, negation, or version identifiers.
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', text)).strip()


def prioritize(hits):
    """Apply legal priority only to already eligible, relevant recall candidates."""
    legal_types = {'id_law', 'cn_law', 'treaty', 'regional'}
    def rank(row):
        meta = row.get('legal_metadata') or json.loads(row.get('legal_meta') or '{}')
        if meta.get('category') in legal_types:
            return 0 if meta.get('validity') == 'in_force' else 1
        return 2
    seen, result = set(), []
    for row in sorted(hits, key=rank):
        meta = row.get('legal_metadata') or json.loads(row.get('legal_meta') or '{}')
        key = (normalized_text(row['text']), *(meta.get(k, '') for k in ('document_no', 'effective_from', 'effective_to')))
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def initialize(store):
    with store.db() as db:
        cols = {r['name'] for r in db.execute('PRAGMA table_info(events)')}
        for name, ddl in [('deleted_at', 'TEXT'), ('revision', 'INTEGER NOT NULL DEFAULT 0'), ('actions_json', "TEXT NOT NULL DEFAULT '[]'")]:
            if name not in cols:
                db.execute(f'ALTER TABLE events ADD COLUMN {name} {ddl}')
        db.execute('''CREATE TABLE IF NOT EXISTS event_changes(
            id INTEGER PRIMARY KEY,event_id INTEGER NOT NULL,actor TEXT NOT NULL,
            action TEXT NOT NULL,before_json TEXT NOT NULL,after_json TEXT NOT NULL,
            reason TEXT NOT NULL,created_at TEXT NOT NULL)''')
        # Preserve additional provenance when duplicate text is submitted under a different title/URL.
        db.execute('''CREATE TABLE IF NOT EXISTS document_origins(
            id INTEGER PRIMARY KEY,document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            title TEXT NOT NULL,source TEXT NOT NULL,url TEXT NOT NULL,created_at TEXT NOT NULL,
            UNIQUE(document_id,title,source,url))''')
        # User confirmed that existing business results should follow the new standard too.
        # Only the effective event grade changes; original model JSON/rule snapshots stay auditable.
        from .store import now
        for row in db.execute("SELECT id,level,revision FROM events WHERE level IN ('lv4','lv5','red','orange','yellow')").fetchall():
            old,new=row['level'],LEGACY_MAPPING[row['level']]
            reason=f'按2026-11-11确认的新标准迁移：{old}→{new}。旧灰色仍有潜在影响，归蓝色；旧绿色无影响，归无风险。本次为标准转换，未重新分析事实。'
            db.execute('UPDATE events SET level=?,revision=revision+1 WHERE id=?',(new,row['id']))
            db.execute('INSERT INTO event_changes(event_id,actor,action,before_json,after_json,reason,created_at) VALUES (?,?,?,?,?,?,?)',
                (row['id'],'系统标准迁移','standard_migration',json.dumps({'level':old}),json.dumps({'level':new}),reason,now()))
