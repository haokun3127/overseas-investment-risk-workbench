"""Read administrator-retained SGX originals after live retrieval fails."""
import hashlib
import io
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from .publication import from_text

MAX_BYTES = 8 * 1024 * 1024


def read_retained_pdf(directory, url):
    target = urlsplit(url)
    query = parse_qs(target.query)
    if (target.scheme != 'https' or target.netloc != 'links.sgx.com' or target.fragment
            or not target.path.startswith('/FileOpen/') or not target.path.endswith('.ashx')
            or set(query) != {'AnncID', 'App', 'FileID'}
            or query['App'] != ['ArchiveAnnouncement']
            or len(query['AnncID']) != 1 or not re.fullmatch(r'[A-Za-z0-9]{1,80}', query['AnncID'][0])
            or len(query['FileID']) != 1 or not query['FileID'][0].isdigit()):
        return None
    root = Path(directory) / 'reference-copies'
    manifest = root / 'pdf-manifest.json'
    if not manifest.exists():
        return None
    try:
        if root.is_symlink() or manifest.is_symlink() or manifest.stat().st_size > 128 * 1024:
            raise ValueError('PDF原件留存索引不合规。')
        data = json.loads(manifest.read_text(encoding='utf-8'))
        if data.get('version') != 1 or not isinstance(data.get('items'), list):
            raise ValueError('PDF原件留存索引格式无效。')
        matches = [item for item in data['items'] if isinstance(item, dict) and item.get('url') == url]
        if not matches:
            return None
        if len(matches) != 1:
            raise ValueError('同一网址对应多个PDF原件留存。')
        item = matches[0]
        filename = item.get('file', '')
        if not isinstance(filename, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}\.pdf', filename):
            raise ValueError('PDF原件留存文件名无效。')
        file = root / filename
        if file.is_symlink() or file.resolve().parent != root.resolve() or file.stat().st_size > MAX_BYTES:
            raise ValueError('PDF原件留存路径或大小不合规。')
        raw = file.read_bytes()
        if (not raw.startswith(b'%PDF-') or len(raw) != item.get('bytes')
                or hashlib.sha256(raw).hexdigest() != item.get('sha256')):
            raise ValueError('PDF原件留存长度或哈希校验未通过。')
        if item.get('provider') != 'original_download' or item.get('retrieval_url') != url:
            raise ValueError('PDF原件留存的下载来源不匹配。')
        fetched = datetime.fromisoformat(item['retrieved_at'])
        if fetched.tzinfo is None or fetched > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError('PDF原件留存获取时间无效。')
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 50 or len(reader.pages) != item.get('pages'):
            raise ValueError('PDF原件留存加密或页数不符。')
        body = '\n\n'.join(page.extract_text() or '' for page in reader.pages)
        if not 100 <= len(body) <= 60000:
            raise ValueError('PDF原件留存未取得完整可检索文本。')
        date, provenance, _ = from_text(body)
        if not date or date != item.get('date'):
            raise ValueError('PDF原件留存发布日期无法与正文核对。')
        title = item.get('title', '')
        if not isinstance(title, str) or not title.strip() or len(title) > 180:
            raise ValueError('PDF原件留存标题无效。')
        return dict(item, raw=raw, body=body, date_source=provenance, title='［PDF原件留存］' + title)
    except (OSError, UnicodeError, KeyError, TypeError, PdfReadError) as error:
        raise ValueError('PDF原件留存无法校验：' + type(error).__name__) from error
