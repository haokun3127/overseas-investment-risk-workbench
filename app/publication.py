"""Read a source's own publication date, never the first event date in its text."""
from datetime import date
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import io
import json
import re
from urllib.parse import urlsplit

MONTHS = {
    'januari': 1, 'februari': 2, 'maret': 3, 'april': 4, 'mei': 5, 'juni': 6,
    'juli': 7, 'agustus': 8, 'september': 9, 'oktober': 10, 'november': 11, 'desember': 12,
    'january': 1, 'february': 2, 'march': 3, 'may': 5, 'june': 6, 'july': 7,
    'august': 8, 'october': 10, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6, 'jul': 7,
    'aug': 8, 'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}
MONTH = '|'.join(sorted(MONTHS, key=len, reverse=True))
DATE = rf'(?:\d{{4}}\s*年\s*\d{{1,2}}\s*月\s*\d{{1,2}}\s*日|\d{{4}}[-/.]\d{{1,2}}[-/.]\d{{1,2}}|\d{{1,2}}/\d{{1,2}}/\d{{4}}|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTH})\.?\s+\d{{4}}|(?:{MONTH})\.?\s+\d{{1,2}},?\s+\d{{4}})'
LABEL = re.compile(rf'^\s*(?:发布时间|发布日期|发布于|发表时间|刊发日期|Published(?:\s+on|\s+at)?|Date\s+published|Release\s+(?:time|date)|Enforcement\s+Release|Tanggal\s+(?:Publikasi|Terbit)|Diterbitkan(?:\s+pada)?)\s*[:：]?\s*(?P<date>{DATE})(?!\d)', re.I | re.M)
DISPATCH = re.compile(rf'^\s*-?\s*Date\s+of\s+dispatch\s+to\s+(?:the\s+)?parties\s*:\s*(?P<date>{DATE})', re.I | re.M)
DATELINE = re.compile(rf'^\s*(?:(?:Senin|Selasa|Rabu|Kamis|Jumat|Sabtu|Minggu|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)[,，]?\s+)?(?P<date>{DATE})(?P<tail>.*)$', re.I)


def normalize(value):
    value = str(value or '').strip()
    numbers = re.match(r'^(\d{4})\s*(?:年|[-/.])\s*(\d{1,2})\s*(?:月|[-/.])\s*(\d{1,2})(?:日)?', value)
    if numbers:
        parts = numbers.groups()
    else:
        numeric = re.fullmatch(r'(\d{1,2})/(\d{1,2})/(\d{4})', value)
        written = re.match(rf'^(\d{{1,2}})(?:st|nd|rd|th)?\s+({MONTH})\.?\s+(\d{{4}})', value, re.I)
        reverse = re.match(rf'^({MONTH})\.?\s+(\d{{1,2}}),?\s+(\d{{4}})', value, re.I)
        if numeric:
            a, b, year = map(int, numeric.groups())
            # Without a declared locale, 08/12/2016 has two valid interpretations.
            if a <= 12 and b <= 12 and a != b:
                return ''
            parts = (year, b, a) if a > 12 else (year, a, b)
        elif written:
            parts = written.group(3), MONTHS[written.group(2).lower()], written.group(1)
        elif reverse:
            parts = reverse.group(3), MONTHS[reverse.group(1).lower()], reverse.group(2)
        else:
            try:
                found = parsedate_to_datetime(value).date()
                return found.isoformat() if 1900 <= found.year <= date.today().year + 1 else ''
            except (TypeError, ValueError, IndexError, OverflowError):
                return ''
    try:
        found = date(*(int(part) for part in parts))
        return found.isoformat() if 1900 <= found.year <= date.today().year + 1 else ''
    except (ValueError, TypeError):
        return ''


def _unique(candidates, source):
    valid = [(normalize(value), evidence) for value, evidence in candidates]
    valid = [(value, evidence) for value, evidence in valid if value]
    if len({value for value, _ in valid}) != 1:
        return '', '', ''
    return valid[0][0], source, valid[0][1]


def from_text(body, dateline_source='document_text'):
    body = body or ''
    head = body[:3000]
    labelled = [(match['date'], ' '.join(match.group().split())) for match in LABEL.finditer(head)]
    if labelled:
        return _unique(labelled, 'page_text')
    legal = bool(re.search(r'ICSID|I\.C\.S\.I\.D|INTERNATIONAL CENTRE FOR (?:THE )?SETTLEMENT|Decision on Jurisdiction', head, re.I))
    if legal:
        labelled = [(match['date'], match.group().strip()) for match in re.finditer(rf'^\s*DATE\s*:\s*(?P<date>{DATE})', head, re.I | re.M)]
        if labelled:
            return _unique(labelled, 'document_text')
    # A header dateline must stand on its own, optionally with a clock/source/weekday.
    # Narrative sentences such as "2023年10月4日，企业停止交易" are not publication dates.
    candidates = []
    previous = ''
    case_record = bool(re.search(r'^\s*Date Registered\s*:', head, re.I | re.M))
    for line in body[:1200].splitlines():
        match = DATELINE.match(line)
        prior, previous = previous, (line.strip() or previous)
        if not match:
            continue
        if case_record or re.search(r'(?:date registered|date of constitution(?: of [^:\n]+)?|modified|updated|更新时间|生效日期|截止日期)\s*[:：]?\s*$', prior, re.I):
            continue
        tail = match['tail'].strip()
        if not tail or re.fullmatch(r'(?:T|\s)*\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:WIB|WITA|WIT|UTC|GMT|Z|[+-]\d{2}:?\d{2}))?', tail, re.I) or re.fullmatch(r'(?:星期|周)[一二三四五六日天]', tail) or re.fullmatch(r'[•·]\s*[\w -]{1,40}', tail):
            candidates.append((match['date'], line.strip()))
    if candidates:
        return _unique(candidates, dateline_source)
    dispatch = [(match['date'], ' '.join(match.group().split())) for match in DISPATCH.finditer(head)]
    if dispatch:
        return _unique(dispatch, 'document_dispatch')
    # Newspaper mastheads carry a date and weekday after the section/page number.
    masthead = []
    for line in body[:350].splitlines():
        match = re.fullmatch(rf'[^。！？；:：]{{0,24}}?(?P<date>\d{{4}}\s*年\s*\d{{1,2}}\s*月\s*\d{{1,2}}\s*日)\s+(?:星期|周)[一二三四五六日天]', line.strip())
        if match:
            masthead.append((match['date'], line.strip()))
    if masthead:
        return _unique(masthead, 'page_text')
    # Require an actual signature block, not any date in the final narrative.
    tail = body[-4000:]
    signatures = []
    for match in re.finditer(rf'^\s*(?P<date>{DATE})\s*$', tail, re.I | re.M):
        context = tail[max(0, match.start()-400):match.start()]
        if re.search(r'(?:董事会|董事局|By Order of the Board)\s*(?:\n[^\n]*){0,5}$', context, re.I):
            signatures.append((match['date'], (context.strip() + '\n' + match.group().strip())[-500:]))
    if legal:
        for match in re.finditer(rf'^\s*(?:London|Paris|Washington|Singapore)\s*,?\s+(?P<date>{DATE})\s*$', tail, re.I | re.M):
            following = tail[match.end():match.end()+180]
            if re.search(r'(?i)IS/|/S/|arbitrator|Higgins|Lalonde', following):
                signatures.append((match['date'], tail[match.start():match.end()+180].strip()))
    return _unique(signatures, 'document_signature')


def from_snapshot(raw, content_type, body=''):
    if 'html' in content_type.lower():
        return from_html(raw.decode('utf-8', errors='replace'), body)
    if 'pdf' in content_type.lower() or raw.startswith(b'%PDF-'):
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(raw))
            indexes = sorted(set(range(min(2, len(reader.pages)))) | set(range(max(0, len(reader.pages)-2), len(reader.pages))))
            edges = '\n\n'.join(f'[第{i+1}页]\n{reader.pages[i].extract_text() or ""}' for i in indexes)
            return from_text(edges)
        except Exception:
            # A malformed/encrypted snapshot must not prevent import or date audit.
            return from_text(body)
    return from_text(body)


def from_disclosure_url(url):
    """Only known exchange disclosure directories, labelled as such in the UI."""
    try:
        parsed = urlsplit(url or '')
        port = parsed.port
    except ValueError:
        return '', '', ''
    if parsed.scheme != 'https' or parsed.username or parsed.password or port not in (None, 443):
        return '', '', ''
    if parsed.hostname == 'static.cninfo.com.cn':
        match = re.fullmatch(r'/finalpage/(\d{4}-\d{2}-\d{2})/\d+\.pdf', parsed.path, re.I)
    elif parsed.hostname == 'disc.static.szse.cn':
        match = re.fullmatch(r'/disc/disk\d+/finalpage/(\d{4}-\d{2}-\d{2})/[\w-]+\.pdf', parsed.path, re.I)
    elif parsed.hostname in {'www1.hkexnews.hk', 'www.hkexnews.hk'}:
        match = re.fullmatch(r'/listedco/listconews/sehk/(\d{4})/(\d{2})(\d{2})/(\d{8})\d+\.pdf', parsed.path, re.I)
        if match and ''.join(match.groups()[:3]) == match.group(4):
            value = normalize('-'.join(match.groups()[:3]))
            return (value, 'disclosure_path', url) if value else ('', '', '')
        return '', '', ''
    else:
        return '', '', ''
    value = normalize(match.group(1)) if match else ''
    return (value, 'disclosure_path', url) if value else ('', '', '')


class PublicationParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.candidates = []
        self.text_candidates = []
        self.json_text = None
        self.byline = None
        self.byline_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag not in {'meta', 'link', 'img', 'input', 'br', 'hr', 'source', 'wbr'}:
            if self.byline is not None:
                self.byline_depth += 1
            elif set(attrs.get('class', '').lower().split()) & {'entry-meta', 'article-meta', 'post-meta', 'news-date', 'publish-time', 'publication-date', 'pubdate'}:
                self.byline, self.byline_depth = [], 1
        key = (attrs.get('property') or attrs.get('name') or '').lower()
        if tag == 'meta' and key in {'article:published_time', 'datepublished', 'pubdate', 'publishdate', 'publish-date', 'publication_date', 'date', 'dc.date.issued', 'dcterms.issued'}:
            value = attrs.get('content', '')
            self.candidates.append((value, f'meta {key}={value}'))
        if tag == 'time' and attrs.get('itemprop', '').lower() == 'datepublished':
            value = attrs.get('datetime', '')
            self.candidates.append((value, f'time datePublished={value}'))
        if tag == 'script' and attrs.get('type', '').lower() == 'application/ld+json':
            self.json_text = []

    def handle_data(self, text):
        if self.byline is not None:
            self.byline.append(text)
        if self.json_text is not None:
            self.json_text.append(text)

    def handle_endtag(self, tag):
        if tag in {'meta', 'link', 'img', 'input', 'br', 'hr', 'source', 'wbr'}:
            return
        if self.byline is not None:
            self.byline_depth -= 1
            if self.byline_depth == 0:
                text = ' '.join(' '.join(self.byline).split())
                self.text_candidates.extend((match.group(), 'HTML publication byline: ' + text[:400])
                                            for match in re.finditer(DATE, text, re.I))
                self.byline = None
        if tag == 'script' and self.json_text is not None:
            try:
                self._walk(json.loads(''.join(self.json_text)))
            except (ValueError, RecursionError):
                pass
            self.json_text = None

    def _walk(self, value):
        if isinstance(value, dict):
            if isinstance(value.get('datePublished'), str):
                self.candidates.append((value['datePublished'], 'JSON-LD datePublished=' + value['datePublished']))
            # Do not use dates belonging to recommended/related articles.
            for key in ('@graph', 'mainEntity', 'mainEntityOfPage'):
                if key in value:
                    self._walk(value[key])
        elif isinstance(value, list):
            for item in value:
                self._walk(item)


def from_html(html, body=''):
    parser = PublicationParser()
    parser.feed(html or '')
    if any(normalize(value) for value, _ in parser.candidates):
        return _unique(parser.candidates, 'page_meta')
    if any(normalize(value) for value, _ in parser.text_candidates):
        return _unique(parser.text_candidates, 'page_text')
    return from_text(body, 'page_text')


def find_publication_date(title, body):
    # A title can contain event years, report periods or a web-archive date.
    value, source, _ = from_text(body, 'page_text')
    return value, source


def absence_note(row):
    if row.get('date'):
        return ''
    if str(row.get('title','')).startswith('公司档案'):
        return '公司档案无独立发布日期'
    text = row.get('body') or row.get('date_context') or ''
    if re.search(r'^\s*Date Registered\s*:',text[:3000],re.I|re.M):
        return '案件持续记录，无单一发布日期'
    if re.search(r'^\s*(?:updated|modified|更新时间)\s*[:：]',text[:1000],re.I|re.M):
        return '原文仅标更新时间，未标发布日期'
    if re.search(r'As of|For the Fiscal Year Ended',text[:3000],re.I):
        return '原文标有报告基准期，未标发布日期'
    if '事实摘录' in row.get('source',''):
        return '事实摘录未单列资料日期'
    return '原文未标明发布日期' if row.get('url') or row.get('method') else '资料日期未标注'
