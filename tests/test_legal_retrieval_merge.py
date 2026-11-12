from app import jobs
from app.model import citation_units


def test_wrapped_statute_units_stop_at_headings_and_stay_verbatim():
    text = ('Pasal 21\n(1) PPMSE wajib\nmenjaga data.\n(2) PPMSE dilarang\nmenjual barang.\n'
            '(3) PPMSE dengan model bisnis Social-Commerce dilarang\nmemfasilitasi transaksi pembayaran.\n'
            'l. menjatuhkan sanksi\nadministratif.\nBagian Kelima\nPembiayaan\nPasal 22\nketentuan lain\nberlaku.')
    units = citation_units({'K1': {'text': text, 'kind': 'knowledge', 'title': 'law'}}).values()
    quotes = [unit['text'] for unit in units]
    assert all(quote in text for quote in quotes)
    assert any(q.startswith('(3) PPMSE') and q.rstrip().endswith('pembayaran.') for q in quotes)
    assert not any('menjatuhkan' in q and 'Bagian' in q for q in quotes)


class _Worker(jobs.Worker):
    def __init__(self):
        self.store = object()


def test_legal_hits_merge_after_general_hits(monkeypatch):
    calls = []

    def fake_retrieve(store, query, **kwargs):
        calls.append((query, kwargs))
        return [{'id': 7, 'document_id': 2}, {'id': 9, 'document_id': 3}]

    monkeypatch.setattr(jobs, 'retrieve', fake_retrieve)
    merged = _Worker()._with_legal_hits([{'id': 7, 'document_id': 2}], [{'text': 'Social commerce payment'}], False, 4)
    assert [hit['id'] for hit in merged] == [7, 9]
    assert calls[0][1]['category'] == 'id_law'
    assert calls[0][1]['per_document'] is False
    assert calls[0][1]['company_id'] == 4


def test_legal_hits_skip_without_facts_or_on_error(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError('x')

    monkeypatch.setattr(jobs, 'retrieve', boom)
    worker = _Worker()
    assert worker._with_legal_hits([{'id': 1}], [{'text': ''}], False, None) == [{'id': 1}]
    assert worker._with_legal_hits([{'id': 1}], [{'text': 'facts'}], False, None) == [{'id': 1}]

