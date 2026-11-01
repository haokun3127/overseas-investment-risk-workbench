import secrets
import pytest
from fastapi.testclient import TestClient
from app import companies
from app.config import Settings
from app.ingest import insert_document
from app.main import create_app
from app.retrieval import annotate_hits, retrieve
from app.store import Store
from retrieval_corpus import LONG_BODY, QUERIES, build_corpus

HEADERS = {'X-Requested-With': 'risk-workbench'}

# Recorded from retrieve() on the pre-repair baseline (commit 4be8801); scoring and order must not change.
GOLDEN = {
    '外籍劳工': [(0, '正文字符 1–2400', 43.623), (0, '正文字符 2401–3606', 41.534), (2, '正文字符 1–49', 41.282)],
    '劳工许可': [(0, '正文字符 2401–3606', 15.005), (0, '正文字符 1–2400', 13.128), (2, '正文字符 1–49', 13.066)],
    '进口清关': [(4, '正文字符 1–35', 57.763)],
    'perizinan berusaha': [(3, '正文字符 1–97', 3.25), (1, '正文字符 1–91', 3.226)],
    '营业许可': [(3, '正文字符 1–97', 39.632)],
}
RETRIEVE_FIELDS = ['date', 'document_id', 'id', 'locator', 'score', 'source', 'text', 'title']


def make_store(path):
    store = Store(path)
    companies.initialize(store)
    return store


@pytest.fixture
def corpus(tmp_path):
    store = make_store(tmp_path)
    return store, build_corpus(store)


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, model_mode='external', model_base_url='https://example.com/v1',
                              model_name='test', model_api_key='test'), run_worker=False)
    with TestClient(app, headers=HEADERS) as c:
        c.post('/api/auth/setup', json={'password': secrets.token_urlsafe(16)})
        yield c


def test_retrieve_scores_and_order_match_baseline(corpus):
    store, ids = corpus
    assert set(GOLDEN) == set(QUERIES)
    for query, expected in GOLDEN.items():
        rows = retrieve(store, query, limit=10)
        assert [(ids.index(r['document_id']), r['locator'], r['score']) for r in rows] == expected, query
        assert sorted(rows[0].keys()) == RETRIEVE_FIELDS


def test_annotate_keeps_order_and_scores(corpus):
    store, _ = corpus
    hits = retrieve(store, '外籍劳工', limit=10, per_document=True)
    annotated = annotate_hits(store, '外籍劳工', hits)
    assert [(h['document_id'], h['score']) for h in annotated] == [(h['document_id'], h['score']) for h in hits]


def test_chinese_hit_window_offsets_are_exact(corpus):
    store, ids = corpus
    hits = annotate_hits(store, '外籍劳工', retrieve(store, '外籍劳工', limit=10, per_document=True))
    guide = next(h for h in hits if h['document_id'] == ids[2])
    body = store.one('SELECT body FROM documents WHERE id=?', (ids[2],))['body']
    assert guide['body_hit'] is True and guide['hit_windows']
    for window in guide['hit_windows']:
        assert body[window['start']:window['end']] == window['text']
        assert '外籍劳工' in window['terms']
    assert '外籍劳工' in guide['matched']['title'] and '外籍劳工' in guide['matched']['body']
    assert guide['matched']['expanded'] == []
    assert guide['kind_label'] == '手动录入' and guide['editable'] is True


def test_indonesian_expansion_only_for_enriched_documents(corpus):
    store, ids = corpus
    hits = annotate_hits(store, '外籍劳工', retrieve(store, '外籍劳工', limit=10, per_document=True))
    law = next(h for h in hits if h['document_id'] == ids[0])
    assert '外籍劳工' in law['matched']['zh_summary'] and '外籍劳工' in law['matched']['zh_keywords']
    assert law['matched']['body'] == [] or all(t in law['highlight_terms'] for t in law['matched']['body'])
    assert law['matched']['expanded'], 'enriched Indonesian law should explain expanded body terms'
    assert all(t.lower() in LONG_BODY.lower() for t in law['matched']['expanded'])
    for window in law['hit_windows']:
        assert LONG_BODY[window['start']:window['end']] == window['text']
    assert len(law['hit_windows']) <= 3
    spans = sorted((w['start'], w['end']) for w in law['hit_windows'])
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:]))
    lengths = [len(t) for t in law['highlight_terms']]
    assert lengths == sorted(lengths, reverse=True)


def test_summary_only_hit_has_no_body_window(corpus):
    store, ids = corpus
    hits = annotate_hits(store, '营业许可', retrieve(store, '营业许可', limit=10, per_document=True))
    assert [h['document_id'] for h in hits] == [ids[3]]
    pp = hits[0]
    assert '营业许可' in pp['matched']['zh_summary'] or '营业许可' in pp['matched']['zh_keywords']
    assert '营业许可' not in pp['matched']['body']


def test_group_key_strips_archive_prefix_and_normalizes_url(tmp_path):
    store = make_store(tmp_path)
    first, _ = insert_document(store, {'title': '［网页存档 2024-01-01］关于外籍劳工的通知', 'body': '外籍劳工通知正文内容。',
                                       'source': 'a', 'url': 'https://www.example.go.id/berita/1/', 'date': ''}, 'knowledge', True)
    second, _ = insert_document(store, {'title': '关于外籍劳工的通知', 'body': '外籍劳工通知正文内容，另一版本。',
                                        'source': 'a', 'url': 'https://example.go.id/berita/1', 'date': ''}, 'knowledge', True)
    hits = annotate_hits(store, '外籍劳工', retrieve(store, '外籍劳工', limit=10, per_document=True))
    keys = {h['document_id']: h['group_key'] for h in hits}
    assert keys[first] == keys[second] == 'example.go.id/berita/1'


def test_search_endpoint_reports_total_and_limits_items(client):
    store = client.app.state.store
    for index in range(12):
        insert_document(store, {'title': f'外籍劳工政策 {index}', 'body': f'外籍劳工相关规定第{index}条。', 'source': 's', 'date': ''},
                        'knowledge', True)
    data = client.get('/api/knowledge/search?q=外籍劳工').json()
    assert data['total_documents'] == 12 and len(data['items']) == 8 and data['limit'] == 8
    assert all('hit_windows' in item and 'group_key' in item and 'kind_label' in item for item in data['items'])
    assert 'relevance' not in data['items'][0]
    assert client.get('/api/knowledge/search?q=').json() == {'items': [], 'total_documents': 0, 'limit': 8, 'query': ''}


def test_admin_without_company_sees_no_company_profiles(client):
    c = client
    cid = c.post('/api/companies', json={'name': '棉纺测试公司', 'business': '棉花贸易'}).json()['id']
    profile = c.post(f'/api/companies/{cid}/knowledge').json()['id']
    assert profile in [i['document_id'] for i in c.get('/api/knowledge/search?q=棉纺测试').json()['items']]
    with c.app.state.store.db() as db:
        db.execute("UPDATE sessions SET active_company=NULL")
    assert profile not in [i['document_id'] for i in c.get('/api/knowledge/search?q=棉纺测试').json()['items']]
