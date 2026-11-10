import socket

import pytest

from app import websearch as web


def test_specific_case_after_long_glossary_is_in_review_input():
    glossary = ('Investment arbitration jurisdiction: a general methodological definition.\n' * 300)
    facts = ('Case: Investor Gamma v. Republic Delta.\n'
             'Investor Gamma held an indirect investment in Bank Delta.\n'
             'The arbitration tribunal declined jurisdiction.\n')
    body = glossary + facts
    window = web.review_window(body, 'Gamma Delta investment arbitration jurisdiction')
    assert facts in window
    assert len(window) == 6000 and window in body


def test_keyword_repetition_does_not_outvote_distinct_company_subjects():
    body = ('Factory factory factory factory factory.\n' * 250
            + 'Company Omega operates a factory in Province Beta.\n' * 12)
    window = web.review_window(body, 'factory Omega Beta')
    assert 'Company Omega operates a factory in Province Beta.' in window
    assert window in body and len(window) <= 6000


def test_english_keywords_do_not_match_inside_unrelated_words():
    body = 'flawless ' * 1400 + 'The law applies to export permits.\n'
    assert 'The law applies to export permits.' in web.review_window(body, 'law')


def test_duplicate_keywords_do_not_change_window_and_no_hits_keep_opening():
    body = 'unrelated material.\n' * 400 + 'Company Gamma must renew its permit.\n'
    assert web.review_window(body, 'Gamma Gamma permit') == web.review_window(body, 'Gamma permit')
    assert web.review_window(body, 'nonexistent') == body[:6000]


@pytest.mark.parametrize('host', ['newsroom.tiktok.com', 'www.thejakartapost.com'])
def test_vetted_publisher_poisoned_dns_can_use_verified_public_resolution(monkeypatch, host):
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **k: [(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))])
    calls = []
    monkeypatch.setattr(web, 'trusted_public_address', lambda name: calls.append(name) or '8.8.8.8')
    assert web.public_address(host,443) == '8.8.8.8'
    assert calls == [host]
    for private in ['localhost', '127.0.0.1', '169.254.169.254', 'other.example']:
        with pytest.raises(ValueError):web.public_address(private,443)
    assert calls == [host]
