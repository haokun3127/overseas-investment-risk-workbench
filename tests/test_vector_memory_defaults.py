from app import vectors


def test_conservative_embedding_batch_preserves_all_inputs_and_vectors(monkeypatch):
    class FakeModel:
        def embed(self, texts, *, batch_size):
            assert batch_size == 2
            assert texts == ['query: ' + 'alpha beta'] * 39
            for i in range(len(texts)):
                yield [i, i + 0.5]

    monkeypatch.setattr(vectors, '_load', lambda store: FakeModel())
    monkeypatch.setattr(vectors, 'active_spec', lambda: vectors.ModelSpec(
        'synthetic-test', 'query: ', 'passage: ', 400, 0, 0, 0))
    result = vectors.embed(None, ['alpha\n beta'] * 39, kind='query')
    assert result == [[float(i), i + 0.5] for i in range(39)]
