"""Isolated browser fixture; never use this entry point for business data.

Run from repository root:
  .venv/bin/python -m uvicorn scripts.ui_websites_server:create_test_app --factory --port 8001
"""
import asyncio
import tempfile
from pathlib import Path

from app.config import ROOT, Settings
from app.main import create_app
from app import websites


def create_test_app():
    (ROOT / 'qa').mkdir(exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix='website-browser-', dir=ROOT / 'qa'))

    async def fixture_search(settings, request):
        await asyncio.sleep(.2)
        return [
            {'title': '合成测试：园区供电公告', 'url': 'https://example.com/news/power',
             'content': '合成检索摘要，仅用于浏览器验证。',
             'raw_content': '合成测试资料：某工业园区供电设施故障，生产线暂停，恢复时间待核实。',
             'published_date': '2026-10-09'},
            {'title': '合成测试：只有摘要', 'url': 'https://example.com/news/summary', 'content': '仅有摘要。'},
            {'title': '合成测试：范围外结果', 'url': 'https://other.example/news/power', 'raw_content': '范围外资料'},
        ]

    websites.PROVIDERS['browser_fixture'] = fixture_search
    settings = Settings(data_dir=directory, search_provider='browser_fixture', search_api_key='fixture-only',
                        model_base_url='', model_name='', model_api_key='')
    return create_app(settings)
