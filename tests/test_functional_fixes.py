import json
from pathlib import Path
import sqlite3
import pytest
from app.main import create_app
from app.config import Settings
from scripts.backup_daily import run
from scripts.reconcile_web_knowledge import plan, apply
from app.publication import absence_note


def test_shell_release_files_are_lf():
    root=Path(__file__).resolve().parents[1]
    assert b'\r' not in (root/'scripts/backup-daily.sh').read_bytes()


def test_absence_notes_do_not_invent_publication_dates():
    assert '更新时间' in absence_note({'body':'updated : 08/12/2016','url':'https://a.test'})
    assert '持续记录' in absence_note({'body':'Date Registered:\nMay 19, 2011'})
    assert '报告基准期' in absence_note({'body':'As of December 31, 2014'})
    assert absence_note({'date':'2024-01-01'})==''


def test_backup_success_failure_and_recoverable_copy(tmp_path, monkeypatch):
    app=create_app(Settings(data_dir=tmp_path/'data'),run_worker=False)
    original=app.state.store.directory/'archive-copies'
    original.mkdir();(original/'original.txt').write_text('original evidence')
    destination=tmp_path/'backup'
    target=run(app.state.store.directory,destination,keep=0)
    assert json.loads((destination/'status.json').read_text())['state']=='completed'
    assert (target/'archive-copies/original.txt').read_text()=='original evidence'
    with sqlite3.connect(target/'risk.db') as db: assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    def broken(*a):raise OSError('test disk failure')
    monkeypatch.setattr('scripts.backup_daily.backup',broken)
    with pytest.raises(OSError):run(app.state.store.directory,destination)
    assert json.loads((destination/'status.json').read_text())['state']=='failed'
    assert target.exists()
    with pytest.raises(ValueError):run(app.state.store.directory,app.state.store.directory/'nested')


def test_reconcile_scoped_idempotent_and_never_creates_jobs(tmp_path):
    app=create_app(Settings(data_dir=tmp_path/'data'),run_worker=False)
    store=app.state.store
    with store.db() as db:
        cid=db.execute("INSERT INTO companies(profile_json,updated_at) VALUES ('{}','x')").lastrowid
        sid=db.execute("INSERT INTO web_sources(name,url,keywords,max_pages,interval_hours,allow_external,auto_import,auto_analyze,created_at,target_company_id) VALUES ('law','https://site.test/law','law',1,0,1,'none',0,'x',?)",(cid,)).lastrowid
        rid=db.execute("INSERT INTO web_runs(source_id,config_json,status,created_at) VALUES (?,?,'completed','x')",(sid,json.dumps({'name':'law'}))).lastrowid
        db.execute("INSERT INTO web_pages(run_id,url,title,body,fetched_at,digest,snapshot,relevant) VALUES (?,'https://site.test/law','Law','Published on June 1, 2024\nOfficial regulation','x','x','law.html',1)",(rid,))
    (store.directory/'uploads/law.html').write_text('<article>Law</article>')
    first=apply(store.directory,plan(store.directory))
    assert first[0]['created']
    assert store.one('SELECT company_id FROM documents')['company_id']==cid
    second=apply(store.directory,plan(store.directory))
    assert not second[0]['created']
    assert store.one('SELECT count(*) n FROM documents')['n']==1
    assert store.one('SELECT count(*) n FROM jobs')['n']==0
    old=plan(store.directory)
    (store.directory/'uploads/law.html').write_text('changed')
    with pytest.raises(ValueError):apply(store.directory,old)
