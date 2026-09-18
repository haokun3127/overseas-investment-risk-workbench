import math
import re
from collections import Counter

def tokens(text):
    words = re.findall(r'[a-z0-9]{2,}', text.lower())
    for phrase in re.findall(r'[\u4e00-\u9fff]+', text):
        words.extend(phrase[i:i+2] for i in range(len(phrase)-1))
    return words

def retrieve(store, query, external=False, limit=4):
    condition = ' AND d.allow_external=1' if external else ''
    rows = store.rows('''SELECT c.id,c.document_id,c.locator,c.text,d.title,d.source,d.date FROM chunks c
        JOIN documents d ON d.id=c.document_id WHERE d.kind='knowledge' AND d.demo=0''' + condition)
    if not rows:
        return []
    query_terms = set(tokens(query))
    counters = [Counter(tokens(row['title'] + ' ' + row['text'])) for row in rows]
    average = sum(sum(c.values()) for c in counters) / max(len(counters),1) or 1
    frequency = Counter(term for c in counters for term in c)
    ranked = []
    for row, terms in zip(rows,counters):
        length = sum(terms.values())
        score = 0
        for term in query_terms & terms.keys():
            idf = math.log(1+(len(rows)-frequency[term]+0.5)/(frequency[term]+0.5))
            score += idf * terms[term]*2.2/(terms[term]+1.2*(0.25+0.75*length/average))
        if score > 0:
            row['score'] = round(score,3)
            ranked.append(row)
    return sorted(ranked,key=lambda r:r['score'],reverse=True)[:limit]
