"""Compare the local legal re-analysis with the production baseline's latest analysis per document."""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'qa/legal-import-20261112'
PLAN = json.loads((ROOT / 'qa/requirements-audit-20261112/date-plan.json').read_text())


def latest(db, doc_id):
    row = db.execute('SELECT id,decision FROM analyses WHERE document_id=? ORDER BY version DESC LIMIT 1', (doc_id,)).fetchone()
    if not row:
        return None
    events = db.execute('SELECT title,category,level,actions_json FROM events WHERE analysis_id=? AND deleted_at IS NULL', (row[0],)).fetchall()
    return {'analysis_id': row[0], 'decision': row[1],
            'events': [{'title': e[0], 'category': e[1], 'level': e[2], 'actions': json.loads(e[3] or '[]')} for e in events]}


def key(analysis):
    return sorted((e['category'], e['level']) for e in analysis['events']) if analysis else None


def main():
    base = sqlite3.connect(WORK / 'production-before.db')
    new = sqlite3.connect(WORK / 'replica/risk.db')
    laws = {r[0]: r[1] for r in new.execute("SELECT id,title FROM documents WHERE id>=109 AND kind='knowledge'")}
    rows = []
    for doc_id, _ in PLAN:
        before, after = latest(base, doc_id), latest(new, doc_id)
        basis = []
        for event in (after or {}).get('events', []):
            for action in event['actions']:
                for item in action.get('basis') or []:
                    basis.append({'action': action['text'][:80], 'law': laws.get(item.get('document_id'), item.get('title')),
                                  'quote': (item.get('quote') or '')[:200]})
        title = new.execute('SELECT title FROM documents WHERE id=?', (doc_id,)).fetchone()[0]
        rows.append({'document_id': doc_id, 'title': title,
                     'before': {'decision': before and before['decision'], 'events': key(before)},
                     'after': {'analysis_id': after and after['analysis_id'], 'decision': after and after['decision'], 'events': key(after)},
                     'same': bool(before and after and before['decision'] == after['decision'] and key(before) == key(after)),
                     'new_analysis': bool(after and before and after['analysis_id'] != before['analysis_id']),
                     'basis': basis})
    summary = {'documents': len(rows), 'reanalysed': sum(r['new_analysis'] for r in rows),
               'unchanged_result': sum(r['same'] for r in rows), 'with_legal_basis': sum(bool(r['basis']) for r in rows)}
    (WORK / 'compare.json').write_text(json.dumps({'summary': summary, 'rows': rows}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False))
    for r in rows:
        print('OK  ' if r['same'] else 'DIFF', r['document_id'], r['before']['events'], '->', r['after']['events'], 'basis', len(r['basis']))


if __name__ == '__main__':
    main()
