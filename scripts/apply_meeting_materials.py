"""Apply reviewed metadata with compare-and-swap; preserve originals and model results."""
import hashlib
import json
from pathlib import Path
from app.legal_knowledge import validate_metadata
from app.store import now


def apply(store,plan):
    changed=[];skipped=[];names=[]
    with store.db() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS material_changes(id INTEGER PRIMARY KEY,document_id INTEGER NOT NULL,
            before_json TEXT NOT NULL,after_json TEXT NOT NULL,reason TEXT NOT NULL,created_at TEXT NOT NULL)''')
        for item in plan['changes']:
            row=db.execute('SELECT * FROM documents WHERE id=?',(item['id'],)).fetchone()
            if not row or hashlib.sha256(row['body'].encode()).hexdigest()!=item['body_sha256']:
                raise ValueError('资料正文与核对版本不同，停止处理：'+str(item['id']))
            before=item['before']
            if any(row[k]!=before[k] for k in ('title','source','legal_meta','legal_revision')):
                skipped.append(item['id']);continue
            meta=json.loads(row['legal_meta'] or '{}')
            if meta.get('category','unclassified')=='unclassified':meta['category']=item['category']
            meta=validate_metadata(meta)
            values={'title':item['title'],'source':item['source'],'legal_meta':json.dumps(meta,ensure_ascii=False)}
            db.execute('UPDATE documents SET title=?,source=?,legal_meta=?,legal_revision=legal_revision+1 WHERE id=? AND legal_revision=?',
                       (values['title'],values['source'],values['legal_meta'],item['id'],before['legal_revision']))
            db.execute('INSERT INTO material_changes(document_id,before_json,after_json,reason,created_at) VALUES (?,?,?,?,?)',
                       (item['id'],json.dumps(before,ensure_ascii=False),json.dumps(values,ensure_ascii=False),item['reason'],now()))
            changed.append(item['id'])
        db.execute('''CREATE TABLE IF NOT EXISTS presentation_changes(id INTEGER PRIMARY KEY,table_name TEXT NOT NULL,
            record_id INTEGER NOT NULL,field_name TEXT NOT NULL,before_value TEXT NOT NULL,after_value TEXT NOT NULL,created_at TEXT NOT NULL)''')
        allowed={'documents':{'title','source'},'web_sources':{'name'},'web_pages':{'title'},'events':{'title'}}
        for item in plan.get('names',[]):
            table=item['table'];field=item['field']
            if table not in allowed or field not in allowed[table]:raise ValueError('名称字段无效')
            # Parameterize values and allow-list identifiers, preserve concurrent changes.
            updated=db.execute(f'UPDATE {table} SET {field}=? WHERE id=? AND {field}=?',
                               (item['after'],item['id'],item['before'])).rowcount
            if updated:
                db.execute('INSERT INTO presentation_changes(table_name,record_id,field_name,before_value,after_value,created_at) VALUES (?,?,?,?,?,?)',
                           (table,item['id'],field,item['before'],item['after'],now()))
                names.append({k:item[k] for k in ('table','id','field')})
        for template in plan.get('templates',[]):
            if not db.execute('SELECT id FROM drafting_templates WHERE name=? AND deleted_at IS NULL',(template['name'],)).fetchone():
                db.execute('INSERT INTO drafting_templates(name,category,body,created_at) VALUES (?,?,?,?)',
                           (template['name'],template['category'],template['body'],now()))
    return {'changed':changed,'skipped_concurrent_edits':skipped,'names_cleaned':names}


if __name__=='__main__':
    import sys
    from app.config import Settings
    from app.main import create_app
    from dataclasses import replace
    app=create_app(replace(Settings(),data_dir=Path(sys.argv[1])),run_worker=False)
    print(json.dumps(apply(app.state.store,json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))),ensure_ascii=False))
