"""ZEROBOARD Ver.38: explicit, low-cost public-web competitor reconnaissance.

Only HTTP requests to public RSS search endpoints and note.com article pages.
No OpenAI calls, no writes, no claims of verified purchases/sales.
"""
from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse

ALLOWED_RSS_HOSTS = {'www.bing.com', 'news.google.com'}
ALLOWED_PAGE_HOSTS = {'note.com', 'www.note.com'}
TIMEOUT = 7
MAX_BYTES = 450_000
MAX_RESULTS = 5
PRICE = re.compile(r'(?:[¥￥]\s*\d{2,7}(?:,\d{3})*|\d{2,7}(?:,\d{3})*\s*円)')
NOTE_LINK = re.compile(r'https?://(?:www\.)?note\.com/[^\s"<>]+', re.I)


class PublicPage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.metadata = {}
        self.title = ''
        self._title = False
        self._script = False
        self._jsonld = []
        self._buffer = []

    def handle_starttag(self, tag, attrs):
        at = dict(attrs)
        if tag == 'meta':
            key = at.get('property') or at.get('name') or ''
            if key and at.get('content'):
                self.metadata.setdefault(key.lower(), at['content'])
        if tag == 'title': self._title = True
        if tag == 'script' and at.get('type') == 'application/ld+json':
            self._script = True
            self._buffer = []

    def handle_endtag(self, tag):
        if tag == 'title': self._title = False
        if tag == 'script' and self._script:
            self._script = False
            try: self._jsonld.append(json.loads(''.join(self._buffer)))
            except (ValueError, TypeError): pass
            self._buffer = []

    def handle_data(self, data):
        if self._title: self.title += data
        if self._script: self._buffer.append(data)


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts = hosts

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if parsed.scheme != 'https' or parsed.hostname not in self.hosts:
            raise ValueError('安全のため許可されていない転送先をブロックしました')
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _fetch(url: str, hosts: set[str]) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in hosts:
        raise ValueError('指定外のホストへのアクセスは禁止しています')
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; ZEROBOARD research; public pages only)',
        'Accept': 'application/rss+xml,application/xml,text/html;q=0.9,*/*;q=0.3',
    })
    opener = urllib.request.build_opener(SafeRedirect(hosts))
    with opener.open(req, timeout=TIMEOUT) as response:
        if response.status != 200: raise ValueError('HTTP status '+str(response.status))
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES: raise ValueError('取得サイズの上限を超えました')
        charset = response.headers.get_content_charset() or 'utf-8'
        return raw.decode(charset, errors='replace'), response.geturl()


def _terms(title: str) -> str:
    clean = re.sub(r'[^\w一-龯ぁ-んァ-ンー\s]', ' ', title or '').strip()
    clean = re.sub(r'\s+', ' ', clean)
    # Short, meaningful search; no user supplied URL/host admitted.
    return clean[:65]


def _search_rss(query: str, max_results: int) -> tuple[list[dict], list[str]]:
    # Bing RSS is web search (site-limited), not generic news headlines.
    urls = [
        'https://www.bing.com/search?'+urllib.parse.urlencode({'q':'site:note.com '+query+' 有料','format':'rss'}),
        'https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':'site:note.com '+query,'hl':'ja','gl':'JP','ceid':'JP:ja'}),
    ]
    found, errors, seen = [], [], set()
    for url in urls:
        try:
            data, _ = _fetch(url, ALLOWED_RSS_HOSTS)
            root = ET.fromstring(data)
            for item in root.findall('.//item'):
                title = html.unescape(''.join(item.find('title').itertext()) if item.find('title') is not None else '')
                link = (item.findtext('link') or '').strip()
                parsed = urlparse(link)
                if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_PAGE_HOSTS:
                    # Google News links are redirects; we will not treat them as direct note pages.
                    continue
                link = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
                if link in seen: continue
                seen.add(link)
                desc = html.unescape(re.sub('<[^>]+>', ' ',item.findtext('description') or ''))
                found.append({'title':title[:240],'url':link,'snippet':desc[:380],
                              'feed_published':item.findtext('pubDate') or '不明',
                              'source_type':'検索RSSの見出し（競合確認前）'})
                if len(found) >= max_results: break
        except Exception as exc:
            errors.append(type(exc).__name__+': '+str(exc)[:160])
        if len(found) >= max_results: break
    return found, errors


def _page_info(url: str) -> dict:
    page, final = _fetch(url, ALLOWED_PAGE_HOSTS)
    parser = PublicPage()
    parser.feed(page)
    m = parser.metadata
    text_title = html.unescape(m.get('og:title') or parser.title or '')[:240]
    description = html.unescape(m.get('og:description') or m.get('description') or '')[:450]
    # Price digits in the article body can refer to unrelated things; do not assert listing price.
    # Restrict visible candidate price to explicit meta / structured offer only.
    structured = []
    def visit(node):
        if isinstance(node, list):
            for value in node: visit(value)
        elif isinstance(node, dict):
            offer = node.get('offers')
            if isinstance(offer, dict) and 'price' in offer:
                structured.append({'value':str(offer.get('price')), 'currency':str(offer.get('priceCurrency') or '未確認')})
            for value in node.values():
                if isinstance(value,(dict,list)): visit(value)
    for obj in parser._jsonld: visit(obj)
    price_value = m.get('product:price:amount')
    if price_value: structured.append({'value':price_value,'currency':m.get('product:price:currency') or '未確認'})
    return {
        'url':final,'title':text_title,'description':description,
        'article_published_at':m.get('article:published_time') or m.get('datepublished') or '未確認',
        'price_evidence':structured[:3],
        'price_status':'ページの構造化データ上に価格らしい記載あり（現在の購入画面は未検証）' if structured else '公開ページのメタ情報からは価格を確認できず',
        'review_status':'未確認（購入者レビュー・販売件数は検証していません）',
        'purchase_status':'未確認（閲覧数・スキは購入実績ではありません）',
    }


def research(title: str, max_results: int = 3, search_query: str | None = None) -> dict:
    """User-triggered research: <=2 search requests + <=3 article requests."""
    if not isinstance(title,str) or not title.strip(): raise ValueError('商品候補のタイトルが必要です')
    count = max(1, min(3, int(max_results)))
    keyword = _terms(search_query or title)
    leads, errors = _search_rss(keyword, count)
    articles = []
    for lead in leads:
        try:
            article = _page_info(lead['url'])
            article['search_headline'] = lead['title']
            article['search_published_at'] = lead['feed_published']
            article['status'] = 'note.com公開ページのメタ情報を取得（販売実績未確認）'
            articles.append(article)
        except Exception as exc:
            errors.append('記事ページ取得失敗: '+type(exc).__name__+': '+str(exc)[:150])
            articles.append({'url':lead['url'],'title':lead['title'],
                             'status':'記事ページ未確認（RSS見出しのみ）',
                             'price_status':'未確認','review_status':'未確認','purchase_status':'未確認'})
    return {
        'candidate_title':title, 'query':keyword,
        'retrieved_at':datetime.now(timezone.utc).isoformat(),
        'articles':articles, 'errors':errors,
        'attempted_search_sources':2,'checked_pages':sum('メタ情報を取得' in a['status'] for a in articles),
        'explicit_price_leads':sum(bool(a.get('price_evidence')) for a in articles),
        'verified_purchases':0,
        'conclusion':'販売件数・購入意思は未確認。競合・価格らしい記述は商品ページ上の確認手がかりであり、需要の立証ではありません。',
        'limits':'公開検索RSSの検索範囲に限られます。Google Newsの中継URLは安全上除外。検索ヒットなしは競合不在を意味しません。',
    }


def meeting_brief(idea: dict, result: dict) -> str:
    lines = [
        '【Ver.38／商品追加調査・CEO判断待ち】',
        '商品候補：'+str(idea.get('title') or ''),
        '想定読者（仮説）：'+str(idea.get('reader') or ''),
        '有料価値（仮説）：'+str(idea.get('paid_value') or ''),
        '公開noteページの確認件数：'+str(result['checked_pages']),
        '確認日時（UTC）：'+result['retrieved_at'],
        '価格の根拠が見つかった記事：'+str(result['explicit_price_leads']),
        '購入件数／売上／レビューの真正性：未確認',
    ]
    for a in result['articles'][:3]:
        prices = ', '.join(v['value']+' '+v['currency'] for v in a.get('price_evidence',[])) or '未確認'
        lines.append('候補記事：'+str(a.get('title',''))+'｜価格候補：'+prices+'｜状態：'+a['status']+'｜'+a['url'])
    lines.extend([
        '調査上の制約：'+result['limits'],
        '役員への依頼：関連情報を購入需要と誤認せず、販売ページと価格をCEOが確認すべきか、他の商品の調査を優先するか検討してください。',
        'CEOが承認するまで有料記事生成・公開・購入・外部支出は行わない。',
    ])
    return '\n'.join(lines)[:6500]
