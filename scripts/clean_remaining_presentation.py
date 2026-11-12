"""Clean display metadata only; source bodies and saved analysis evidence are immutable."""
import collections
from app.presentation import clean_name, clean_summary
from app.store import now


def apply(store):
    changed=[]
    fields={'documents':{'title':clean_name,'source':clean_name,'zh_summary':clean_summary,'zh_keywords':clean_summary},
            'events':{'title':clean_name},'web_sources':{'name':clean_name},'web_pages':{'title':clean_name}}
    with store.db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS presentation_changes(
            id INTEGER PRIMARY KEY,table_name TEXT NOT NULL,record_id INTEGER NOT NULL,
            field_name TEXT NOT NULL,before_value TEXT NOT NULL,
            after_value TEXT NOT NULL,created_at TEXT NOT NULL)""")
        for table,columns in fields.items():
            for row in db.execute('SELECT id,'+','.join(columns)+' FROM '+table).fetchall():
                for field,clean in columns.items():
                    before=row[field];after=clean(before)
                    if before==after:
                        continue
                    db.execute(f'UPDATE {table} SET {field}=? WHERE id=?',(after,row['id']))
                    db.execute("""INSERT INTO presentation_changes(
                        table_name,record_id,field_name,before_value,after_value,created_at)
                        VALUES (?,?,?,?,?,?)""",(table,row['id'],field,before,after,now()))
                    changed.append({'table':table,'id':row['id'],'field':field})
    return {'fields_cleaned':len(changed),'counts':dict(collections.Counter(c['table']+'.'+c['field'] for c in changed))}
