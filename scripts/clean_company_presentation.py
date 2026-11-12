"""Clean preparation metadata with an audit trail; preserve source text and results."""
import json
from app.presentation import clean_company_profile, clean_name
from app.store import now


def apply(store):
    changes=[]
    with store.db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS presentation_changes(
            id INTEGER PRIMARY KEY,table_name TEXT NOT NULL,record_id INTEGER NOT NULL,
            field_name TEXT NOT NULL,before_value TEXT NOT NULL,
            after_value TEXT NOT NULL,created_at TEXT NOT NULL)""")
        for row in db.execute('SELECT id,profile_json FROM companies').fetchall():
            profile=json.loads(row['profile_json'])
            cleaned=clean_company_profile(profile)
            if cleaned==profile:
                continue
            encoded=json.dumps(cleaned,ensure_ascii=False)
            db.execute('UPDATE companies SET profile_json=? WHERE id=?',(encoded,row['id']))
            db.execute("""INSERT INTO presentation_changes(
                table_name,record_id,field_name,before_value,after_value,created_at)
                VALUES ('companies',?,'profile_json',?,?,?)""",
                (row['id'],row['profile_json'],encoded,now()))
            changes.append(row['id'])
        titles=0
        for row in db.execute("""SELECT d.id,d.title FROM documents d
            JOIN companies c ON c.document_id=d.id""").fetchall():
            cleaned=clean_name(row['title'])
            if cleaned==row['title']:
                continue
            db.execute('UPDATE documents SET title=? WHERE id=?',(cleaned,row['id']))
            db.execute("""INSERT INTO presentation_changes(
                table_name,record_id,field_name,before_value,after_value,created_at)
                VALUES ('documents',?,'title',?,?,?)""",
                (row['id'],row['title'],cleaned,now()))
            titles+=1
    return {'company_profiles_cleaned':len(changes),'company_document_titles_cleaned':titles}
