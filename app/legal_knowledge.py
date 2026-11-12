"""Typed legal knowledge and exact, heading-based sections. No inferred legal validity."""
import json
import re
from datetime import date
from urllib.parse import urlparse

CATEGORIES = {
    'unclassified': '未分类', 'id_law': '印尼国内法律法规', 'judgment': '司法判决',
    'administrative': '行政裁决与处罚', 'arbitration': '仲裁裁决', 'treaty': '国际条约与协定',
    'cn_law': '中国相关法律法规', 'sanctions': '制裁与出口管制',
    'international': '国际组织与多边机构文件', 'regional': '东盟及其他国家涉印尼法律',
    'incident': '事件参考（未经诉讼或仲裁处理）', 'case': '案例（经诉讼或仲裁处理）',
    'indicator': '风险指标体系', 'advice': '风险处置建议', 'template': '报告模板',
}
SECTIONS = {'general': '正文', 'facts': '事实认定', 'law': '法律适用',
            'reasoning': '法院／仲裁庭认为', 'disposition': '裁判主文', 'execution': '执行情况'}
VALIDITY = {'unknown': '效力未确认', 'in_force': '现行有效', 'not_yet': '尚未生效',
            'repealed': '已废止', 'historical': '历史版本'}
PATTERNS = {
    'facts': r'事实认定|案件事实|经审理查明|本院查明|DUDUK PERKARA|TENTANG DUDUK PERKARA|Statement of Facts|Findings of Fact',
    'law': r'法律适用|适用法律|法律依据|DASAR HUKUM|Applicable Law|Legal Basis',
    'reasoning': r'本院认为|法院认为|仲裁庭认为|裁判理由|PERTIMBANGAN HUKUM|TENTANG PERTIMBANGAN HUKUM|Legal Reasoning|Reasons for (?:the )?(?:Decision|Award)|Tribunal.s Analysis',
    'disposition': r'判决如下|裁定如下|判决主文|裁决主文|MENGADILI|MEMUTUSKAN|OPERATIVE PART|DISPOSITION',
    'execution': r'执行情况|执行结果|Enforcement Status',
}
# Require an entire heading line, with optional numbering, to avoid tagging a quote or narrative mention.
HEADING = re.compile(r'^\s*(?:(?:[一二三四五六七八九十]+[、.]|\d+[.)、]|[IVX]+[.)])\s*)?'
                     r'(?P<title>' + '|'.join(PATTERNS.values()) + r')\s*[:：;；]?\s*$', re.I | re.M)


def section_spans(body):
    matches = list(HEADING.finditer(body))
    spans = []
    cursor, section = 0, 'general'
    for match in matches:
        if match.start() > cursor:
            spans.append((cursor, match.start(), section))
        cursor = match.start()
        section = next(key for key, pattern in PATTERNS.items()
                       if re.fullmatch(pattern, match['title'], re.I))
    if cursor < len(body):
        spans.append((cursor, len(body), section))
    return spans


def structured_chunks(body, size=2400):
    for start, end, section in section_spans(body):
        for offset in range(start, end, size):
            stop = min(offset + size, end)
            yield f'正文字符 {offset + 1}–{stop}', body[offset:stop], section


def validate_metadata(values):
    if not isinstance(values, dict):
        raise ValueError('知识分类信息必须是对象。')
    result = {
        'category': str(values.get('category') or 'unclassified'),
        'jurisdiction': str(values.get('jurisdiction') or '').strip(),
        'document_no': str(values.get('document_no') or '').strip(),
        'issuer': str(values.get('issuer') or '').strip(),
        'effective_from': str(values.get('effective_from') or '').strip(),
        'effective_to': str(values.get('effective_to') or '').strip(),
        'validity': str(values.get('validity') or 'unknown'),
        'verified_on': str(values.get('verified_on') or '').strip(),
        'verification_note': str(values.get('verification_note') or '').strip(),
        'verification_urls': values.get('verification_urls') or [],
        'corroboration': str(values.get('corroboration') or 'unreviewed'),
    }
    if result['category'] not in CATEGORIES or result['validity'] not in VALIDITY:
        raise ValueError('知识分类或效力状态无效。')
    for field in ('effective_from', 'effective_to', 'verified_on'):
        if result[field]:
            try:
                date.fromisoformat(result[field])
            except ValueError:
                raise ValueError('生效、失效及核验日期须为 YYYY-MM-DD。') from None
    if result['effective_from'] and result['effective_to'] and result['effective_to'] < result['effective_from']:
        raise ValueError('失效日期不能早于生效日期。')
    if result['verified_on'] and result['verified_on'] > date.today().isoformat():
        raise ValueError('核验日期不能晚于今天。')
    urls = result['verification_urls']
    if not isinstance(urls, list) or len(urls) > 10:
        raise ValueError('核验来源最多10个网址。')
    for url in urls:
        if not isinstance(url, str) or len(url) > 2000 or urlparse(url).scheme not in ('https', 'http') or not urlparse(url).hostname:
            raise ValueError('核验来源须为完整的 http 或 https 网址。')
    result['verification_urls'] = list(dict.fromkeys(urls))
    if result['corroboration'] not in ('unreviewed', 'single', 'confirmed'):
        raise ValueError('交叉核验状态无效。')
    if result['corroboration'] == 'confirmed':
        hosts = {urlparse(url).hostname.lower().removeprefix('www.') for url in urls}
        if len(hosts) < 2 or not result['verified_on'] or not result['verification_note']:
            raise ValueError('确认交叉印证须记录两个不同来源网址、核验日期及独立性核验说明。')
    for field in ('jurisdiction', 'document_no', 'issuer'):
        if len(result[field]) > 300:
            raise ValueError('国家、文号或发布机构超过300字符。')
    if len(result['verification_note']) > 3000:
        raise ValueError('核验说明超过3000字符。')
    if result['validity'] != 'unknown' and not (result['verified_on'] and result['verification_note'] and urls):
        raise ValueError('确认法规效力时，请同时填写核验日期、核验依据说明和原文网址。')
    return result


def metadata(doc):
    value = {**validate_metadata({}), **json.loads(doc.get('legal_meta') or '{}')}
    value['category_label'] = CATEGORIES[value['category']]
    value['validity_label'] = VALIDITY[value['validity']]
    # Multiple links are evidence for a reviewer, not automatic proof of independent corroboration.
    value['verification_label'] = '已记录人工核验' if value['verified_on'] and value['verification_note'] else '尚无人工核验记录'
    value['revision'] = doc.get('legal_revision', 0)
    return value


def matches_filters(row, category='', section='', validity=''):
    m = json.loads(row.get('legal_meta') or '{}')
    return ((not category or m.get('category', 'unclassified') == category)
            and (not validity or m.get('validity', 'unknown') == validity)
            and (not section or row.get('section_type', 'general') == section))


def migrate(store):
    with store.db() as db:
        cols = {row['name'] for row in db.execute('PRAGMA table_info(documents)')}
        if 'legal_meta' not in cols:
            db.execute("ALTER TABLE documents ADD COLUMN legal_meta TEXT NOT NULL DEFAULT '{}'")
            db.execute('ALTER TABLE documents ADD COLUMN legal_revision INTEGER NOT NULL DEFAULT 0')
        cols = {row['name'] for row in db.execute('PRAGMA table_info(chunks)')}
        if 'section_type' not in cols:
            db.execute("ALTER TABLE chunks ADD COLUMN section_type TEXT NOT NULL DEFAULT 'general'")
        db.execute('''CREATE TABLE IF NOT EXISTS consultation_reports(
            id INTEGER PRIMARY KEY, company_id INTEGER, question TEXT NOT NULL,
            result_json TEXT NOT NULL, created_at TEXT NOT NULL)''')
        # Preserve all existing chunk IDs and citations. Old chunks crossing headings stay general.
        if not db.execute("SELECT 1 FROM settings WHERE key='legal_section_migration_v1'").fetchone():
            for doc in db.execute("SELECT id,body FROM documents WHERE kind='knowledge'").fetchall():
                spans = section_spans(doc['body'])
                for chunk in db.execute('SELECT id,locator,text FROM chunks WHERE document_id=?', (doc['id'],)).fetchall():
                    loc = re.fullmatch(r'正文字符 (\d+)[–-](\d+)', chunk['locator'])
                    if not loc:
                        continue
                    start, stop = int(loc[1]) - 1, int(loc[2])
                    if doc['body'][start:stop] != chunk['text']:
                        continue
                    tag = next((tag for a, b, tag in spans if a <= start and stop <= b), 'general')
                    db.execute('UPDATE chunks SET section_type=? WHERE id=?', (tag, chunk['id']))
                for locator, text, tag in structured_chunks(doc['body']):
                    if tag != 'general' and not db.execute('SELECT 1 FROM chunks WHERE document_id=? AND locator=? AND text=? AND section_type=?',
                                                          (doc['id'], locator, text, tag)).fetchone():
                        db.execute('INSERT INTO chunks(document_id,locator,text,section_type) VALUES (?,?,?,?)',
                                   (doc['id'], locator, text, tag))
            db.execute("INSERT INTO settings VALUES ('legal_section_migration_v1','true')")
