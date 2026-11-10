"""Validate one retained Common Crawl response without replaying remote HTML."""
import base64
import gzip
import hashlib
import io
import json
import re
import zlib
from datetime import datetime, timedelta, timezone
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path

ARTICLE_PATH = '/gjhz/ydyl/202210/20221012/j_2022101209031700016758393063044357.html'
TARGET = 'https://www.capco.org.cn' + ARTICLE_PATH
ORIGINAL = 'https://capco.org.cn/pub/zgssgsxh' + ARTICLE_PATH
TITLE = '赞宇科技：在印尼打造油化行业龙头新版图'
MAX_BYTES = 2 * 1024 * 1024


def _digest(raw):
    return base64.b32encode(hashlib.sha1(raw).digest()).decode().rstrip('=')


def _header(raw, key):
    values = raw.get_all(key, [])
    if len(values) != 1:
        raise ValueError('存档响应字段缺失或重复：' + key)
    return str(values[0])


class _Identity(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.titles, self.bylines, self.text = [], [], []
        self.parts, self.depth, self.kind = None, 0, ''

    def handle_starttag(self, tag, attrs):
        if tag in {'br', 'hr', 'img', 'input', 'meta', 'link', 'source', 'wbr'}:
            return
        if self.parts is not None:
            self.depth += 1
        elif tag == 'h3' or (tag == 'div' and 'ly' in dict(attrs).get('class', '').split()):
            self.parts, self.depth, self.kind = [], 1, tag

    def handle_endtag(self, tag):
        if tag in {'br', 'hr', 'img', 'input', 'meta', 'link', 'source', 'wbr'}:
            return
        if self.parts is not None:
            self.depth -= 1
            if self.depth == 0:
                (self.titles if self.kind == 'h3' else self.bylines).append(''.join(self.parts))
                self.parts = None

    def handle_data(self, text):
        self.text.append(text)
        if self.parts is not None:
            self.parts.append(text)


def read_archive_copy(directory, url):
    if url not in {ORIGINAL, TARGET}:
        return None
    root = Path(directory) / 'archive-copies'
    manifest = root / 'manifest.json'
    if not manifest.exists():
        return None
    try:
        if root.is_symlink() or manifest.is_symlink() or manifest.stat().st_size > 128 * 1024:
            raise ValueError('存档副本目录不合规。')
        data = json.loads(manifest.read_text(encoding='utf-8'))
        if data.get('version') != 1 or not isinstance(data.get('items'), list):
            raise ValueError('存档副本目录格式无效。')
        items = [i for i in data['items'] if isinstance(i, dict) and i.get('url') == ORIGINAL]
        if not items:
            return None
        if len(items) != 1:
            raise ValueError('同一原网址对应多个存档副本。')
        item = items[0]
        name = item.get('file', '')
        if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}\.warc\.gz', name):
            raise ValueError('存档副本文件名无效。')
        file = root / name
        if file.is_symlink() or file.resolve().parent != root.resolve() or file.stat().st_size > MAX_BYTES:
            raise ValueError('存档副本文件路径或大小不合规。')
        compressed = file.read_bytes()
        if len(compressed) != item['length'] or hashlib.sha256(compressed).hexdigest() != item['sha256']:
            raise ValueError('存档副本长度或哈希校验未通过。')
        collection = item['collection']
        if not re.fullmatch(r'CC-MAIN-20\d{2}-\d{2}', collection):
            raise ValueError('存档批次无效。')
        pattern = rf'crawl-data/{collection}/segments/\d+\.\d+/warc/CC-MAIN-\d{{14}}-\d{{14}}-\d{{5}}\.warc\.gz'
        if (item['provider'] != 'Common Crawl' or not re.fullmatch(pattern, item['warc_path'])
                or item['retrieval_url'] != 'https://data.commoncrawl.org/' + item['warc_path']
                or type(item['offset']) is not int or item['offset'] < 0 or item['target_url'] != TARGET):
            raise ValueError('存档来源信息不匹配。')
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('存档解压结果超过限制。')
        first, rest = raw.split(b'\r\n', 1)
        if first not in {b'WARC/1.0', b'WARC/1.1'}:
            raise ValueError('不是有效的WARC存档响应。')
        head, block = rest.split(b'\r\n\r\n', 1)
        warc = BytesParser().parsebytes(head + b'\r\n\r\n')
        size = int(_header(warc, 'Content-Length'))
        if size < 1 or len(block) < size or block[size:].strip(b'\r\n'):
            raise ValueError('存档响应长度不一致或包含额外记录。')
        block = block[:size]
        if (_header(warc, 'WARC-Type') != 'response'
                or _header(warc, 'WARC-Target-URI') != TARGET
                or _header(warc, 'WARC-Record-ID') != item['record_id']
                or _header(warc, 'WARC-Date') != item['captured_at']
                or _header(warc, 'WARC-Block-Digest') != 'sha1:' + _digest(block)):
            raise ValueError('存档记录身份或响应校验值不匹配。')
        status, response = block.split(b'\r\n', 1)
        http_head, body = response.split(b'\r\n\r\n', 1)
        headers = BytesParser().parsebytes(http_head + b'\r\n\r\n')
        if (status != b'HTTP/1.1 200 OK' or len(body) != int(_header(headers, 'Content-Length'))
                or _header(headers, 'Content-Type').split(';')[0].strip().lower() != 'text/html'
                or headers.get('Transfer-Encoding') or headers.get('Content-Encoding')):
            raise ValueError('存档未包含完整的200 HTML原文。')
        if (_header(warc, 'WARC-Payload-Digest') != 'sha1:' + _digest(body)
                or item['payload_digest'] != _digest(body)):
            raise ValueError('存档正文校验值不匹配。')
        html = body.decode('utf-8')
        parser = _Identity(); parser.feed(html)
        text = ''.join(parser.text)
        sections = ['一、公司简介', '二、杜库达油化工厂项目情况', '社会责任', '四、海外投资遇到的风险挑战']
        if TITLE not in parser.titles or len(text) < 1800 or not all(s in text for s in sections):
            raise ValueError('存档未包含目标文章的完整章节。')
        dates = {m for line in parser.bylines for m in re.findall(r'发布时间\s*[：:]\s*(\d{4}-\d{2}-\d{2})', line)}
        if dates != {'2022-10-12'}:
            raise ValueError('无法核对原文发布日期。')
        captured = datetime.fromisoformat(item['captured_at'].replace('Z', '+00:00'))
        retrieved = datetime.fromisoformat(item['retrieved_at'].replace('Z', '+00:00'))
        if (captured.tzinfo is None or retrieved.tzinfo is None or retrieved < captured
                or retrieved > datetime.now(timezone.utc) + timedelta(minutes=5)):
            raise ValueError('存档时间或副本获取时间无效。')
        return dict(item, raw=body, html=html, date='2022-10-12', archived_at=captured.date().isoformat())
    except (OSError, EOFError, UnicodeError, KeyError, TypeError, AttributeError, zlib.error) as error:
        raise ValueError('网页存档副本无法校验：' + type(error).__name__) from error
