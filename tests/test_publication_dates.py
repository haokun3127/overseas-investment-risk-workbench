import io
import json
import sqlite3

import pytest
from docx import Document

from app.ingest import insert_document, parse_file
from app.publication import from_html, from_text, normalize, from_snapshot, from_disclosure_url
from app.store import Store
from app.main import create_app
from app.config import Settings
from scripts.backfill_publication_dates import plan, apply


@pytest.mark.parametrize('text, expected', [
    ('新闻标题\n发布时间：2020/04/27\n3月发生事件。', '2020-04-27'),
    ('新闻标题\n2020-03-16 11:00\n3月14日开展工作。', '2020-03-16'),
    ('Rabu, 27 September 2023\nPukul 21:47 WIB', '2023-09-27'),
    ('Published on October 4, 2023\nArticle text', '2023-10-04'),
    ('发布日期：2026年11月4日\n正文', '2026-11-04'),
    ('2023年10月4日，企业停止交易。2024年1月31日完成合并。', ''),
    ('法规于2023年9月26日生效。', ''),
    ('更新时间：2026-11-04', ''),
    ('发布日期：2026-02-30', ''),
    ('发布日期：2023-01-01\n发布日期：2024-01-01', ''),
    ('2023-01-01\n2024-01-01', ''),
])
def test_publication_requires_own_date(text, expected):
    assert from_text(text)[0] == expected


def test_html_metadata_does_not_use_modification_or_related_dates():
    html = '<meta property="article:modified_time" content="2026-11-04"><script type="application/ld+json">' + json.dumps({
        '@type': 'NewsArticle', 'datePublished': '2023-10-04T17:00:00+07:00',
        'dateModified': '2026-11-04', 'relatedLink': {'datePublished': '2025-01-01'}}) + '</script>'
    assert from_html(html)[0:2] == ('2023-10-04', 'page_meta')
    assert from_html('<meta property="article:modified_time" content="2026-11-04">')[0] == ''
    assert from_html('<meta name="pubdate" content="2023-10-04"><meta name="date" content="2024-01-01">')[0] == ''


def test_publication_byline_can_be_after_long_body():
    html = '<p>' + '旧事件发生于2020年1月1日。' * 300 + '</p><div class="entry-meta"><p>By ministry</p><span>Rabu, 27 September 2023</span><span>Pukul 21:47 WIB</span></div>'
    assert from_html(html)[0:2] == ('2023-09-27', 'page_text')


def test_ingest_fills_publication_but_preserves_manual_and_excerpt_dates(tmp_path):
    store = Store(tmp_path)
    body = '发布时间：2020/04/27\n原文报道'
    auto, _ = insert_document(store, {'title': '原文', 'body': body})
    manual, _ = insert_document(store, {'title': '手动', 'body': body, 'date': '2020-05-01'})
    excerpt, _ = insert_document(store, {'title': '摘录', 'body': body, 'source': '事件事实摘录'})
    assert store.one('SELECT date,date_source FROM documents WHERE id=?', (auto,)) == {'date': '2020-04-27', 'date_source': 'page_text'}
    assert store.one('SELECT date,date_source FROM documents WHERE id=?', (manual,)) == {'date': '2020-05-01', 'date_source': 'provided'}
    assert store.one('SELECT date FROM documents WHERE id=?', (excerpt,))['date'] == ''


def test_docx_import_extracts_header_not_core_created_time(tmp_path):
    doc = Document()
    doc.add_paragraph('报道标题')
    doc.add_paragraph('发布时间：2020/04/27')
    doc.add_paragraph('事件发生于2020年3月16日。')
    stream = io.BytesIO()
    doc.save(stream)
    record = parse_file('报道.docx', stream.getvalue())[0]['record']
    store = Store(tmp_path)
    document, _ = insert_document(store, record)
    assert store.one('SELECT date,date_source FROM documents WHERE id=?', (document,))['date'] == '2020-04-27'


def test_backfill_is_readonly_audited_backed_up_and_non_overwriting(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / 'data'), run_worker=False)
    store = app.state.store
    doc, _ = insert_document(store, {'title': '参考原文', 'body': '2020年发生事件'}, kind='knowledge', file_path='ref.html')
    (store.directory / 'uploads' / 'ref.html').write_text('<meta property="article:published_time" content="2023-10-04">')
    before = (store.directory / 'risk.db').read_bytes()
    report = plan(store.directory)
    assert (store.directory / 'risk.db').read_bytes() == before
    assert len(report['items']) == 1 and report['items'][0]['date'] == '2023-10-04'
    backup = tmp_path / 'backup.db'
    assert apply(store.directory, report, backup) == 1
    assert backup.exists()
    with sqlite3.connect(backup) as db:
        assert db.execute('SELECT date FROM documents WHERE id=?', (doc,)).fetchone()[0] == ''
    assert plan(store.directory)['items'] == []
    with pytest.raises(ValueError):
        apply(store.directory, report, tmp_path / 'second-backup.db')


def test_backfill_source_change_aborts(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / 'data'), run_worker=False)
    doc, _ = insert_document(app.state.store, {'title': '参考', 'body': '无日期'}, kind='knowledge', file_path='ref.html')
    raw = app.state.store.directory / 'uploads' / 'ref.html'
    raw.write_text('<meta name="pubdate" content="2023-10-04">')
    report = plan(app.state.store.directory)
    raw.write_text('<meta name="pubdate" content="2024-01-01">')
    with pytest.raises(ValueError, match='Sources changed'):
        apply(app.state.store.directory, report, tmp_path / 'backup.db')


def test_webpage_detail_keeps_date_provenance(tmp_path):
    from fastapi.testclient import TestClient
    app = create_app(Settings(data_dir=tmp_path / 'data'), run_worker=False)
    with app.state.store.db() as db:
        run = db.execute("INSERT INTO web_runs(source_id,config_json,status,created_at) VALUES (1,'{}','completed','x')").lastrowid
        page = db.execute("INSERT INTO web_pages(run_id,url,title,body,date,date_source,fetched_at,digest,snapshot) VALUES (?,'https://example.com','title','body','1990-05-31','document_text','x','digest','ref.pdf')", (run,)).lastrowid
    with TestClient(app, headers={'X-Requested-With': 'risk-workbench'}) as client:
        client.post('/api/auth/setup', json={'password': 'isolated-date-test-password'})
        result = client.get(f'/api/web/pages/{page}').json()
        assert result['date_source'] == 'document_text' and result['date'] == '1990-05-31'


@pytest.mark.parametrize('text, expected, source', [
    ('SANY factory news\n19/08/2022\nOn August 15th a factory opened.', '2022-08-19', 'document_text'),
    ('Release Date\n01/14/2021\nOFAC announces settlement.', '2021-01-14', 'page_text'),
    ('Release time：2024.08.07\nBTR news', '2024-08-07', 'page_text'),
    ('Enforcement Release: January 14, 2021\nOFAC', '2021-01-14', 'page_text'),
    ('Januari 31, 2024•Perusahaan\nGoTo dan TikTok', '2024-01-31', 'document_text'),
    ('ICSID AWARD\nDate of dispatch to the Parties: 6 December 2016', '2016-12-06', 'document_dispatch'),
    ('ICSID ORDER\nDATE: August 29, 2014', '2014-08-29', 'document_text'),
    ('[第1页]\n社会社会 1414 2022 年 6 月 13 日 星期一\n新闻正文', '2022-06-13', 'page_text'),
    ('报道标题\n2023年10月4日，企业停止交易。', '', ''),
    ('updated : 08/12/2016\nA news item', '', ''),
    ('As of December 31, 2014\nReserves and Resources', '', ''),
    ('Date Registered:\nMay 19, 2011\nCase Details', '', ''),
    ('Case Details\nDate Registered:\nMay 19, 2011\nDate of Constitution of Tribunal:\nSeptember 21, 2011', '', ''),
    ('Date of Constitution of Tribunal:\nSeptember 21, 2011', '', ''),
])
def test_publication_real_world_formats(text, expected, source):
    assert from_text(text)[:2] == (expected, source)


def test_dates_do_not_guess_numeric_locale_or_allow_invalid_ranges():
    assert normalize('08/12/2016') == ''
    assert normalize('19/08/2022') == '2022-08-19'
    assert normalize('01/14/2021') == '2021-01-14'
    assert normalize('10th May 1988') == '1988-05-10'
    assert normalize('13/13/2023') == ''
    assert normalize('01/14/1800') == ''


def test_signature_dates_need_signature_context_and_use_full_document():
    body = '公告\n' + '事件发生于2026年3月13日。\n' * 400
    assert from_text(body + '特此公告！\n赞宇科技集团股份有限公司\n董事会\n2026 年 3月 16 日')[:2] == ('2026-03-16', 'document_signature')
    assert from_text(body + '历史上发生的交易如下\n2026 年 3月 16 日')[0] == ''
    english = body + 'By Order of the Board\nPhilip Cecil Rickard\nExecutive Director and Chief Executive Officer\n12 June 2017\nSponsor information'
    assert from_text(english)[:2] == ('2017-06-12', 'document_signature')
    legal = 'AMCO v. Republic of Indonesia\nDecision on Jurisdiction\n' + 'Narrative\n' * 500
    assert from_text(legal + 'London 10th May 1988\nIS/\nRosalyn Higgins IS/')[:2] == ('1988-05-10', 'document_signature')
    assert from_text('Ordinary news\n' + 'Narrative\n' * 500 + 'London 10th May 1988\nIS/')[0] == ''


@pytest.mark.parametrize('url, expected', [
    ('https://static.cninfo.com.cn/finalpage/2026-08-24/1225489200.PDF', '2026-08-24'),
    ('https://disc.static.szse.cn/disc/disk03/finalpage/2026-03-17/6aad0034-8e86-4781-94cf-fe972bea0f84.PDF', '2026-03-17'),
    ('https://www1.hkexnews.hk/listedco/listconews/sehk/2025/0317/2025031700019.pdf', '2025-03-17'),
    ('https://www1.hkexnews.hk/listedco/listconews/sehk/2025/0317/2025031800019.pdf', ''),
    ('https://static.cninfo.com.cn.evil.test/finalpage/2026-08-24/1225489200.PDF', ''),
    ('https://static.cninfo.com.cn/finalpage/2026-02-30/1225489200.PDF', ''),
    ('https://news.test/2026-08-24/story', ''),
    ('https://static.cninfo.com.cn:invalid/finalpage/2026-08-24/1225489200.PDF', ''),
])
def test_official_disclosure_path_is_narrow_and_distinct(url, expected):
    result = from_disclosure_url(url)
    assert result[0] == expected
    if expected:
        assert result[1:] == ('disclosure_path', url)


def test_original_pdf_date_shared_across_split_documents(tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    stream = io.BytesIO()
    writer = PdfWriter()
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
    for text in ('ICSID Award\\nDate of dispatch to the Parties: 6 December 2016', 'A different section without its own date'):
        page = writer.add_blank_page(600, 800)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
        content = DecodedStreamObject()
        content.set_data(('BT /F1 12 Tf 30 750 Td ' + ' 0 -20 Td '.join('(' + line + ') Tj' for line in text.split('\\n')) + ' ET').encode('ascii'))
        page[NameObject('/Contents')] = content
    writer.write(stream)
    raw = stream.getvalue()
    assert from_snapshot(raw, 'application/pdf')[:2] == ('2016-12-06', 'document_dispatch')
    app = create_app(Settings(data_dir=tmp_path / 'data'), run_worker=False)
    uploads = app.state.store.directory / 'uploads'
    (uploads / 'award.pdf').write_bytes(raw)
    doc, _ = insert_document(app.state.store, {'title': 'Award volume 2', 'body': '1980-01-01\nA historical date in a later section'}, kind='knowledge', file_path='award.pdf')
    assert app.state.store.one('SELECT date,date_source FROM documents WHERE id=?', (doc,)) == {'date': '2016-12-06', 'date_source': 'document_dispatch'}
    with app.state.store.db() as db:
        db.execute("UPDATE documents SET date='',date_source='' WHERE id=?", (doc,))
    report = plan(app.state.store.directory)
    assert report['items'][0]['date'] == '2016-12-06'
    assert report['items'][0]['snapshot_sha256']


def test_web_keep_fills_empty_date_before_truncation(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / 'data'), run_worker=False)
    runner = app.state.collector
    with app.state.store.db() as db:
        run = db.execute("INSERT INTO web_runs(source_id,config_json,status,created_at) VALUES (1,'{}','running','x')").lastrowid
    pages = []
    runner.keep(run, pages, 'https://example.com/news', 'BTR', 'Release time：2024.08.07\nNews', '', b'<h1>BTR</h1>', 'text/html')
    row = app.state.store.one('SELECT date,date_source FROM web_pages WHERE id=?', (pages[0]['id'],))
    assert row == {'date': '2024-08-07', 'date_source': 'page_text'}
