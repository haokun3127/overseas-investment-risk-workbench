"""Validate administrator-retained public PDF text copies, never search snippets."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .publication import normalize

MAX_COPY_BYTES = 2 * 1024 * 1024


def read_reference_copy(directory, url):
    target = urlsplit(url)
    if (target.scheme != 'https' or target.netloc != 'kppu.go.id' or target.query or target.fragment
            or not re.fullmatch(r'/uploads/siaran-pers/\d+_Siaran-Pers-No\.?-?\d+_KPPU-PR_[IVX]+_\d{4}(?:-Ralat)?\.pdf', target.path)):
        return None
    root = Path(directory) / 'reference-copies'
    manifest = root / 'manifest.json'
    if not manifest.exists():
        return None
    try:
        if manifest.is_symlink() or manifest.stat().st_size > 128 * 1024:
            raise ValueError('副本目录索引不合规。')
        data = json.loads(manifest.read_text(encoding='utf-8'))
        if data.get('version') != 1 or not isinstance(data.get('items'), list):
            raise ValueError('副本目录格式无效。')
        matches = [item for item in data['items'] if isinstance(item, dict) and item.get('url') == url]
        if not matches:
            return None
        if len(matches) != 1:
            raise ValueError('同一网址对应多个副本，未采用。')
        item = matches[0]
        filename = item.get('file', '')
        if not isinstance(filename, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}\.txt', filename):
            raise ValueError('副本文件名无效。')
        file = root / filename
        if root.is_symlink() or file.is_symlink() or file.resolve().parent != root.resolve():
            raise ValueError('副本文件超出指定目录。')
        if file.stat().st_size > MAX_COPY_BYTES:
            raise ValueError('副本超过读取限制。')
        raw = file.read_bytes()
        if hashlib.sha256(raw).hexdigest() != item.get('sha256'):
            raise ValueError('副本内容哈希校验未通过。')
        text = raw.decode('utf-8').replace('\r\n', '\n')
        header, marker, body = text.partition('Markdown Content:\n')
        if not marker or len(body.strip()) < 1000 or len(body) > MAX_COPY_BYTES:
            raise ValueError('未取得完整的PDF文本。')
        if ('URL Source: ' + url) not in header.splitlines() or 'Number of Pages: 3' not in header.splitlines():
            raise ValueError('副本原始网址或页数不匹配。')
        if item.get('provider') != 'Jina Reader' or item.get('retrieval_url') != 'https://r.jina.ai/' + url:
            raise ValueError('副本获取来源不匹配。')
        number = re.search(r'No\.?-?(\d+)_KPPU-PR_([IVX]+)_(\d{4})', target.path)
        identity = number[1] + '/KPPU-PR/' + number[2] + '/' + number[3]
        if not body.lstrip().startswith('SIARAN PERS KPPU') or ('Nomor ' + identity) not in body[:300]:
            raise ValueError('副本文件编号与原网址不一致。')
        dates = re.findall(r'Siaran pers ini dipublikasikan pada\s+(\d{1,2}\s+\w+\s+\d{4})', body)
        normalized = {normalize(value) for value in dates}
        if len(normalized) != 1 or '' in normalized or item.get('date') not in normalized:
            raise ValueError('副本正文中的发布日期无法核对。')
        fetched = datetime.fromisoformat(item['retrieved_at'])
        if fetched.tzinfo is None or fetched > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError('副本获取时间无效。')
        title = item.get('title', '')
        if not isinstance(title, str) or not title.strip() or len(title) > 180:
            raise ValueError('副本标题无效。')
        return dict(item, raw=raw, body=body, title='［PDF文本副本］' + title)
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, AttributeError) as error:
        raise ValueError('留存副本无法校验：' + type(error).__name__) from error
