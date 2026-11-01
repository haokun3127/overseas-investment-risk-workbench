import math
import re
from collections import Counter
from urllib.parse import urlsplit
from .vectors import fuse_hits

_STOP_SPLIT = re.compile(r"[的了和与及或在对于向从以由把被让给并而但且或及]")

_CROSS_LINGUAL_MAP = {
    "外籍": ("tka", "rptka", "dkptka", "asing", "tenaga", "kemnaker", "permenaker"),
    "劳工": ("ketenagakerjaan", "pekerja", "pekerjaan", "buruh", "tenaga", "kemnaker", "permenaker", "tka", "rptka", "labor", "labour"),
    "劳动": ("ketenagakerjaan", "pekerja", "buruh", "tenaga", "kemnaker", "permenaker", "kerja"),
    "用工": ("ketenagakerjaan", "pekerja", "tenaga", "kerja", "tka", "rptka"),
    "工资": ("upah", "ump", "umk", "umr", "minimum", "pengupahan", "subsidi", "gaji", "wage"),
    "解雇": ("phk", "pemutusan", "hubungan", "pesangon"),
    "裁员": ("phk", "pemutusan", "hubungan", "pesangon"),
    "罢工": ("mogok", "serikat", "pekerja"),
    "许可": ("perizinan", "berusaha", "oss", "nib", "izin", "bkpm", "rptka", "license", "licensing"),
    "商业": ("berusaha", "usaha", "perdagangan", "niaga", "business", "commercial"),
    "外资": ("pma", "penanaman", "modal", "asing", "bkpm", "dni", "investment", "foreign"),
    "准入": ("bidang", "usaha", "penanaman", "modal", "dni", "daftar", "negatif", "perpres"),
    "负面": ("negatif", "daftar", "dni", "tertutup", "terbatas"),
    "环评": ("amdal", "ukl", "upl", "lingkungan", "hidup", "persetujuan"),
    "环保": ("lingkungan", "hidup", "amdal", "limbah", "b3", "emisi"),
    "本地": ("tkdn", "komponen", "dalam", "negeri", "lokal"),
    "国产": ("tkdn", "komponen", "dalam", "negeri"),
    "关税": ("bea", "masuk", "keluar", "tarif", "kepabeanan", "customs", "tariff", "duty"),
    "清关": ("kepabeanan", "pabean", "impor", "ekspor", "larangan", "pembatasan", "lartas"),
    "进口": ("impor", "persetujuan", "pi", "lartas", "permendag", "import"),
    "出口": ("ekspor", "larangan", "dmo", "pe", "export"),
    "原产": ("ska", "form", "origin", "coo", "fta", "rcep", "acfta"),
    "垄断": ("persaingan", "usaha", "kppu", "monopoli", "kartel", "antitrust"),
    "竞争": ("persaingan", "usaha", "kppu", "komisi", "pengawas"),
    "制裁": ("sanctions", "ofac", "sdn", "blocked", "entity", "ssi"),
    "强迫": ("uflpa", "forced", "labor", "uyghur", "cbp", "withhold"),
    "仲裁": ("arbitrase", "arbitration", "icsid", "pca", "siac", "bani", "unctad", "award", "dispute"),
    "法院": ("mahkamah", "agung", "konstitusi", "pengadilan", "putusan", "perkara", "mkri"),
    "判决": ("putusan", "mahkamah", "pengadilan", "perkara", "kamar", "yurisprudensi"),
    "税收": ("pajak", "pph", "ppn", "tax", "holiday", "allowance", "kemenkeu", "pmk"),
    "税务": ("pajak", "direktorat", "jenderal", "pph", "ppn", "tax"),
    "矿业": ("pertambangan", "minerba", "iup", "iupk", "rkab", "nikel", "esdm"),
    "镍矿": ("nikel", "nickel", "minerba", "hilirisasi", "smelter", "esdm"),
    "土地": ("pertanahan", "hgb", "hgu", "hak", "guna", "bangunan", "agraria", "atr", "bpn"),
    "外汇": ("devisa", "dhe", "sda", "rupiah", "bank", "indonesia", "pbi"),
}

# Chinese queries often use a near-synonym that never appears in the foreign text or its summary.
_SYNONYM_OF = {
    "薪酬": "工资",
    "薪资": "工资",
    "报酬": "工资",
    "工钱": "工资",
    "执照": "许可",
    "营业执照": "许可",
}
_FUNCTION_ZH = {"怎么", "哪些", "是否", "规定", "要求", "法律", "什么", "如何", "可以", "进行", "关于", "以及"}
_LATIN_STOP = {"dan", "yang", "untuk", "dari", "dengan", "atau", "pada", "dalam", "akan", "tidak", "ini", "itu", "the", "and", "for"}
_SPECIFIC = {term for values in _CROSS_LINGUAL_MAP.values() for term in values if len(term) >= 3}

def tokens(text, expand=False):
    words = re.findall(r"[a-z0-9]{2,}", text.lower())
    for phrase in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(phrase) == 2:
            words.append(phrase)
            continue
        words.extend(phrase[i:i+2] for i in range(len(phrase)-1))
        for seg in _STOP_SPLIT.split(phrase):
            if len(seg) == 2:
                words.append(seg)
    if expand:
        extra = []
        for w in list(words):
            if w in _CROSS_LINGUAL_MAP:
                extra.extend(_CROSS_LINGUAL_MAP[w])
        words.extend(extra)
    return words

def _core_count(terms):
    count = 0
    for term in terms:
        if term in _FUNCTION_ZH or term in _LATIN_STOP:
            continue
        if re.fullmatch(r"[a-z0-9]{2,}", term) or term in _CROSS_LINGUAL_MAP or term in _SYNONYM_OF:
            count += 1
    return count

def _concept_groups(query, allow_expand=True):
    raw = list(dict.fromkeys(tokens(query, expand=False)))
    groups = []
    for term in raw:
        canon = _SYNONYM_OF.get(term, term)
        syns = {term}
        if canon != term:
            syns.add(canon)
        if allow_expand:
            syns.update(_CROSS_LINGUAL_MAP.get(canon, ()))
            syns.update(_CROSS_LINGUAL_MAP.get(term, ()))
        groups.append(syns)
    return raw, groups

def _group_hits(groups, terms):
    return sum(1 for group in groups if group & terms)

def _bm25_concepts(groups, counters):
    if not counters or not groups:
        return [0.0] * len(counters), [0] * len(counters)
    average = sum(sum(c.values()) for c in counters) / max(len(counters), 1) or 1
    frequency = Counter(term for c in counters for term in c)
    total = len(counters)
    scores, matched_groups = [], []
    for terms in counters:
        length = sum(terms.values())
        score = 0.0
        hit_groups = 0
        for grp in groups:
            common = grp & terms.keys()
            if not common:
                continue
            hit_groups += 1
            best_term_score = 0.0
            for term in common:
                idf = math.log(1 + (total - frequency[term] + 0.5) / (frequency[term] + 0.5))
                ts = idf * terms[term] * 2.2 / (terms[term] + 1.2 * (0.25 + 0.75 * length / average))
                if ts > best_term_score:
                    best_term_score = ts
            score += best_term_score
        scores.append(score)
        matched_groups.append(hit_groups)
    return scores, matched_groups

def retrieve(store, query, external=False, limit=4, company_id=None, per_document=False):
    condition = " AND d.allow_external=1" if external else ""
    rows = store.rows("""SELECT c.id,c.document_id,c.locator,c.text,d.title,d.source,d.date,d.zh_summary,d.zh_keywords,d.company_id FROM chunks c
        JOIN documents d ON d.id=c.document_id WHERE d.kind='knowledge' AND d.demo=0 AND d.quarantined_at IS NULL""" + condition + " ORDER BY c.id")
    scoped = store.rows("SELECT document_id,id FROM companies WHERE document_id IS NOT NULL") if store.one("SELECT name FROM sqlite_master WHERE type='table' AND name='companies'") else []
    owners = {r["document_id"]: r["id"] for r in scoped}
    if company_id is None:
        company_id = 0
    filtered_rows = []
    for r in rows:
        doc_cid = r.get("company_id") or owners.get(r["document_id"])
        if doc_cid is not None and doc_cid != company_id:
            continue
        filtered_rows.append(r)
    rows = filtered_rows
    if not rows:
        return []
    raw_list, groups_raw = _concept_groups(query, allow_expand=False)
    _, groups_exp = _concept_groups(query, allow_expand=True)
    if not raw_list:
        return []
    raw_query_terms = set(raw_list)
    expanded_query_terms = set(tokens(query, expand=True))

    doc_ids = list(dict.fromkeys(r["document_id"] for r in rows))
    doc_first = {r["document_id"]: r for r in reversed(rows)}
    doc_counters = [Counter(tokens(" ".join((doc_first[did]["title"], doc_first[did]["zh_keywords"], doc_first[did]["zh_summary"])))) for did in doc_ids]
    doc_scores_raw, _ = _bm25_concepts(groups_raw, doc_counters)
    doc_scores_exp, _ = _bm25_concepts(groups_exp, doc_counters)
    doc_scores = {
        did: (s_exp if (doc_first[did]["zh_summary"] or doc_first[did]["zh_keywords"]) else s_raw)
        for did, s_raw, s_exp in zip(doc_ids, doc_scores_raw, doc_scores_exp)
    }

    chunk_counters = [Counter(tokens(r["text"])) for r in rows]
    chunk_scores_raw, _ = _bm25_concepts(groups_raw, chunk_counters)
    chunk_scores_exp, _ = _bm25_concepts(groups_exp, chunk_counters)

    ranked = []
    core_n = _core_count(raw_list)
    has_cjk_query = bool(re.search(r"[\u4e00-\u9fff]", query))
    for index, (row, c_raw, c_exp) in enumerate(zip(rows, chunk_scores_raw, chunk_scores_exp)):
        did = row["document_id"]
        doc_index = doc_ids.index(did)
        enriched = bool(row["zh_summary"] or row["zh_keywords"])
        title_tokens = set(tokens(row["title"]))
        raw_doc = doc_scores_raw[doc_index]
        exp_doc = doc_scores_exp[doc_index]
        # A Chinese summary/keyword/title hit stays at full weight. A foreign body that matches the
        # expanded terms, while the summary never states the Chinese meaning, is kept behind those hits.
        summary_side = raw_doc > 0 or exp_doc > 0 or bool(expanded_query_terms & title_tokens)
        demote = 1.0
        if has_cjk_query and enriched and not summary_side:
            body_terms = set(chunk_counters[index])
            body_hits = _group_hits(groups_exp, body_terms)
            specific = any((group & body_terms) & _SPECIFIC for group in groups_exp)
            if body_hits < 2 and not specific:
                continue
            demote = 0.35
        active_groups = groups_exp if enriched else groups_raw
        q_terms = expanded_query_terms if enriched else raw_query_terms
        c_score = c_exp if enriched else c_raw
        # Weight document-level Chinese summary/keyword raw hits higher than expanded body hits
        base_score = raw_doc * 1.5 + doc_scores[did] * 0.5 + c_score * 0.4
        if base_score <= 0:
            continue
        all_doc_tokens = set(tokens(" ".join((row["title"], row["zh_keywords"], row["zh_summary"], row["text"]))))
        matched_concepts = sum(1 for grp in active_groups if grp & all_doc_tokens)
        title_hit = bool(q_terms & set(tokens(row["title"])))
        coverage_discount = 0.45 if core_n >= 2 and matched_concepts <= 1 and not title_hit else 1.0
        if per_document and did in owners:
            specific_title_terms = set(tokens(row["title"])) - {"印尼", "印度", "度尼", "尼西", "西亚", "有限", "限公", "公司"}
            if not (raw_query_terms & specific_title_terms):
                continue
        coverage_boost = (1.0 + 0.6 * max(0, matched_concepts - 1)) ** 2
        raw_rank = base_score * coverage_boost * coverage_discount
        row.pop("company_id", None)
        row["_mc"] = matched_concepts
        row["_tier"] = 0 if demote < 1 else 1
        row["_pre"] = raw_rank
        row["score"] = round(raw_rank * demote, 3)
        ranked.append(row)
    ranked.sort(key=lambda r: (r["_tier"], r["_mc"], r["score"], -r["id"]), reverse=True)
    if ranked:
        top_score = max(r["_pre"] for r in ranked)
        ranked = [r for r in ranked if r["_pre"] >= top_score * 0.25]
    for r in ranked:
        r.pop("_mc", None)
        r.pop("_tier", None)
        r.pop("_pre", None)
    if per_document:
        seen = set()
        ranked = [r for r in ranked if not (r["document_id"] in seen or seen.add(r["document_id"]))]
    else:
        for row in ranked:
            row.pop("zh_summary", None)
            row.pop("zh_keywords", None)
    # Hybrid order only when vectors are ready; otherwise BM25 rows, scores and order are returned untouched.
    try:
        fused = fuse_hits(store, query, ranked, limit, external, company_id, per_document)
    except Exception:
        fused = None
    if fused is not None:
        return fused
    return ranked[:limit]


def _field_matches(text, terms):
    field_tokens = set(tokens(text))
    phrases = [term for term in terms if len(term) > 2 and re.fullmatch(r"[\u4e00-\u9fff]+", term) and term in (text or "")]
    found = phrases + [term for term in terms if term in field_tokens and term not in phrases]
    return [term for term in found if term in phrases or not any(term in phrase for phrase in phrases)]


def _locator_range(locator):
    match = re.search(r"正文字符\s*(\d+)\s*[–-]\s*(\d+)", locator or "")
    if not match:
        return None
    return int(match.group(1)) - 1, int(match.group(2))


def _term_spans(text, terms):
    spans = []
    lowered = text.lower()
    for term in sorted(set(terms), key=len, reverse=True):
        if len(term) < 2:
            continue
        if re.fullmatch(r"[a-z0-9]+", term, re.I):
            pattern = re.compile(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])")
            iterator = pattern.finditer(lowered)
        else:
            iterator = re.finditer(re.escape(term), text)
        for match in iterator:
            spans.append((match.start(), match.end(), term))
    spans.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    return spans


def _hit_windows(text, terms, locator, maximum=3, radius=120):
    spans = _term_spans(text, terms)
    if not spans:
        return []
    segment = _locator_range(locator)
    candidates = []
    for start, end, term in spans:
        left = max(0, start - radius)
        right = min(len(text), end + radius)
        hits = {item[2] for item in spans if item[0] < right and item[1] > left}
        in_segment = bool(segment and start >= segment[0] and end <= segment[1])
        candidates.append({
            "start": left,
            "end": right,
            "text": text[left:right],
            "terms": sorted(hits),
            "_rank": (0 if in_segment else 1, -len(hits), left),
        })
    candidates.sort(key=lambda item: item["_rank"])
    chosen = []
    for item in candidates:
        if any(item["start"] < kept["end"] and item["end"] > kept["start"] for kept in chosen):
            continue
        chosen.append(item)
        if len(chosen) >= maximum:
            break
    for item in chosen:
        item.pop("_rank", None)
    return sorted(chosen, key=lambda item: item["start"])


def _group_key(title, url):
    normalized_title = re.sub(r"^(?:［网页存档[^］]*］|［RSS］)\s*", "", title or "").strip()
    if url:
        parsed = urlsplit(url)
        host = parsed.netloc.lower().removeprefix("www.")
        path = parsed.path.rstrip("/")
        return f"{host}{path}".lower()
    return normalized_title.lower()


def kind_label(store, doc):
    if store.one("SELECT 1 AS x FROM companies WHERE document_id=?", (doc["id"],)):
        return "公司档案"
    if (doc.get("filename") or "").startswith("website-snapshot"):
        return "网站入库"
    if doc.get("file_path") or doc.get("has_file"):
        return "上传资料"
    return "手动录入"


def annotate_hits(store, query, hits, viewer_company_id=None):
    """Add explainability and reading metadata without changing BM25 score or order."""
    base_terms = list(dict.fromkeys(tokens(query)))
    for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", query):
        if phrase not in base_terms:
            base_terms.append(phrase)
    expanded_terms = list(dict.fromkeys(base_terms + tokens(query, expand=True)))
    annotated = []
    for hit in hits:
        doc = store.one(
            """SELECT id,title,source,url,date,date_source,created_at,archived_at,fetched_at,
                      filename,file_path,company_id,body FROM documents WHERE id=?""",
            (hit["document_id"],),
        )
        if not doc:
            continue
        # Same rule as retrieve(): cross-lingual expansion only counts for documents with a Chinese summary/keywords.
        enriched = bool(hit.get("zh_summary") or hit.get("zh_keywords"))
        field_terms = expanded_terms if enriched else base_terms
        body_tokens = set(tokens(doc["body"]))
        matched = {
            "title": _field_matches(doc["title"], field_terms),
            "zh_summary": _field_matches(hit.get("zh_summary") or "", field_terms),
            "zh_keywords": _field_matches(hit.get("zh_keywords") or "", field_terms),
            "body": _field_matches(doc["body"], field_terms),
            "expanded": [term for term in field_terms if term not in base_terms and term in body_tokens],
        }
        body_terms = sorted(
            dict.fromkeys(item[2] for item in _term_spans(doc["body"], field_terms)),
            key=len,
            reverse=True,
        )
        hit_windows = _hit_windows(doc["body"], field_terms, hit.get("locator", ""))
        row = {
            **hit,
            "url": doc["url"],
            "created_at": doc["created_at"],
            "date_source": doc["date_source"],
            "archived_at": doc["archived_at"],
            "fetched_at": doc["fetched_at"],
            "characters": len(doc["body"]),
            "kind_label": kind_label(store, doc),
            "matched": matched,
            "hit_windows": hit_windows,
            "body_hit": bool(hit_windows),
            "highlight_terms": body_terms,
            "editable": viewer_company_id is None or doc.get("company_id") == viewer_company_id,
            "group_key": _group_key(doc["title"], doc["url"]),
        }
        annotated.append(row)
    return annotated
