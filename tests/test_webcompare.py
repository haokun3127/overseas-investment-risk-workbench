import json

from app.webcompare import differences
from test_websearch import web_client,add_source,fake_fetch,fake_model,process,make_company
from app import websearch


def snapshot(c,source,body,status='completed',url='https://source.example/news/article',method='direct',archived=''):
    store=c.app.state.store
    with store.db() as db:
        rid=db.execute("INSERT INTO web_runs(source_id,config_json,status,created_at) VALUES (?,?,?,'2026-10-24')",(source,json.dumps({'name':'来源','keywords':'通知','max_pages':1}),status)).lastrowid
        pid=db.execute("INSERT INTO web_pages(run_id,url,title,body,fetched_at,digest,snapshot,method,archived_at) VALUES (?,?,'通知',?,'2026-10-24',?,'',?,?)",(rid,url,body,str(rid),method,archived)).lastrowid
    return rid,pid


def test_comparison_matches_previous_successful_same_source_same_url(web_client):
    c=web_client;sid=add_source(c);other=add_source(c,url='https://other.example/news/')
    first,one=snapshot(c,sid,'通知：企业应在三十日内申报。')
    assert c.get(f'/api/web/pages/{one}/compare').json()['status']=='added'
    _,failed=snapshot(c,sid,'失败任务不作基线。',status='failed')
    snapshot(c,other,'不同来源不作基线。')
    snapshot(c,sid,'不同网址不作基线。',url='https://source.example/news/other')
    second,two=snapshot(c,sid,'通知：企业应在十五日内申报。新增逾期暂停采购条款。')
    result=c.get(f'/api/web/pages/{two}/compare').json()
    assert result['status']=='changed' and result['previous_id']==one and result['previous_run_id']==first
    assert result['added_characters']>0 and result['removed_characters']>0
    text=''.join(r['text'] for h in result['hunks'] for r in h)
    assert '三十日' in text and '十五日' in text and '新增逾期' in text
    items=c.get(f'/api/web/runs/{second}').json()['items']
    assert items[0]['change']['status']=='changed'
    assert c.get(f'/api/web/pages/{failed}/compare').status_code==409
    assert c.get('/api/web/pages/999999/compare').status_code==404
    # Querying an older page never compares against a future run.
    assert c.get(f'/api/web/pages/{one}/compare').json()['previous_id'] is None


def test_whitespace_unchanged_and_archive_boundaries(web_client):
    c=web_client;sid=add_source(c)
    snapshot(c,sid,'申报要求\n按期完成。')
    _,same=snapshot(c,sid,'申报要求  按期完成。')
    assert c.get(f'/api/web/pages/{same}/compare').json()['status']=='unchanged'
    _,old=snapshot(c,sid,'历史正文。',method='archive',archived='2020-01-01')
    r=c.get(f'/api/web/pages/{old}/compare').json()
    assert r['status']=='incomparable' and r['hunks']==[]
    _,live=snapshot(c,sid,'新正文。')
    assert c.get(f'/api/web/pages/{live}/compare').json()['status']=='incomparable'


def test_diff_is_bounded_and_preserves_literal_markup():
    r=differences({'body':'<script>literal</script>新正文。'*5000},{'body':'旧正文。'*5000})
    assert r['truncated'] and sum(len(h) for h in r['hunks'])<=240
    assert sum(len(row['text']) for h in r['hunks'] for row in h)<=60000
    assert r['added_characters']>60000 and r['removed_characters']>0


def test_website_auto_analysis_also_snapshots_rules(web_client,monkeypatch):
    c=web_client;store=c.app.state.store
    monkeypatch.setattr(websearch,'fetch_page',fake_fetch)
    monkeypatch.setattr(websearch.model,'call_model',fake_model)
    owner=make_company(c)
    run=process(c,add_source(c,auto_import='event',auto_analyze=True,target_company_id=owner))
    assert run['status']=='completed'
    job=store.one('SELECT * FROM jobs')
    assert job and job['rules_snapshot_origin']=='submission'
    assert json.loads(job['rules_json'])==store.setting('rules')
