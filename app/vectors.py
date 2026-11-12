"""Local multilingual vectors in a dedicated sqlite-vec database (<data_dir>/vectors.db).

risk.db keeps the business data. vectors.db holds two vec0 tables (knowledge chunks and the 45
third-level indicators) plus small bookkeeping tables, and ATTACHes risk.db only to find chunks
that still lack a vector and to re-check eligibility of KNN hits. Whenever sqlite-vec, fastembed or
the model is unavailable, every caller falls back to BM25 / the per-chunk analysis.
"""
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple

from .indicators import texts as indicator_texts

VECTOR_DB = 'vectors.db'
MODEL_DIR = 'models'
READY_COVERAGE = 0.8
READY_TTL = 5.0
LOAD_RETRY_SECONDS = 600
PRUNE_INTERVAL = 600
SHARED_OWNER = -1
KNN_MAX = 4096
RRF_K = 60
WINDOWS_PER_CHUNK = 3
# Keep the normal worker at the same conservative batch size as the bounded replay.
EMBED_BATCH_SIZE = 2
INDEX_BATCH_SIZE = 2


class ModelSpec(NamedTuple):
    name: str
    query_prefix: str
    passage_prefix: str
    max_chars: int
    min_indicator: float
    min_margin: float
    min_hit: float


# Preference order; the first model fastembed lists in list_supported_models() is used.
# Similarity below is cosine (vec0 distance_metric=cosine, similarity = 1 - distance).
# - intfloat/multilingual-e5-small: needs "query: "/"passage: " prefixes. e5 scores bunch up around
#   0.70-0.90 even for unrelated text, so a 0.2 floor never triggers. Its floors are an uncalibrated
#   starting point: fastembed 0.9 does not ship this model.
# - sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 (0.22 GB, 384 dim, zh/en/id among ~50
#   languages, 128-token input, no prefixes). Measured against the 45 indicator glosses: unrelated text
#   -0.1~0.15, ordinary business news 0.15~0.25, clearly risk-related zh/en/id passages 0.30~0.60.
# Large models (multilingual-e5-large, jina-v3, Qwen3 0.6B: 2.2 GB+) are excluded on a 3.4 GB host.
# RAG_MIN_INDICATOR_SIMILARITY / RAG_MIN_HIT_SIMILARITY override min_indicator / min_hit.
MODEL_SPECS = (
    ModelSpec('intfloat/multilingual-e5-small', 'query: ', 'passage: ', 1000, 0.80, 0.02, 0.80),
    ModelSpec('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', '', '', 400, 0.28, 0.10, 0.30),
)

ELIGIBLE = "d.kind='knowledge' AND d.demo=0 AND d.quarantined_at IS NULL"
FINGERPRINT = "c.document_id||':'||length(c.text)||':'||length(d.title)||':'||length(ifnull(d.zh_keywords,''))"

_lock = threading.RLock()
_state = {'spec': None, 'dim': 0, 'model': None, 'failed_at': 0.0}
_ready_cache = {}
_last_prune = {}


def _env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def active_spec():
    """First preferred model that fastembed supports. Raises when fastembed is missing."""
    with _lock:
        if _state['spec'] is None:
            from fastembed import TextEmbedding
            supported = {item['model']: item for item in TextEmbedding.list_supported_models()}
            spec = next((item for item in MODEL_SPECS if item.name in supported), None)
            if spec is None:
                raise RuntimeError('no supported multilingual embedding model')
            _state['dim'] = int(supported[spec.name]['dim'])
            _state['spec'] = spec
        return _state['spec']


def _model_key():
    return f'{active_spec().name}|{_state["dim"]}'


def _load(store):
    if _state['model'] is not None:
        return _state['model']
    if _state['failed_at'] and time.monotonic() - _state['failed_at'] < LOAD_RETRY_SECONDS:
        raise RuntimeError('embedding model unavailable')
    try:
        from fastembed import TextEmbedding
        spec = active_spec()
        cache = Path(store.directory) / MODEL_DIR
        cache.mkdir(parents=True, exist_ok=True)
        # Default thread count allocates a large ONNX arena and OOM-kills this 3.4GB host.
        _state['model'] = TextEmbedding(spec.name, cache_dir=str(cache), threads=1)
    except Exception:
        _state['failed_at'] = time.monotonic()
        raise
    _state['failed_at'] = 0.0
    return _state['model']


def _model_failed():
    return bool(_state['failed_at']) and time.monotonic() - _state['failed_at'] < LOAD_RETRY_SECONDS


def embed(store, texts, kind='passage'):
    """Blocking; async callers must go through asyncio.to_thread. kind is 'query' or 'passage'."""
    if not texts:
        return []
    with _lock:
        model = _load(store)
        spec = active_spec()
        prefix = spec.query_prefix if kind == 'query' else spec.passage_prefix
        clipped = [prefix + ' '.join((text or '').split())[:spec.max_chars] for text in texts]
        return [[float(value) for value in vector] for vector in model.embed(clipped, batch_size=EMBED_BATCH_SIZE)]


def passage(title, keywords, text):
    return f'{title}\n{(keywords or "")[:80]}\n{text or ""}'


def _windows(text, size):
    body = ' '.join((text or '').split())
    if not body:
        return ['']
    return [body[start:start + size] for start in range(0, len(body), size)][:WINDOWS_PER_CHUNK]


def _blob(vector):
    import sqlite_vec
    return sqlite_vec.serialize_float32(vector)


def _vector_path(store):
    return Path(store.directory) / VECTOR_DB


@contextmanager
def _open(store, create=False):
    import sqlite_vec
    path = _vector_path(store)
    if not create and not path.exists():
        raise FileNotFoundError(str(path))
    conn = sqlite3.connect(str(path), timeout=30)
    try:
        conn.row_factory = sqlite3.Row
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        conn.execute('ATTACH DATABASE ? AS biz', (str(store.path),))
        yield conn
    finally:
        conn.close()


def ensure(store):
    """Create vectors.db and its bookkeeping tables. False when sqlite-vec cannot be loaded."""
    try:
        with _open(store, create=True) as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            conn.execute('''CREATE TABLE IF NOT EXISTS chunk_index(
                chunk_id INTEGER PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                owner INTEGER NOT NULL)''')
            conn.execute('CREATE TABLE IF NOT EXISTS indicator_index(category TEXT PRIMARY KEY, text TEXT NOT NULL)')
            conn.commit()
        return True
    except Exception:
        return False


def _vec_tables(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE name IN ('chunk_vec','indicator_vec')").fetchall()
    return len(rows) == 2


def _prepare(conn):
    """Create the vec0 tables for the active model; rebuild them when the model or dimension changed."""
    key = _model_key()
    row = conn.execute("SELECT value FROM meta WHERE key='model'").fetchone()
    if row and row['value'] == key and _vec_tables(conn):
        return
    dim = int(_state['dim'])
    conn.execute('DROP TABLE IF EXISTS chunk_vec')
    conn.execute('DROP TABLE IF EXISTS indicator_vec')
    conn.execute('DELETE FROM chunk_index')
    conn.execute('DELETE FROM indicator_index')
    conn.execute(f'''CREATE VIRTUAL TABLE chunk_vec USING vec0(
        chunk_id INTEGER PRIMARY KEY,
        embedding float[{dim}] distance_metric=cosine,
        owner INTEGER)''')
    conn.execute(f'''CREATE VIRTUAL TABLE indicator_vec USING vec0(
        category TEXT PRIMARY KEY,
        embedding float[{dim}] distance_metric=cosine)''')
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('model',?)", (key,))
    conn.commit()


def _check_model(conn):
    row = conn.execute("SELECT value FROM meta WHERE key='model'").fetchone()
    if not row or row['value'] != _model_key() or not _vec_tables(conn):
        raise RuntimeError('vector index was not built with the active model')


def _owner_sql(conn):
    """Same ownership rule as retrieve(): document company, else company-profile owner, else shared."""
    has_companies = conn.execute("SELECT 1 FROM biz.sqlite_master WHERE type='table' AND name='companies'").fetchone()
    lookup = '(SELECT co.id FROM biz.companies co WHERE co.document_id=d.id ORDER BY co.id DESC LIMIT 1)' if has_companies else 'NULL'
    return f'COALESCE(NULLIF(d.company_id,0),{lookup},{SHARED_OWNER})'


def _prune(conn, store):
    key = str(_vector_path(store))
    if time.monotonic() - _last_prune.get(key, 0.0) < PRUNE_INTERVAL:
        return
    _last_prune[key] = time.monotonic()
    stale = [row[0] for row in conn.execute(f'''SELECT m.chunk_id FROM chunk_index m
        LEFT JOIN biz.chunks c ON c.id=m.chunk_id
        LEFT JOIN biz.documents d ON d.id=c.document_id
        WHERE c.id IS NULL OR d.id IS NULL OR NOT ({ELIGIBLE})''')]
    for chunk_id in stale:
        conn.execute('DELETE FROM chunk_vec WHERE chunk_id=?', (chunk_id,))
        conn.execute('DELETE FROM chunk_index WHERE chunk_id=?', (chunk_id,))
    conn.commit()


def index_once(store, batch=INDEX_BATCH_SIZE):
    """Embed one batch of indicators or not-yet-indexed knowledge chunks. False when caught up or unavailable."""
    try:
        current = dict(indicator_texts())
        with _open(store) as conn:
            _prepare(conn)
            stored = {row['category']: row['text'] for row in conn.execute('SELECT category,text FROM indicator_index')}
        missing = [(name, text) for name, text in current.items() if stored.get(name) != text]
        extra = [name for name in stored if name not in current]
        if missing or extra:
            vectors = embed(store, [text for _, text in missing], 'passage')
            with _open(store) as conn:
                _check_model(conn)
                for name in extra:
                    conn.execute('DELETE FROM indicator_vec WHERE category=?', (name,))
                    conn.execute('DELETE FROM indicator_index WHERE category=?', (name,))
                for (name, text), vector in zip(missing, vectors):
                    conn.execute('DELETE FROM indicator_vec WHERE category=?', (name,))
                    conn.execute('INSERT INTO indicator_vec(category,embedding) VALUES (?,?)', (name, _blob(vector)))
                    conn.execute('INSERT OR REPLACE INTO indicator_index(category,text) VALUES (?,?)', (name, text))
                conn.commit()
            _ready_cache.clear()
            return True
        with _open(store) as conn:
            owner = _owner_sql(conn)
            pending = [dict(row) for row in conn.execute(f'''SELECT c.id, c.text, d.title, ifnull(d.zh_keywords,'') keywords,
                    {FINGERPRINT} fingerprint, {owner} owner
                FROM biz.chunks c JOIN biz.documents d ON d.id=c.document_id
                LEFT JOIN chunk_index m ON m.chunk_id=c.id
                WHERE {ELIGIBLE} AND (m.chunk_id IS NULL OR m.fingerprint<>{FINGERPRINT} OR m.owner<>{owner})
                ORDER BY c.id LIMIT ?''', (batch,))]
            if not pending:
                _prune(conn, store)
                return False
        vectors = embed(store, [passage(row['title'], row['keywords'], row['text']) for row in pending], 'passage')
        with _open(store) as conn:
            _check_model(conn)
            for row, vector in zip(pending, vectors):
                conn.execute('DELETE FROM chunk_vec WHERE chunk_id=?', (row['id'],))
                conn.execute('INSERT INTO chunk_vec(chunk_id,embedding,owner) VALUES (?,?,?)', (row['id'], _blob(vector), row['owner']))
                conn.execute('INSERT OR REPLACE INTO chunk_index(chunk_id,fingerprint,owner) VALUES (?,?,?)',
                             (row['id'], row['fingerprint'], row['owner']))
            conn.commit()
        _ready_cache.clear()
        return True
    except Exception:
        return False


def index_status(store):
    """Counts read from vectors.db without loading the model."""
    with _open(store) as conn:
        model = conn.execute("SELECT value FROM meta WHERE key='model'").fetchone()
        if not model or not _vec_tables(conn):
            return {'model': None, 'indicators': 0, 'chunks_indexed': 0, 'chunks_total': 0}
        current = dict(indicator_texts())
        indicators = sum(1 for row in conn.execute('SELECT category,text FROM indicator_index') if current.get(row['category']) == row['text'])
        total = conn.execute(f'SELECT COUNT(*) FROM biz.chunks c JOIN biz.documents d ON d.id=c.document_id WHERE {ELIGIBLE}').fetchone()[0]
        have = conn.execute(f'''SELECT COUNT(*) FROM chunk_index m JOIN biz.chunks c ON c.id=m.chunk_id
            JOIN biz.documents d ON d.id=c.document_id WHERE {ELIGIBLE} AND m.fingerprint={FINGERPRINT}''').fetchone()[0]
    return {'model': model['value'].split('|')[0], 'indicators': indicators, 'chunks_indexed': have, 'chunks_total': total}


def _status_cached(store):
    key = str(_vector_path(store))
    cached = _ready_cache.get(key)
    if cached and time.monotonic() - cached[0] < READY_TTL:
        return cached[1]
    try:
        info = index_status(store)
    except Exception:
        info = None
    _ready_cache[key] = (time.monotonic(), info)
    return info


def indicators_ready(store):
    if _model_failed():
        return False
    info = _status_cached(store)
    return bool(info and info['model'] and info['indicators'] == len(indicator_texts()))


def ready(store):
    """Knowledge-chunk vectors cover enough of the corpus for hybrid retrieval."""
    if not indicators_ready(store):
        return False
    info = _status_cached(store)
    return bool(info['chunks_total']) and info['chunks_indexed'] / info['chunks_total'] >= READY_COVERAGE


def status(store):
    try:
        info = index_status(store)
    except Exception as error:
        return {'available': False, 'error': type(error).__name__, 'ready': False, 'indicators_ready': False}
    return {**info, 'available': True, 'model_failed': _model_failed(),
            'indicators_ready': indicators_ready(store), 'ready': ready(store)}


def similar_chunks(store, text, limit, external, company_id):
    """vec0 KNN over knowledge chunks, re-checked against risk.db. Raises on any failure."""
    spec = active_spec()
    query = _blob(embed(store, [text], 'query')[0])
    owner_id = company_id or 0
    condition = ''  # All in-scope, non-quarantined knowledge can support analysis.
    with _open(store) as conn:
        _check_model(conn)
        owner = _owner_sql(conn)
        rows = conn.execute(f'''WITH knn AS (
                SELECT chunk_id, distance FROM chunk_vec
                WHERE embedding MATCH ? AND k = ? AND owner IN (?, ?))
            SELECT knn.chunk_id, c.document_id, 1 - knn.distance similarity
            FROM knn JOIN biz.chunks c ON c.id=knn.chunk_id JOIN biz.documents d ON d.id=c.document_id
            WHERE d.kind='knowledge' AND d.demo=0 AND d.quarantined_at IS NULL{condition} AND {owner} IN (?, ?)
            ORDER BY knn.distance''',
            (query, min(KNN_MAX, max(limit * 4, 32)), SHARED_OWNER, owner_id, SHARED_OWNER, owner_id)).fetchall()
    floor = _env_float('RAG_MIN_HIT_SIMILARITY', spec.min_hit)
    return [dict(row) for row in rows if row['similarity'] >= floor][:limit]


def fuse_hits(store, query, bm25_rows, limit, external, company_id, per_document):
    """Reciprocal-rank fusion of BM25 and vec0 KNN. None means keep the BM25 list exactly as it is.

    'score' stays the BM25 score (0.0 for vector-only hits) because callers may threshold it;
    the order follows 'fused_rank'.
    """
    if not ready(store):
        return None
    try:
        return _fuse(store, query, bm25_rows, limit, external, company_id, per_document)
    except Exception:
        return None


def _fuse(store, query, bm25_rows, limit, external, company_id, per_document):
    vector_hits = similar_chunks(store, query, max(limit, 8) * (3 if per_document else 1), external, company_id)
    if not vector_hits:
        return None
    rows, bm25_rank, vector_rank, similarity, vector_chunk = {}, {}, {}, {}, {}
    for row in bm25_rows:
        key = row['document_id'] if per_document else row['id']
        if key not in bm25_rank:
            bm25_rank[key] = len(bm25_rank) + 1
            rows[key] = row
    for hit in vector_hits:
        key = hit['document_id'] if per_document else hit['chunk_id']
        if key not in vector_rank:
            vector_rank[key] = len(vector_rank) + 1
            similarity[key] = hit['similarity']
            vector_chunk[key] = hit['chunk_id']
    missing = [vector_chunk[key] for key in vector_rank if key not in rows]
    if missing:
        profiles = set()
        if per_document and store.one("SELECT name FROM sqlite_master WHERE type='table' AND name='companies'"):
            profiles = {row['document_id'] for row in store.rows('SELECT document_id FROM companies WHERE document_id IS NOT NULL')}
        marks = ','.join('?' for _ in missing)
        for row in store.rows(f'''SELECT c.id,c.document_id,c.locator,c.text,c.section_type,d.legal_meta,d.title,d.source,d.date,d.zh_summary,d.zh_keywords
                FROM chunks c JOIN documents d ON d.id=c.document_id WHERE c.id IN ({marks})''', tuple(missing)):
            # BM25 only lets a company profile through per-document search on a title match.
            if row['document_id'] in profiles:
                continue
            item = dict(row)
            if not per_document:
                item.pop('zh_summary', None)
                item.pop('zh_keywords', None)
            item['score'] = 0.0
            rows[row['document_id'] if per_document else row['id']] = item
    unranked = len(bm25_rank) + len(vector_rank) + 1

    def fused_score(key):
        return sum(1 / (RRF_K + ranks[key]) for ranks in (bm25_rank, vector_rank) if key in ranks)

    order = sorted(rows, key=lambda key: (-fused_score(key), bm25_rank.get(key, unranked), vector_rank.get(key, unranked)))
    fused = []
    for position, key in enumerate(order[:limit], 1):
        item = dict(rows[key])
        item['fused_rank'] = position
        item['bm25_rank'] = bm25_rank.get(key)
        item['vector_rank'] = vector_rank.get(key)
        item['vector_similarity'] = round(similarity[key], 3) if key in similarity else None
        fused.append(item)
    return fused


def concern_categories(concerns, names):
    """Indicator names written in the client's concerns, longest match only: 合同执行风险 does not also select 执行风险."""
    spans = []
    for name in names:
        spans.extend((match.start(), match.end(), name) for match in re.finditer(re.escape(name), concerns or ''))
    found = []
    for start, end, name in sorted(spans):
        if any(left <= start and end <= right and right - left > end - start for left, right, _ in spans):
            continue
        if name not in found:
            found.append(name)
    return found


def indicator_scores(store, chunks):
    """Cosine similarity of every chunk to every indicator via vec0 KNN (k = all indicators).

    Long chunks are scored on up to WINDOWS_PER_CHUNK windows because the model truncates its input.
    """
    spec = active_spec()
    windows, owners = [], []
    for index, chunk in enumerate(chunks):
        for piece in _windows(chunk['text'], spec.max_chars):
            windows.append(piece)
            owners.append(index)
    vectors = embed(store, windows, 'query')
    total = len(indicator_texts())
    scores = [{} for _ in chunks]
    with _open(store) as conn:
        _check_model(conn)
        for index, vector in zip(owners, vectors):
            for row in conn.execute('SELECT category, distance FROM indicator_vec WHERE embedding MATCH ? AND k = ?', (_blob(vector), total)):
                similarity = 1 - row['distance']
                if similarity > scores[index].get(row['category'], -2.0):
                    scores[index][row['category']] = similarity
    return scores


def plan_sources(store, chunks, concerns, allowed, max_categories=6, max_sources=8):
    """Vector-preselected indicators, each with at least one source chunk. None keeps the per-chunk path.

    Raises on embedding / vector errors; the caller treats that like None.
    """
    if not chunks or not indicators_ready(store):
        return None
    spec = active_spec()
    names = [name for name, _ in indicator_texts()]
    allowed_names = [name for name in names if name in allowed]
    if len(allowed_names) < 3:
        return None
    scores = indicator_scores(store, chunks)
    best = {name: max(item.get(name, -1.0) for item in scores) for name in names}
    top = max(best.values())
    mean = sum(best.values()) / len(best)
    floor = _env_float('RAG_MIN_INDICATOR_SIMILARITY', spec.min_indicator)
    # Low top score, or a top score that barely stands out from the average, means no indicator really fits.
    if top < floor or top - mean < spec.min_margin:
        return None
    chosen = [name for name in concern_categories(concerns, names) if name in allowed_names][:max_sources]
    for name in sorted(allowed_names, key=lambda item: best[item], reverse=True):
        if len(chosen) >= max_categories or best[name] < floor:
            break
        if name not in chosen:
            chosen.append(name)
    if len(chosen) < 3:
        return None
    order = {name: sorted(range(len(chunks)), key=lambda index: scores[index].get(name, -1.0), reverse=True) for name in chosen}
    by_category = {name: [order[name][0]] for name in chosen}
    picked = list(dict.fromkeys(order[name][0] for name in chosen))
    progressed = True
    while progressed and len(picked) < max_sources:
        progressed = False
        for name in chosen:
            if len(picked) >= max_sources:
                break
            index = next((item for item in order[name] if item not in picked and scores[item].get(name, -1.0) >= floor), None)
            if index is not None:
                picked.append(index)
                by_category[name].append(index)
                progressed = True
    picked.sort()
    return {'categories': chosen,
            'sources': [chunks[index] for index in picked],
            'category_chunks': {name: [chunks[index]['id'] for index in by_category[name]] for name in chosen},
            'top_similarity': round(top, 3),
            'floor': floor,
            'model': spec.name}


class Indexer:
    def __init__(self, store, settings):
        self.store, self.settings, self.task = store, settings, None

    def start(self):
        import asyncio
        self.task = asyncio.create_task(self.loop())

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except BaseException:
                pass

    async def loop(self):
        import asyncio
        while True:
            worked = await asyncio.to_thread(index_once, self.store)
            await asyncio.sleep(0.2 if worked else 30)
