import pytest
from app import websearch as web
from test_websearch import web_client,add_source,process


def test_late_filing_section_survives_before_model_review(web_client,monkeypatch):
    before='Annual accounts and repeated financial table.\n'*1800
    fact='The Indonesian government imposed export restrictions on the Batu Hijau operation.'
    after='Other financial statements and accounting notes.\n'*1500
    body=before+fact+after
    raw=('<title>Annual report</title><p>'+body+'</p>').encode()
    def fetch(url,*a,**kw):
        if url.endswith('robots.txt'):return url,'',b'','text/plain'
        return url,raw.decode(),raw,'text/html'
    seen=[]
    async def model(settings,payload,**kw):
        seen.extend(payload['pages'])
        return {'items':[{'id':p['id'],'relevant':True,'reason':'Concrete export restrictions','quote':fact} for p in payload['pages']]},{}
    monkeypatch.setattr(web,'fetch_page',fetch)
    monkeypatch.setattr(web.model,'call_model',model)
    run=process(web_client,add_source(web_client,keywords='Indonesian export restrictions Batu Hijau',max_pages=1))
    assert run['status']=='completed' and run['items'][0]['relevant']==1
    assert fact in seen[0]['body']
    page=web_client.get('/api/web/pages/'+str(run['items'][0]['id'])).json()
    assert fact in page['body'] and '长文节选' in page['body'] and len(page['body'])<=web.MAX_BODY
    record=web_client.app.state.store.one('SELECT snapshot FROM web_pages WHERE id=?',(page['id'],))
    assert (web_client.app.state.store.directory/'uploads'/record['snapshot']).read_bytes()==raw


def test_short_and_no_topic_excerpts_stay_bounded_and_contiguous():
    assert web.retained_body('short body','topic')=='short body'
    body='a'*70000
    assert web.retained_body(body,'')==body[:web.MAX_BODY-len(web.TRUNCATED)]+web.TRUNCATED


def test_large_html_is_read_completely_or_explicitly_rejected(monkeypatch):
    # Exercise fetch/decode boundary, not just a helper that repeats its implementation.
    payload=b'<html><title>Large filing</title>'+b'a'*(web.MAX_BYTES+100)+b'</html>'
    class Response:
        status=200
        def getheader(self,name,default=None):return 'text/html' if name=='Content-Type' else default
        def read(self,size):return payload[:size]
    class Connection:
        def close(self):pass
    monkeypatch.setattr(web,'open_response',lambda *a,**kw:(Connection(),Response()))
    _,_,raw,_=web.fetch_page('https://source.example/report','https://source.example/report')
    assert raw==payload and raw.endswith(b'</html>')
    monkeypatch.setattr(web,'MAX_HTML_BYTES',100)
    with pytest.raises(ValueError,match='采集限制'):
        web.fetch_page('https://source.example/report','https://source.example/report')
