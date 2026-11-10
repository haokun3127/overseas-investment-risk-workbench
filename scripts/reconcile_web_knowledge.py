"""Plan first, then reconcile completed source pages without analysing risk events."""
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from app.ingest import insert_document
from app.store import Store


def url_key(value):
    p = urlsplit(value)
    query = [(k,v) for k,v in parse_qsl(p.query) if not k.startswith('utm_') and k not in {'from_seo_redirect','lang'}]
    return urlunsplit(('', (p.hostname or '').removeprefix('www.'), p.path.rstrip('/'), urlencode(query), ''))


def text_key(value):
    return re.sub(r'\s+', '', value)


def plan(directory):
    directory = Path(directory)
    manifest_path = directory / 'customer-test-manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.is_file() else {'cases':[]}
    with sqlite3.connect(f'file:{directory / "risk.db"}?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        docs = [dict(r) for r in db.execute("SELECT * FROM documents WHERE kind='knowledge' AND demo=0 AND quarantined_at IS NULL ORDER BY id")]
        companies = {r[0] for r in db.execute('SELECT id FROM companies')}
        pages = [dict(r) for r in db.execute("""SELECT p.*,s.id source_id,s.url source_url,s.target_company_id
            FROM web_sources s JOIN web_runs r ON r.id=(SELECT max(id) FROM web_runs WHERE source_id=s.id)
            JOIN web_pages p ON p.run_id=r.id WHERE s.deleted_at IS NULL AND r.status='completed' AND p.relevant=1 ORDER BY s.id,p.id""")]
    items = []
    for p in pages:
        owners = {p['target_company_id']} if p['target_company_id'] else set()
        keys = {url_key(p['url']),url_key(p['source_url'])}
        for case in manifest['cases']:
            if any(url_key(ref['url']) in keys for ref in case['references']):
                owners.add(case['company_id'])
        if not owners or not owners <= companies:
            raise ValueError(f"Page {p['id']} has no verified company ownership")
        snapshot = (directory/'uploads'/p['snapshot']).resolve()
        if not snapshot.is_relative_to((directory/'uploads').resolve()) or not snapshot.is_file():
            raise ValueError('Missing or unsafe original snapshot')
        imports = json.loads(p['imports_json'])
        for owner in sorted(owners):
            mapped = imports.get('knowledge_by_company',{}).get(str(owner),[])
            reused = [d['id'] for d in docs if d['id'] in mapped and d['company_id']==owner]
            if len(reused) != len(mapped):
                raise ValueError('Invalid knowledge ownership mapping')
            if not reused:
                candidates = [d for d in docs if d['company_id']==owner and url_key(d['url']) in keys]
                if len(text_key(p['body'])) >= 100 and text_key(p['body']) in text_key('\n'.join(d['body'] for d in candidates)):
                    reused = [d['id'] for d in candidates]
                else:
                    reused = [d['id'] for d in docs if d['company_id']==owner and text_key(d['body'])==text_key(p['body'])]
            items.append({'page_id':p['id'],'source_id':p['source_id'],'company_id':owner,
                          'reuse_document_ids':reused,'body_sha256':hashlib.sha256(p['body'].encode()).hexdigest(),
                          'snapshot_sha256':hashlib.sha256(snapshot.read_bytes()).hexdigest()})
    return {'schema':1,'items':items}


def apply(directory, report):
    if plan(directory) != report:
        raise ValueError('Sources changed; regenerate reconciliation plan')
    store = Store(Path(directory))
    result=[]
    for item in report['items']:
        p=store.one('SELECT p.*,r.config_json FROM web_pages p JOIN web_runs r ON r.id=p.run_id WHERE p.id=?',(item['page_id'],))
        ids=item['reuse_document_ids']
        created=False
        if not ids:
            source=json.loads(p['config_json'])
            did,created=insert_document(store,{'title':p['title'],'body':p['body'],'url':p['url'],
                'source':source['name'],'date':p['date']},kind='knowledge',company_id=item['company_id'],
                file_path=p['snapshot'],filename='website-snapshot'+Path(p['snapshot']).suffix,
                meta={'date_source':p['date_source'],'archived_at':p['archived_at'],'fetched_at':p['fetched_at']})
            ids=[did]
        imports=json.loads(p['imports_json'])
        imports.setdefault('knowledge_by_company',{})[str(item['company_id'])]=ids
        imports.setdefault('knowledge',ids[0])
        with store.db() as db:
            if imports != json.loads(p['imports_json']):
                db.execute('UPDATE web_pages SET imports_json=? WHERE id=?',(json.dumps(imports),p['id']))
        result.append({**item,'document_ids':ids,'created':created})
    return result
