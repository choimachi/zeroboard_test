#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ZEROBOARD note記事の公開メタデータ検証（最大3記事、本体・APIキー不要）。"""
import html
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

MAX_ARTICLES = 3
MAX_BYTES = 900_000
TIMEOUT = 12


def article_url(raw):
    p = urlparse(urljoin('https://note.com/', html.unescape(raw)))
    if p.hostname not in ('note.com', 'www.note.com'):
        return None
    if not re.fullmatch(r'/[^/]+/n/n[a-zA-Z0-9]+/?', p.path):
        return None
    return 'https://note.com' + p.path.rstrip('/')


class Metadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.meta = {}
        self.page_title = ''
        self._title = False
        self._jsonld = False
        self._jsonld_buf = []
        self.jsonld = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'a' and a.get('href'):
            self.links.append(a['href'])
        elif tag == 'meta':
            key = a.get('property') or a.get('name') or a.get('itemprop')
            if key and a.get('content') and key not in self.meta:
                self.meta[key] = a['content']
        elif tag == 'title':
            self._title = True
        elif tag == 'script' and a.get('type', '').lower() == 'application/ld+json':
            self._jsonld = True
            self._jsonld_buf = []

    def handle_data(self, data):
        if self._title:
            self.page_title += data
        if self._jsonld:
            self._jsonld_buf.append(data)

    def handle_endtag(self, tag):
        if tag == 'title':
            self._title = False
        if tag == 'script' and self._jsonld:
            self._jsonld = False
            try:
                self.jsonld.append(json.loads(''.join(self._jsonld_buf)))
            except (ValueError, TypeError):
                pass


def request(url):
    req = Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; ZEROBOARD-article-metadata-check/1.0)',
        'Accept': 'text/html,application/xhtml+xml',
    })
    with urlopen(req, timeout=TIMEOUT) as r:
        body = r.read(MAX_BYTES + 1)
        return {'http_status': r.status, 'final_url': r.geturl(),
                'content_type': r.headers.get('Content-Type', ''),
                'truncated': len(body) > MAX_BYTES,
                'html': body[:MAX_BYTES].decode('utf-8', 'replace')}


def extract_price(data):
    """Only explicitly structured Offer price; no regex guessing from article body."""
    candidates = []
    def walk(node, depth=0):
        if depth > 10:
            return
        if isinstance(node, list):
            for x in node[:100]:
                walk(x, depth + 1)
        elif isinstance(node, dict):
            t = node.get('@type', '')
            types = [t] if isinstance(t, str) else t if isinstance(t, list) else []
            if 'Offer' in types and 'price' in node:
                candidates.append({'price': node['price'], 'currency': node.get('priceCurrency', '未記載'), 'source': 'JSON-LD Offer'})
            for v in node.values():
                if isinstance(v, (list, dict)):
                    walk(v, depth + 1)
    for x in data:
        walk(x)
    return candidates[:2]




def scout(tag='AI副業', max_articles=3):
    """Read public HTML only (tag + <=3 article pages); no account, API key or posting."""
    tag = str(tag or 'AI副業').strip()[:40]
    if not tag or any(ch in tag for ch in ('/', '?', '#', '&', '\n', '\r')):
        raise ValueError('タグには短いキーワードを指定してください。')
    max_articles = max(1, min(int(max_articles), MAX_ARTICLES))
    target = 'https://note.com/hashtag/' + quote(tag)
    report = {'checked_at_utc': datetime.now(timezone.utc).isoformat(),
              'tag': tag, 'tag_url': target, 'max_articles': max_articles,
              'requests_attempted': 0, 'articles': [],
              'important': '記事URLの存在や記事タイトルは販売・購入需要の証明ではありません。価格・公開日が見つからなければ未確認。'}
    try:
        report['requests_attempted'] += 1
        page = request(target)
        report['tag_http_status'] = page['http_status']
        if page['http_status'] != 200 or 'html' not in page['content_type'].lower():
            report['status'] = 'tag_page_not_html'
            return report
        parser = Metadata()
        parser.feed(page['html'])
        urls = list(dict.fromkeys(filter(None, (article_url(x) for x in parser.links))))
        report['tag_article_links_found'] = len(urls)
        for url in urls[:max_articles]:
            time.sleep(0.7)
            item = {'url': url, 'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
                    'purchase_status': '未確認', 'review_status': '未確認',
                    'relevance_status': '関連性未確認（タグに掲載されているだけ）'}
            report['requests_attempted'] += 1
            try:
                response = request(url)
                item.update({'http_status': response['http_status'], 'final_url': response['final_url'],
                             'truncated': response['truncated']})
                if response['http_status'] == 200 and 'html' in response['content_type'].lower() and article_url(response['final_url']):
                    p = Metadata()
                    p.feed(response['html'])
                    item['title'] = html.unescape(p.meta.get('og:title', p.page_title)).strip()[:200]
                    item['published_date_claim'] = (p.meta.get('article:published_time') or
                                                     p.meta.get('datePublished') or None)
                    item['structured_prices'] = extract_price(p.jsonld)
                    item['price_status'] = ('構造化データに価格候補あり・原ページ要確認' if item['structured_prices'] else '未確認')
                    item['status'] = 'metadata_read'
                else:
                    item['status'] = 'article_not_html_or_redirected'
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                item.update({'status': 'fetch_failed', 'error_type': type(exc).__name__,
                             'http_status': getattr(exc, 'code', None)})
            report['articles'].append(item)
        report['status'] = 'complete' if report['articles'] else 'no_article_links'
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        report.update({'status': 'tag_fetch_failed', 'error_type': type(exc).__name__,
                       'http_status': getattr(exc, 'code', None)})
    return report


def meeting_brief(candidate, report):
    rows = []
    for article in report.get('articles', []):
        rows.append({'title': article.get('title') or '未取得', 'url': article.get('url'),
                     'published_date': article.get('published_date_claim') or '未確認',
                     'retrieved_at': article.get('retrieved_at_utc'),
                     'price': article.get('structured_prices') or '未確認',
                     'status': article.get('status')})
    context = {'candidate': str(candidate or '')[:160], 'tag': report.get('tag'),
               'articles': rows, 'limitations': 'タグ掲載記事は競合確定ではない。価格・レビュー・購入実績・関連性は原ページ確認まで未検証。'}
    return ('【ZEROBOARD Ver.40 公開note調査の追加検討】\n'
            'この情報を事実と仮説に分けて評価。新たな有料記事制作はCEO承認まで禁止。\n'
            + json.dumps(context, ensure_ascii=False, default=str)[:9000])
